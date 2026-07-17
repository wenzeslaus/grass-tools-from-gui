#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       g.model.run
# AUTHOR(S):    Vaclav Petras (with substantial AI assistance)
#               Based on gui/wxpython/gmodeler by Martin Landa and
#               Ondrej Pesek
# PURPOSE:      Run a Graphical Modeler model file (.gxm) without the GUI
# COPYRIGHT:    (C) 2026 by the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Runs a model prepared in the wxGUI Graphical Modeler.
# % keyword: general
# % keyword: modeler
# % keyword: model
# % keyword: workflow
# %end
# %option G_OPT_F_INPUT
# % description: Name of model file (.gxm) to run
# %end
# %option
# % key: variables
# % type: string
# % required: no
# % multiple: yes
# % key_desc: name=value
# % label: Values of model variables
# % description: Overrides the default values defined in the model
# %end
# %option
# % key: parameters
# % type: string
# % required: no
# % multiple: yes
# % key_desc: action.option=value
# % label: Values of parameterized options and flags
# % description: Action is a numeric action id or a tool name from the model; flags take true or false
# %end
# %flag
# % key: i
# % description: Keep intermediate data instead of removing them at the end
# %end

import ast
import operator
import os
import re
import shlex
import sys
import xml.etree.ElementTree as ET

import grass.script as gs
from grass.exceptions import CalledModuleError

# Begin of the .gxm parser shared verbatim with g.model.export; keep both
# copies identical. As a follow-up, this parser should move to a Python
# library (e.g., a new grass.models package) so that the GUI modeler can
# use it as well.

UNRESOLVED_VARIABLE = re.compile(r"%\{([^}]+)\}")


class ModelFileError(Exception):
    """Raised when a file cannot be processed as a GXM model file."""


def _element_text(node, tag, default=""):
    """Get whitespace-normalized text of a child element"""
    child = node.find(tag)
    if child is None or child.text is None:
        return default
    return " ".join(child.text.split())


def _legacy_unescape(value):
    """Reverse the extra escaping present in some older model files.

    Mirrors ProcessModelFile._filterValue in gui/wxpython/gmodeler/model.py.
    """
    return value.replace("&lt;", "<").replace("&gt;", ">")


def parse_gxm(path):
    """Parse a Graphical Modeler model file (.gxm).

    The format is defined by WriteModelFile and ProcessModelFile in
    gui/wxpython/gmodeler/model.py. Layout-only information (positions,
    sizes, relation control points, canvas comments) is not preserved.

    Returns a dictionary with the following keys:

    - properties: name, description, author, and overwrite (bool)
    - variables: variable name to {type, value, description} mapping
    - items: actions and loops ordered by item id, distinguished by "kind";
      an action has id, label, module, enabled, comment, flags (each with
      name, enabled, parameterized), params (each with name, value,
      parameterized), and loop_ids (ids of loops it belongs to); a loop has
      id, condition, and item_ids
    - data: data items, each with prompt, value, and intermediate
    - condition_ids: ids of if-else items (parsed only to be reported)

    Raises ModelFileError when the file is not a valid model file.
    """
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ModelFileError(str(error))
    if root is None or root.tag != "gxm":
        message = "root element is not <gxm>"
        raise ModelFileError(message)

    properties = {"name": "", "description": "", "author": "", "overwrite": False}
    properties_node = root.find("properties")
    if properties_node is not None:
        for key in ("name", "description", "author"):
            properties[key] = _element_text(properties_node, key)
        for flag_node in properties_node.findall("flag"):
            if flag_node.get("name") == "overwrite":
                properties["overwrite"] = True

    variables = {}
    variables_node = root.find("variables")
    if variables_node is not None:
        for node in variables_node.findall("variable"):
            name = node.get("name", "")
            if not name:
                continue
            variables[name] = {
                "type": node.get("type", "string"),
                "value": _element_text(node, "value"),
                "description": _element_text(node, "description"),
            }

    items = []
    for node in root.findall("action"):
        task = node.find("task")
        if task is None:
            continue
        flags = []
        params = []
        for flag_node in task.findall("flag"):
            flags.append(
                {
                    "name": flag_node.get("name", ""),
                    # A parameterized flag can be stored as unset (value="0").
                    "enabled": flag_node.get("value", "1") != "0",
                    "parameterized": flag_node.get("parameterized", "0") == "1",
                }
            )
        for param_node in task.findall("parameter"):
            params.append(
                {
                    "name": param_node.get("name", ""),
                    "value": _legacy_unescape(_element_text(param_node, "value")),
                    "parameterized": param_node.find("parameterized") is not None,
                }
            )
        items.append(
            {
                "kind": "action",
                "id": int(node.get("id", -1)),
                "label": node.get("name") or task.get("name", ""),
                "module": task.get("name", ""),
                "enabled": task.find("disabled") is None,
                "comment": _element_text(node, "comment"),
                "flags": flags,
                "params": params,
                "loop_ids": [],
            }
        )

    for node in root.findall("loop"):
        item_ids = []
        for item_node in node.findall("item"):
            try:
                item_ids.append(int(item_node.text))
            except (TypeError, ValueError):
                pass
        items.append(
            {
                "kind": "loop",
                "id": int(node.get("id", -1)),
                "condition": _legacy_unescape(_element_text(node, "condition")),
                "item_ids": item_ids,
            }
        )

    condition_ids = [int(node.get("id", -1)) for node in root.findall("if-else")]

    # Ids define the execution order of the model (actions, loops, and
    # other items share one id sequence).
    items.sort(key=operator.itemgetter("id"))
    for loop in [item for item in items if item["kind"] == "loop"]:
        for item in items:
            if item["kind"] == "action" and item["id"] in loop["item_ids"]:
                item["loop_ids"].append(loop["id"])

    data = []
    for node in root.findall("data"):
        param = node.find("data-parameter")
        if param is None:
            continue
        data.append(
            {
                "prompt": param.get("prompt", ""),
                "value": _legacy_unescape(_element_text(param, "value")),
                "intermediate": node.find("intermediate") is not None,
            }
        )

    return {
        "properties": properties,
        "variables": variables,
        "items": items,
        "data": data,
        "condition_ids": condition_ids,
    }


def substitute_variables(text, values):
    """Substitute %name and %{name} variable references in text.

    Longer names are substituted first so that a name which is a prefix
    of another name does not break the substitution of the longer name.
    Only non-empty values are substituted (same as the GUI modeler).
    """
    for name in sorted(values, key=len, reverse=True):
        value = values[name]
        if not value:
            continue
        pattern = re.compile(
            r"%(?:\{" + re.escape(name) + r"\}|" + re.escape(name) + r")"
        )
        # Escape backslashes so that re.sub does not interpret them.
        text = pattern.sub(value.replace("\\", r"\\"), text)
    return text


def find_unresolved_variable(text):
    """Get the name of the first unresolved %{name} reference or None.

    Only the curly braces form is detected because a plain % followed by
    text cannot be distinguished from a literal percent sign.
    """
    match = UNRESOLVED_VARIABLE.search(text)
    if match:
        return match.group(1)
    return None


def split_loop_condition(condition):
    """Split a loop condition into the loop variable name and iterable text.

    Raises ModelFileError if the condition does not have the
    "variable in values" form used by the Graphical Modeler.
    """
    parts = re.split(r"\s+in\s+", condition, maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        message = (
            f"invalid loop condition '{condition}' (expected 'variable in values')"
        )
        raise ModelFileError(message)
    return parts[0].strip(), parts[1].strip()


def parse_command_tokens(tokens):
    """Parse command line tokens into module name, flags, and options.

    Used for commands embedded in loop conditions (backticks form).
    Returns (module, short_flags, long_flags, options) where short_flags
    is a string of one-letter flags, long_flags is a list of long flag
    names (e.g., overwrite), and options maps option names to values.
    """
    if not tokens:
        message = "empty command in loop condition"
        raise ModelFileError(message)
    module = tokens[0]
    short_flags = ""
    long_flags = []
    options = {}
    for token in tokens[1:]:
        if token.startswith("--"):
            long_flags.append(token[2:])
        elif token.startswith("-") and "=" not in token:
            short_flags += token[1:]
        elif "=" in token:
            name, value = token.split("=", 1)
            options[name] = value
        else:
            message = f"cannot parse command token '{token}'"
            raise ModelFileError(message)
    return module, short_flags, long_flags, options


# End of the .gxm parser shared with g.model.export.


def model_actions(model):
    """Get all action items of the model in execution order"""
    return [item for item in model["items"] if item["kind"] == "action"]


def resolve_variables(model, overrides_option):
    """Compute effective variable values from defaults and user overrides.

    Returns a name to value mapping. Ends with a fatal error for unknown
    variable names and for variables without any value, matching the GUI
    behavior of requiring a value for every variable before a run.
    """
    values = {name: info["value"] for name, info in model["variables"].items()}
    if overrides_option:
        for entry in overrides_option.split(","):
            if "=" not in entry:
                gs.fatal(
                    _("Invalid variable assignment <{}> (expected name=value)").format(
                        entry
                    )
                )
            name, value = entry.split("=", 1)
            if name not in values:
                gs.fatal(
                    _(
                        "Variable <{name}> is not defined in the model"
                        " (defined variables: {defined})"
                    ).format(name=name, defined=", ".join(values) or _("none"))
                )
            values[name] = value
    missing = [name for name, value in values.items() if not value]
    if missing:
        gs.fatal(
            _(
                "No value set for model variable(s): {names}."
                " Set them with the variables option."
            ).format(names=", ".join(missing))
        )
    return values


def parse_flag_value(value, key):
    """Convert a user-provided flag value to a boolean"""
    lowered = value.lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    gs.fatal(
        _("Invalid value <{value}> for flag <{key}> (use true or false)").format(
            value=value, key=key
        )
    )


def apply_parameter_overrides(model, overrides_option):
    """Apply user values to parameterized options and flags of actions.

    Each override has the form action.option=value where action is the
    numeric action id or the tool name (action label) from the model.
    Ends with a fatal error for unknown actions, ambiguous names, and
    options which are not parameterized in the model.
    """
    if not overrides_option:
        return
    actions = model_actions(model)
    for entry in overrides_option.split(","):
        if "=" not in entry:
            gs.fatal(
                _(
                    "Invalid parameter assignment <{}> (expected action.option=value)"
                ).format(entry)
            )
        key, value = entry.split("=", 1)
        if "." not in key:
            gs.fatal(
                _(
                    "Invalid parameter key <{}> (expected action.option"
                    " with action being an action id or a tool name)"
                ).format(key)
            )
        action_ref, option_name = key.rsplit(".", 1)
        if action_ref.isdigit():
            matched = [item for item in actions if item["id"] == int(action_ref)]
        else:
            matched = [item for item in actions if item["label"] == action_ref]
        if not matched:
            gs.fatal(_("No action <{}> in the model").format(action_ref))
        if len(matched) > 1:
            gs.fatal(
                _(
                    "Action name <{name}> is ambiguous; use one of the"
                    " action ids instead: {ids}"
                ).format(
                    name=action_ref,
                    ids=", ".join(str(item["id"]) for item in matched),
                )
            )
        action = matched[0]
        for flag in action["flags"]:
            if flag["name"] == option_name and flag["parameterized"]:
                flag["enabled"] = parse_flag_value(value, key)
                break
        else:
            for param in action["params"]:
                if param["name"] == option_name and param["parameterized"]:
                    param["value"] = value
                    break
            else:
                gs.fatal(
                    _(
                        "Option <{option}> of action ({id}) {label} is not"
                        " parameterized in the model"
                    ).format(option=option_name, id=action["id"], label=action["label"])
                )


def check_parameterized_values(model):
    """Report parameterized options which are still without a value"""
    missing = []
    for action in model_actions(model):
        if not action["enabled"]:
            continue
        for param in action["params"]:
            if param["parameterized"] and not param["value"]:
                missing.append(
                    "{id}.{option} (({id}) {label})".format(
                        id=action["id"], option=param["name"], label=action["label"]
                    )
                )
    if missing:
        gs.fatal(
            _(
                "No value set for parameterized option(s): {names}."
                " Set them with the parameters option."
            ).format(names=", ".join(missing))
        )


def command_kwargs(item):
    """Convert item flags to grass.script.run_command keyword arguments.

    Returns (short_flags, kwargs) where kwargs holds the long flags
    (overwrite, verbose, quiet) as booleans.
    """
    short_flags = ""
    kwargs = {}
    for flag in item["flags"]:
        if not flag["enabled"]:
            continue
        name = flag["name"]
        if len(name) == 1:
            short_flags += name
        elif name in {"overwrite", "verbose", "quiet", "superquiet"}:
            kwargs[name] = True
        else:
            gs.fatal(
                _("Unsupported flag <{flag}> in action ({id}) {label}").format(
                    flag=name, id=item["id"], label=item["label"]
                )
            )
    return short_flags, kwargs


def run_action(action, variables, env):
    """Run one model action with variables substituted in option values"""
    short_flags, kwargs = command_kwargs(action)
    for param in action["params"]:
        value = substitute_variables(param["value"], variables)
        unresolved = find_unresolved_variable(value)
        if unresolved:
            gs.fatal(
                _(
                    "Undefined variable <{variable}> in option <{option}>"
                    " of action ({id}) {label}"
                ).format(
                    variable=unresolved,
                    option=param["name"],
                    id=action["id"],
                    label=action["label"],
                )
            )
        if value:
            kwargs[param["name"]] = value
    gs.message(
        _("Running ({id}) {label}...").format(id=action["id"], label=action["label"])
    )
    try:
        gs.run_command(action["module"], flags=short_flags, env=env, **kwargs)
    except CalledModuleError:
        gs.fatal(
            _("Action ({id}) {label} failed").format(
                id=action["id"], label=action["label"]
            )
        )


def loop_values(loop, variables, env):
    """Compute the list of values a loop iterates over.

    Supports the two condition forms of the Graphical Modeler: a Python
    list literal and a command in backticks whose output lines are the
    values. Variable references in the condition are substituted first;
    string-typed variable values are quoted so that they form valid
    literals (same as Model.Run in the GUI).
    """
    variable, iterable_text = split_loop_condition(loop["condition"])
    iterable_text = substitute_variables(iterable_text, variables)
    unresolved = find_unresolved_variable(iterable_text)
    if unresolved:
        gs.fatal(
            _("Undefined variable <{variable}> in condition of loop ({id})").format(
                variable=unresolved, id=loop["id"]
            )
        )
    if iterable_text.startswith("`") and iterable_text.endswith("`"):
        module, short_flags, long_flags, options = parse_command_tokens(
            shlex.split(iterable_text[1:-1])
        )
        kwargs = dict.fromkeys(long_flags, True)
        try:
            output = gs.read_command(
                module, flags=short_flags, env=env, **kwargs, **options
            )
        except CalledModuleError:
            gs.fatal(
                _("Command in condition of loop ({id}) failed").format(id=loop["id"])
            )
        return_values = output.splitlines()
    else:
        try:
            literal = ast.literal_eval(iterable_text)
        except (ValueError, SyntaxError):
            gs.fatal(
                _(
                    "Unsupported condition <{condition}> of loop ({id});"
                    " supported forms are a list of values and a command"
                    " in backticks"
                ).format(condition=loop["condition"], id=loop["id"])
            )
        if not isinstance(literal, (list, tuple)):
            gs.fatal(
                _("Condition of loop ({id}) does not evaluate to a list").format(
                    id=loop["id"]
                )
            )
        return_values = [str(value) for value in literal]
    return variable, return_values


def run_loop(loop, model, variables, env):
    """Run all enabled actions of a loop for each loop value"""
    # Quoting of string values applies only to the loop condition;
    # plain values are used for the actions inside the loop.
    loop_variable, values = loop_values(
        loop, quoted_condition_variables(model, variables), env
    )
    actions = [
        item
        for item in model_actions(model)
        if loop["id"] in item["loop_ids"] and item["enabled"]
    ]
    for value in values:
        iteration_variables = dict(variables)
        iteration_variables[loop_variable] = value
        for action in actions:
            run_action(action, iteration_variables, env)


def quoted_condition_variables(model, variables):
    """Get variable values with string-typed values quoted for conditions"""
    values = {}
    for name, value in variables.items():
        variable_type = model["variables"].get(name, {}).get("type", "string")
        if variable_type == "string":
            value = '"' + value + '"'
        values[name] = value
    return values


def remove_intermediate_data(model, variables, env):
    """Remove data items marked as intermediate in the model"""
    by_type = {"raster": [], "vector": [], "raster_3d": []}
    for data in model["data"]:
        if not data["intermediate"]:
            continue
        if data["prompt"] not in by_type:
            gs.warning(
                _(
                    "Not removing intermediate data <{value}>"
                    " of unsupported type <{type}>"
                ).format(value=data["value"], type=data["prompt"])
            )
            continue
        name = substitute_variables(data["value"], variables)
        if find_unresolved_variable(name):
            gs.warning(
                _(
                    "Not removing intermediate data <{}> because its name"
                    " contains an unresolved variable"
                ).format(data["value"])
            )
            continue
        by_type[data["prompt"]].append(name)
    for element, names in by_type.items():
        if names:
            gs.run_command(
                "g.remove", flags="f", type=element, name=",".join(names), env=env
            )


def main():
    options, flags = gs.parser()
    try:
        model = parse_gxm(options["input"])
    except ModelFileError as error:
        gs.fatal(
            _("Unable to load model file <{name}>: {error}").format(
                name=options["input"], error=error
            )
        )

    if model["condition_ids"]:
        gs.fatal(
            _(
                "The model contains if-else condition item(s) (id(s): {ids})"
                " which are not supported by this tool"
            ).format(ids=", ".join(str(i) for i in model["condition_ids"]))
        )
    for action in model_actions(model):
        if len(action["loop_ids"]) > 1:
            gs.fatal(
                _(
                    "Action ({id}) {label} belongs to more than one loop;"
                    " nested loops are not supported"
                ).format(id=action["id"], label=action["label"])
            )

    variables = resolve_variables(model, options["variables"])
    apply_parameter_overrides(model, options["parameters"])
    check_parameterized_values(model)

    env = os.environ.copy()
    if model["properties"]["overwrite"]:
        env["GRASS_OVERWRITE"] = "1"

    for item in model["items"]:
        if item["kind"] == "action":
            if item["loop_ids"] or not item["enabled"]:
                continue
            run_action(item, variables, env)
        elif item["kind"] == "loop":
            run_loop(item, model, variables, env)

    if not flags["i"]:
        remove_intermediate_data(model, variables, env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
