#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       g.model.export
# AUTHOR(S):    Vaclav Petras (with substantial AI assistance)
#               Based on gui/wxpython/gmodeler by Martin Landa and
#               Ondrej Pesek
# PURPOSE:      Convert a Graphical Modeler model file (.gxm) to a script
# COPYRIGHT:    (C) 2026 by the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Converts a model prepared in the wxGUI Graphical Modeler to a script.
# % keyword: general
# % keyword: modeler
# % keyword: model
# % keyword: workflow
# %end
# %option G_OPT_F_INPUT
# % description: Name of model file (.gxm) to convert
# %end
# %option G_OPT_F_OUTPUT
# % description: Name for the generated file
# %end
# %option
# % key: format
# % type: string
# % required: yes
# % options: python,pywps,actinia
# % answer: python
# % descriptions: python;Python script;pywps;PyWPS process (Python);actinia;actinia process chain (JSON)
# % description: Format of the generated file
# %end

import ast
import json
import operator
import pathlib
import re
import shlex
import stat
import sys
import time
import xml.etree.ElementTree as ET

import grass.script as gs
from grass.exceptions import CalledModuleError, ScriptError
from grass.script import task as gtask

# Begin of the .gxm parser shared with g.model.run. This copy extends the
# shared parser with if-else condition parsing; when porting to the main
# source tree, unify the copies and move the parser to a Python library
# (e.g., a new grass.models package) so that the GUI modeler can use it as
# well.

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
    - items: actions, loops, and if-else conditions ordered by item id,
      distinguished by "kind"; an action has id, label, module, enabled,
      comment, flags (each with name, enabled, parameterized), params (each
      with name, value, parameterized), loop_ids (ids of loops it belongs
      to), and condition_ids (ids of if-else conditions it belongs to); a
      loop has id, condition, and item_ids; a condition has id, condition,
      if_ids, and else_ids

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
                "condition_ids": [],
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

    for node in root.findall("if-else"):
        branches = {"if": [], "else": []}
        for branch, ids in branches.items():
            branch_node = node.find(branch)
            if branch_node is None:
                continue
            for item_node in branch_node.findall("item"):
                try:
                    ids.append(int(item_node.text))
                except (TypeError, ValueError):
                    pass
        items.append(
            {
                "kind": "condition",
                "id": int(node.get("id", -1)),
                "condition": _legacy_unescape(_element_text(node, "condition")),
                "if_ids": branches["if"],
                "else_ids": branches["else"],
            }
        )

    # Ids define the execution order of the model (actions, loops, and
    # other items share one id sequence).
    items.sort(key=operator.itemgetter("id"))
    for loop in [item for item in items if item["kind"] == "loop"]:
        for item in items:
            if item["kind"] == "action" and item["id"] in loop["item_ids"]:
                item["loop_ids"].append(loop["id"])
    for condition in [item for item in items if item["kind"] == "condition"]:
        for item in items:
            if item["kind"] != "action":
                continue
            for branch_ids in (condition["if_ids"], condition["else_ids"]):
                if item["id"] in branch_ids:
                    item["condition_ids"].append(condition["id"])

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


# End of the .gxm parser shared with g.model.run.

# Mapping of Graphical Modeler variable types to standard parser options,
# following ModelToPython._getStandardizedOption.
STANDARD_OPTIONS = {
    "raster": "G_OPT_R_MAP",
    "vector": "G_OPT_V_MAP",
    "mapset": "G_OPT_M_MAPSET",
    "file": "G_OPT_F_INPUT",
    "dir": "G_OPT_M_DIR",
    "region": "G_OPT_M_REGION",
}

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class PythonReferences:
    """Code expressions referencing generated-script options (python format)"""

    @staticmethod
    def value(name):
        """Expression for a value which is exactly one reference"""
        return 'options["{}"]'.format(name)

    @staticmethod
    def fstring_piece(name):
        """Expression for a reference inside an f-string"""
        return "{options['" + name + "']}"

    @staticmethod
    def parameterized(key, _param_name):
        """Expression for the value of a parameterized option"""
        return 'options["{}"]'.format(key)

    flags_call = "get_parameterized_flags(options, [{}])"


class PyWPSReferences:
    """Code expressions referencing PyWPS request inputs (pywps format)"""

    @staticmethod
    def value(name):
        """Expression for a value which is exactly one reference"""
        return 'request.inputs["{}"][0].data'.format(name)

    @staticmethod
    def fstring_piece(name):
        """Expression for a reference inside an f-string"""
        return "{request.inputs['" + name + "'][0].data}"

    @staticmethod
    def parameterized(key, param_name):
        """Expression for the value of a parameterized option.

        Options with "input" in their name are ComplexInputs, so the
        received file is referenced instead of the literal data (same
        distinction as in the GUI PyWPS export).
        """
        attribute = "file" if "input" in param_name else "data"
        return 'request.inputs["{}"][0].{}'.format(key, attribute)

    flags_call = "get_parameterized_flags(request.inputs, [{}])"


def model_actions(model):
    """Get all action items of the model in execution order"""
    return [item for item in model["items"] if item["kind"] == "action"]


def action_nickname(action):
    """Get a unique short name of an action used in generated option keys.

    Follows BaseModelConverter._getModuleNickname (letters of the action
    label plus the action id).
    """
    return re.sub(r"[^a-zA-Z]+", "", action["label"]) + str(action["id"])


def option_key(action, name):
    """Get the generated script option key for a parameterized option"""
    return "{}_{}".format(action_nickname(action), name)


def get_interface(module, cache):
    """Get the parsed interface description of a tool (cached)"""
    if module not in cache:
        try:
            cache[module] = gtask.parse_interface(module)
        except (ScriptError, CalledModuleError, OSError) as error:
            gs.fatal(
                _("Unable to get the interface of <{module}>: {error}").format(
                    module=module, error=error
                )
            )
    return cache[module]


def string_literal(value):
    """Get a double-quoted Python string literal for a value"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def is_number(value):
    """Check whether a value is a valid Python number literal"""
    try:
        float(value)
    except ValueError:
        return False
    return True


def split_references(value, names):
    """Split text into literal parts and variable references.

    Returns a list of ("text", part) and ("ref", name) tuples in the
    original order. Longer names are matched first so that a name which
    is a prefix of another name does not shadow the longer name.
    """
    if not names:
        return [("text", value)]
    alternatives = []
    for name in sorted(names, key=len, reverse=True):
        escaped = re.escape(name)
        alternatives.extend((r"%\{" + escaped + r"\}", "%" + escaped))
    pattern = re.compile("|".join(alternatives))
    parts = []
    position = 0
    for match in pattern.finditer(value):
        if match.start() > position:
            parts.append(("text", value[position : match.start()]))
        parts.append(("ref", match.group().lstrip("%").strip("{}")))
        position = match.end()
    if position < len(value) or not parts:
        parts.append(("text", value[position:]))
    return parts


def reference_code(name, loop_variable, refs):
    """Get the Python expression for a variable reference"""
    if name == loop_variable:
        return name
    return refs.value(name)


def value_expression(value, iface_param, variable_names, loop_variable, refs):
    """Get the Python expression for an option value, or None to omit it.

    Model variable references become lookups in the refs style, loop
    variable references become the loop variable, and values mixing
    references with text become f-strings.
    """
    names = list(variable_names)
    if loop_variable:
        names.append(loop_variable)
    parts = split_references(value, names)
    references = [part for kind, part in parts if kind == "ref"]
    if not references:
        if not value:
            return None
        if iface_param.get("type") in {"integer", "float"} and is_number(value):
            return value
        return string_literal(value)
    if len(parts) == 1:
        return reference_code(references[0], loop_variable, refs)
    pieces = []
    for kind, part in parts:
        if kind == "text":
            pieces.append(
                part.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("{", "{{")
                .replace("}", "}}")
            )
        elif part == loop_variable:
            pieces.append("{" + part + "}")
        else:
            pieces.append(refs.fstring_piece(part))
    return 'f"' + "".join(pieces) + '"'


def action_arguments(action, iface, variable_names, loop_variable, refs):
    """Build run_command argument strings for one action.

    Returns the list of argument code strings; the flags argument for
    parameterized flags references the get_parameterized_flags helper.
    """
    short_flags = ""
    long_flag_args = []
    parameterized_flag_keys = []
    for flag in action["flags"]:
        name = flag["name"]
        if flag["parameterized"]:
            if len(name) == 1:
                parameterized_flag_keys.append(string_literal(option_key(action, name)))
                continue
            gs.warning(
                _(
                    "Parameterized flag <{flag}> of action ({id}) {label}"
                    " is exported as a fixed flag (parameterized long flags"
                    " are not supported)"
                ).format(flag=name, id=action["id"], label=action["label"])
            )
        if not flag["enabled"]:
            continue
        if len(name) == 1:
            short_flags += name
        else:
            long_flag_args.append("{}=True".format(name))

    arguments = []
    flags_call = refs.flags_call.format(", ".join(parameterized_flag_keys))
    if short_flags and parameterized_flag_keys:
        arguments.append('flags="{}" + {}'.format(short_flags, flags_call))
    elif short_flags:
        arguments.append('flags="{}"'.format(short_flags))
    elif parameterized_flag_keys:
        arguments.append("flags={}".format(flags_call))
    arguments.extend(long_flag_args)

    known_names = list(variable_names) + ([loop_variable] if loop_variable else [])
    for param in action["params"]:
        if param["parameterized"]:
            expression = refs.parameterized(
                option_key(action, param["name"]), param["name"]
            )
        else:
            for kind, part in split_references(param["value"], known_names):
                unresolved = find_unresolved_variable(part) if kind == "text" else None
                if unresolved:
                    gs.fatal(
                        _(
                            "Undefined variable <{variable}> in option"
                            " <{option}> of action ({id}) {label}"
                        ).format(
                            variable=unresolved,
                            option=param["name"],
                            id=action["id"],
                            label=action["label"],
                        )
                    )
            expression = value_expression(
                param["value"],
                iface.get_param(param["name"], raiseError=False) or {},
                variable_names,
                loop_variable,
                refs,
            )
        if expression is not None:
            arguments.append("{}={}".format(param["name"], expression))
    return arguments


def render_call(function, module, arguments, indent):
    """Render a function call over multiple lines like ModelToPython does"""
    head = "{}{}(".format(" " * indent, function)
    continuation = " " * len(head)
    tokens = [string_literal(module)] + arguments
    lines = []
    for position, token in enumerate(tokens):
        prefix = head if position == 0 else continuation
        suffix = ")" if position == len(tokens) - 1 else ","
        lines.append(prefix + token + suffix)
    return lines


def action_lines(action, iface, variable_names, indent, refs, loop_variable=None):
    """Generate the code lines for one action.

    Disabled actions are included as commented-out code so that the
    generated script documents the whole model.
    """
    lines = render_call(
        "run_command",
        action["module"],
        action_arguments(action, iface, variable_names, loop_variable, refs),
        indent,
    )
    if not action["enabled"]:
        note = "{}# Action ({}) {} is disabled in the model:".format(
            " " * indent, action["id"], action["label"]
        )
        lines = [note] + [" " * indent + "# " + line[indent:] for line in lines]
    return lines


def loop_reference_check(loop, variable_names):
    """Refuse model variable references in loop conditions.

    The GUI substitutes the variable defaults into the condition text at
    export time which produces a script that ignores the corresponding
    script option; refusing is more predictable.
    """
    _, iterable_text = split_loop_condition(loop["condition"])
    parts = split_references(iterable_text, variable_names)
    refs = [part for kind, part in parts if kind == "ref"]
    if refs or find_unresolved_variable(iterable_text):
        gs.fatal(
            _(
                "Condition of loop ({id}) references a variable;"
                " this is not supported by the Python export"
            ).format(id=loop["id"])
        )


def loop_lines(loop, model, interfaces, variable_names, refs, indent):
    """Generate the code lines for one loop and its actions.

    Returns (lines, uses_read_command) where uses_read_command tells the
    caller whether the generated code calls read_command.
    """
    variable, iterable_text = split_loop_condition(loop["condition"])
    if not IDENTIFIER.fullmatch(variable):
        gs.fatal(
            _(
                "Loop variable <{variable}> of loop ({id}) is not usable"
                " as a Python variable name"
            ).format(variable=variable, id=loop["id"])
        )
    loop_reference_check(loop, variable_names)
    uses_read_command = False
    if iterable_text.startswith("`") and iterable_text.endswith("`"):
        module, short_flags, long_flags, options = parse_command_tokens(
            shlex.split(iterable_text[1:-1])
        )
        arguments = []
        if short_flags:
            arguments.append('flags="{}"'.format(short_flags))
        arguments.extend("{}=True".format(name) for name in long_flags)
        arguments.extend(
            "{}={}".format(name, string_literal(value))
            for name, value in options.items()
        )
        iterable_code = "read_command({}).splitlines()".format(
            ", ".join([string_literal(module)] + arguments)
        )
        uses_read_command = True
    else:
        try:
            literal = ast.literal_eval(iterable_text)
        except (ValueError, SyntaxError):
            literal = None
        if not isinstance(literal, (list, tuple)):
            gs.fatal(
                _(
                    "Unsupported condition <{condition}> of loop ({id});"
                    " supported forms are a list of values and a command"
                    " in backticks"
                ).format(condition=loop["condition"], id=loop["id"])
            )
        iterable_code = iterable_text
    lines = ["{}for {} in {}:".format(" " * indent, variable, iterable_code)]
    has_enabled_action = False
    for action in model_actions(model):
        if loop["id"] not in action["loop_ids"]:
            continue
        iface = get_interface(action["module"], interfaces)
        lines.extend(
            action_lines(
                action, iface, variable_names, indent + 4, refs, loop_variable=variable
            )
        )
        lines.append("")
        has_enabled_action = has_enabled_action or action["enabled"]
    if lines[-1] == "":
        lines.pop()
    if not has_enabled_action:
        # Only comments (or nothing) in the loop body would be a syntax error.
        lines.append("{}pass".format(" " * (indent + 4)))
    return lines, uses_read_command


def condition_expression(condition, model, refs):
    """Translate an if-else condition into a Python expression.

    Model variable references become option lookups converted to the
    variable's type. The GUI export substitutes the variable default
    values as literals instead, which ignores the values given to the
    generated interface at run time.
    """
    variables = model["variables"]
    pieces = []
    for kind, part in split_references(condition["condition"], list(variables)):
        if kind == "text":
            unresolved = find_unresolved_variable(part)
            if unresolved:
                gs.fatal(
                    _(
                        "Undefined variable <{variable}> in the condition"
                        " of if-else ({id})"
                    ).format(variable=unresolved, id=condition["id"])
                )
            pieces.append(part)
            continue
        code = refs.value(part)
        variable_type = variables[part]["type"]
        if variable_type == "integer":
            code = "int({})".format(code)
        elif variable_type == "float":
            code = "float({})".format(code)
        pieces.append(code)
    expression = "".join(pieces).strip()
    try:
        compile(expression, "<condition>", "eval")
    except SyntaxError:
        gs.fatal(
            _(
                "Condition <{condition}> of if-else ({id}) is not a valid"
                " Python expression"
            ).format(condition=condition["condition"], id=condition["id"])
        )
    return expression


def condition_lines(condition, model, interfaces, variable_names, refs, indent):
    """Generate the code lines for one if-else condition and its actions"""
    lines = [
        "{}if {}:".format(" " * indent, condition_expression(condition, model, refs))
    ]
    for keyword, branch_ids in (
        ("if", condition["if_ids"]),
        ("else", condition["else_ids"]),
    ):
        branch = []
        has_enabled_action = False
        for action in model_actions(model):
            if action["id"] not in branch_ids:
                continue
            iface = get_interface(action["module"], interfaces)
            branch.extend(action_lines(action, iface, variable_names, indent + 4, refs))
            branch.append("")
            has_enabled_action = has_enabled_action or action["enabled"]
        if branch and branch[-1] == "":
            branch.pop()
        if keyword == "else" and not branch:
            continue
        if not has_enabled_action:
            # Only comments (or nothing) in the branch would be a syntax error.
            branch.append("{}pass".format(" " * (indent + 4)))
        if keyword == "else":
            lines.append("{}else:".format(" " * indent))
        lines.extend(branch)
    return lines


def header_lines(model):
    """Generate the script header comment and the parser interface"""
    properties = model["properties"]
    description = properties["description"] or "Script generated from a model."
    return [
        "#!/usr/bin/env python3",
        "#",
        "#" * 77,
        "#",
        "# MODULE:       {}".format(properties["name"] or "model"),
        "#",
        "# AUTHOR(S):    {}".format(properties["author"]),
        "#",
        "# PURPOSE:      {}".format(description),
        "#",
        "# DATE:         {}".format(time.asctime()),
        "#",
        "#" * 77,
        "",
        "# %module",
        "# % description: {}".format(description),
        "# %end",
    ]


def flag_description(iface, action, name):
    """Get the description of a flag from the tool interface"""
    try:
        info = iface.get_flag(name)
    except ValueError:
        info = {}
    return (
        info.get("label")
        or info.get("description")
        or "Flag {} of {}".format(name, action["module"])
    )


def param_description(info, action, name):
    """Get the description of an option from its interface entry"""
    return (
        info.get("label")
        or info.get("description")
        or "Option {} of {}".format(name, action["module"])
    )


def parameterized_option_lines(model, interfaces):
    """Generate parser option definitions for parameterized options"""
    lines = []
    for action in model_actions(model):
        if not action["enabled"]:
            continue
        iface = None
        for flag in action["flags"]:
            if not flag["parameterized"] or len(flag["name"]) != 1:
                continue
            iface = iface or get_interface(action["module"], interfaces)
            description = flag_description(iface, action, flag["name"])
            lines.extend(
                [
                    "# %option",
                    "# % key: {}".format(option_key(action, flag["name"])),
                    "# % description: {}".format(description),
                    "# % required: yes",
                    "# % type: string",
                    "# % options: True,False",
                    "# % answer: {}".format("True" if flag["enabled"] else "False"),
                    "# %end",
                ]
            )
        for param in action["params"]:
            if not param["parameterized"]:
                continue
            iface = iface or get_interface(action["module"], interfaces)
            info = iface.get_param(param["name"], raiseError=False) or {}
            description = param_description(info, action, param["name"])
            option_type = info.get("type", "string")
            if option_type == "float":
                option_type = "double"
            lines.extend(
                [
                    "# %option",
                    "# % key: {}".format(option_key(action, param["name"])),
                    "# % description: {}".format(description),
                    "# % required: yes",
                    "# % type: {}".format(option_type),
                ]
            )
            if info.get("key_desc"):
                lines.append("# % key_desc: {}".format(",".join(info["key_desc"])))
            if param["value"]:
                lines.append("# % answer: {}".format(param["value"]))
            lines.append("# %end")
    return lines


def variable_option_lines(model):
    """Generate parser option definitions for model variables"""
    lines = []
    for name, info in model["variables"].items():
        standard = STANDARD_OPTIONS.get(info["type"])
        lines.extend(
            (
                "# %option {}".format(standard) if standard else "# %option",
                "# % key: {}".format(name),
            )
        )
        if info["description"]:
            lines.append("# % description: {}".format(info["description"]))
        lines.append("# % required: yes")
        if not standard:
            option_type = info["type"]
            if option_type == "float":
                option_type = "double"
            lines.append("# % type: {}".format(option_type))
        if info["value"]:
            lines.append("# % answer: {}".format(info["value"]))
        lines.append("# %end")
    return lines


def cleanup_lines(model, variable_names):
    """Generate the cleanup function removing intermediate data"""
    lines = ["def cleanup():"]
    by_type = {"raster": [], "vector": [], "raster_3d": []}
    for data in model["data"]:
        if not data["intermediate"]:
            continue
        if data["prompt"] not in by_type or split_references(
            data["value"], variable_names
        ) != [("text", data["value"])]:
            lines.append(
                "    # Remove intermediate data <{}> ({}) manually.".format(
                    data["value"], data["prompt"]
                )
            )
            continue
        by_type[data["prompt"]].append(data["value"])
    body = []
    for element, names in by_type.items():
        if names:
            body.extend(
                render_call(
                    "run_command",
                    "g.remove",
                    [
                        'flags="f"',
                        'type="{}"'.format(element),
                        'name="{}"'.format(",".join(names)),
                    ],
                    4,
                )
            )
    lines.extend(body)
    if not body:
        lines.append("    pass")
    return lines


def body_lines(model, interfaces, variable_names, refs, indent, action_extra=None):
    """Generate the code lines for all model items in execution order.

    Returns (lines, uses_read_command). When given, action_extra is
    called as action_extra(action, indent) after each enabled action
    outside of loops and conditions to add follow-up code lines (used
    for the PyWPS output exports).
    """
    lines = []
    uses_read_command = False
    for item in model["items"]:
        if item["kind"] == "action":
            if item["loop_ids"] or item["condition_ids"]:
                continue
            iface = get_interface(item["module"], interfaces)
            lines.extend(action_lines(item, iface, variable_names, indent, refs))
            if action_extra and item["enabled"]:
                lines.extend(action_extra(item, indent))
            lines.append("")
        elif item["kind"] == "loop":
            loop_code, reads = loop_lines(
                item, model, interfaces, variable_names, refs, indent
            )
            uses_read_command = uses_read_command or reads
            lines.extend(loop_code)
            lines.append("")
        elif item["kind"] == "condition":
            lines.extend(
                condition_lines(item, model, interfaces, variable_names, refs, indent)
            )
            lines.append("")
    return lines, uses_read_command


def generate_python(model):
    """Generate the Python script text for a model"""
    interfaces = {}
    variable_names = list(model["variables"])
    parameterized_flags_used = any(
        flag["parameterized"] and len(flag["name"]) == 1
        for action in model_actions(model)
        if action["enabled"]
        for flag in action["flags"]
    )

    body, uses_read_command = body_lines(
        model, interfaces, variable_names, PythonReferences, 4
    )
    body.append("    return 0")

    lines = header_lines(model)
    lines.extend(parameterized_option_lines(model, interfaces))
    lines.extend(variable_option_lines(model))
    lines.append("")
    lines.append("import atexit")
    if model["properties"]["overwrite"]:
        lines.append("import os")
    lines.append("import sys")
    lines.append("")
    imported = ["parser", "run_command"]
    if uses_read_command:
        imported.insert(1, "read_command")
    lines.append("from grass.script import {}".format(", ".join(imported)))
    lines.extend(["", ""])
    lines.extend(cleanup_lines(model, variable_names))
    lines.extend(["", ""])
    lines.append("def main(options, flags):")
    lines.extend(body)
    if parameterized_flags_used:
        lines.extend(
            [
                "",
                "",
                "def get_parameterized_flags(options, keys):",
                '    """Collect enabled parameterized flag letters"""',
                '    flags = ""',
                "    for key in keys:",
                '        if options[key] == "True":',
                '            flags += key.rsplit("_", 1)[1]',
                "    return flags",
            ]
        )
    lines.extend(
        [
            "",
            "",
            'if __name__ == "__main__":',
            "    options, flags = parser()",
            "    atexit.register(cleanup)",
        ]
    )
    if model["properties"]["overwrite"]:
        lines.append('    os.environ["GRASS_OVERWRITE"] = "1"')
    lines.append("    sys.exit(main(options, flags))")
    return "\n".join(lines) + "\n"


# Export commands for PyWPS process outputs by data type prompt
# (command, format option value, file extension), as in the GUI export.
PYWPS_EXPORTS = {
    "raster": ("r.out.gdal", "GTiff", ".tif"),
    "vector": ("v.out.ogr", "GML", ".gml"),
}


def pywps_format_expression(prompt):
    """Get the pywps Format() expression for a data type prompt, or None"""
    if prompt == "raster":
        return 'Format("image/tif")'
    if prompt == "vector":
        return 'Format("application/gml+xml")'
    return None


def pywps_default(value, option_type):
    """Get the Python literal for a PyWPS input default value"""
    if option_type in {"integer", "float"} and is_number(value):
        return value
    return string_literal(value)


def pywps_io_lines(collection, object_type, identifier, title, spec):
    """Generate one inputs/outputs append statement of the PyWPS process"""
    lines = [
        "        {}.append({}(".format(collection, object_type),
        "            identifier={},".format(string_literal(identifier)),
        "            title={},".format(string_literal(title)),
    ]
    for position, entry in enumerate(spec):
        suffix = "))" if position == len(spec) - 1 else ","
        lines.append("            " + entry + suffix)
    lines.append("")
    return lines


def generate_pywps(model):
    """Generate the PyWPS process script text for a model.

    The generated script has the same structure as the PyWPS export of
    the GUI Graphical Modeler (a Process subclass with parameterized
    options as inputs, new non-intermediate data as ComplexOutputs
    exported by r.out.gdal/v.out.ogr, and a static handler running the
    actions), with the deviations documented in the tool manual.
    """
    interfaces = {}
    variables = model["variables"]
    variable_names = list(variables)
    properties = model["properties"]
    intermediate_values = {
        data["value"] for data in model["data"] if data["intermediate"]
    }

    input_lines = []
    output_lines = []
    # Action id to list of (option key, param, interface entry) to export.
    exports = {}
    parameterized_flags_used = False

    for name, info in variables.items():
        data_type = info["type"] if info["type"] in {"integer", "float"} else "string"
        spec = ['data_type="{}"'.format(data_type)]
        if info["value"]:
            spec.append("default={}".format(pywps_default(info["value"], data_type)))
        input_lines.extend(
            pywps_io_lines(
                "inputs", "LiteralInput", name, info["description"] or name, spec
            )
        )

    for action in model_actions(model):
        if not action["enabled"]:
            continue
        iface = get_interface(action["module"], interfaces)
        for flag in action["flags"]:
            if not flag["parameterized"] or len(flag["name"]) != 1:
                continue
            parameterized_flags_used = True
            spec = [
                'data_type="string"',
                'default="{}"'.format("True" if flag["enabled"] else "False"),
            ]
            input_lines.extend(
                pywps_io_lines(
                    "inputs",
                    "LiteralInput",
                    option_key(action, flag["name"]),
                    flag_description(iface, action, flag["name"]),
                    spec,
                )
            )
        for param in action["params"]:
            info = iface.get_param(param["name"], raiseError=False) or {}
            key = option_key(action, param["name"])
            description = param_description(info, action, param["name"])
            format_expression = pywps_format_expression(info.get("prompt"))
            if param["parameterized"]:
                if "input" in param["name"] and format_expression:
                    object_type = "ComplexInput"
                    spec = ["supported_formats=[{}]".format(format_expression)]
                else:
                    object_type = "LiteralInput"
                    spec = ['data_type="{}"'.format(info.get("type", "string"))]
                if param["value"] and "output" not in param["name"]:
                    spec.append(
                        "default={}".format(
                            pywps_default(param["value"], info.get("type", "string"))
                        )
                    )
                input_lines.extend(
                    pywps_io_lines("inputs", object_type, key, description, spec)
                )
            if info.get("age") != "new":
                continue
            if not param["value"] and not param["parameterized"]:
                continue
            if param["value"] in intermediate_values:
                continue
            if action["loop_ids"] or action["condition_ids"]:
                gs.warning(
                    _(
                        "Output <{option}> of action ({id}) {label} inside a"
                        " loop or if-else condition is not exposed as a"
                        " process output"
                    ).format(
                        option=param["name"], id=action["id"], label=action["label"]
                    )
                )
                continue
            if not format_expression:
                gs.warning(
                    _(
                        "Output <{option}> of action ({id}) {label} is not"
                        " exposed as a process output (data type <{prompt}>"
                        " is not supported)"
                    ).format(
                        option=param["name"],
                        id=action["id"],
                        label=action["label"],
                        prompt=info.get("prompt", ""),
                    )
                )
                continue
            output_lines.extend(
                pywps_io_lines(
                    "outputs",
                    "ComplexOutput",
                    key,
                    description,
                    ["supported_formats=[{}]".format(format_expression)],
                )
            )
            exports.setdefault(action["id"], []).append((key, param, info))

    def action_extra(action, indent):
        """Generate the output export code following one action"""
        lines = []
        for key, param, info in exports.get(action["id"], []):
            command, format_name, extension = PYWPS_EXPORTS[info["prompt"]]
            if param["parameterized"]:
                expression = PyWPSReferences.parameterized(key, param["name"])
            else:
                expression = value_expression(
                    param["value"], info, variable_names, None, PyWPSReferences
                )
            path = 'os.path.join(tempfile.gettempdir(), {} + "{}")'.format(
                expression, extension
            )
            arguments = [
                "input={}".format(expression),
                "output={}".format(path),
                'format="{}"'.format(format_name),
            ]
            if properties["overwrite"]:
                arguments.append("overwrite=True")
            lines.extend(render_call("run_command", command, arguments, indent))
            lines.append(
                '{}response.outputs["{}"].file = {}'.format(" " * indent, key, path)
            )
        return lines

    body, uses_read_command = body_lines(
        model, interfaces, variable_names, PyWPSReferences, 8, action_extra
    )
    name_literal = string_literal(properties["name"] or "model")

    lines = ["#!/usr/bin/env python3", ""]
    if exports:
        lines.extend(["import os", "import tempfile", ""])
    imported = ["run_command"]
    if uses_read_command:
        imported.insert(0, "read_command")
    lines.extend(
        [
            "from grass.script import {}".format(", ".join(imported)),
            "from pywps import Process, LiteralInput, ComplexInput, ComplexOutput, Format",
            "",
            "",
            "class Model(Process):",
            "    def __init__(self):",
            "        inputs = []",
            "        outputs = []",
            "",
        ]
    )
    lines.extend(input_lines)
    lines.extend(output_lines)
    lines.extend(
        [
            "        super(Model, self).__init__(",
            "            self._handler,",
            "            identifier={},".format(name_literal),
            "            title={},".format(name_literal),
            "            inputs=inputs,",
            "            outputs=outputs,",
            "            # here you could also specify the GRASS location, for example:",
            '            # grass_location="EPSG:5514",',
            "            abstract={},".format(
                string_literal(properties["description"])
            ),
            '            version="1.0",',
            "            store_supported=True,",
            "            status_supported=True)",
            "",
            "    @staticmethod",
            "    def _handler(request, response):",
        ]
    )
    lines.extend(body)
    lines.append("        return response")
    if parameterized_flags_used:
        lines.extend(
            [
                "",
                "",
                "def get_parameterized_flags(inputs, keys):",
                '    """Collect enabled parameterized flag letters"""',
                '    flags = ""',
                "    for key in keys:",
                '        if inputs[key][0].data == "True":',
                '            flags += key.rsplit("_", 1)[1]',
                "    return flags",
            ]
        )
    lines.extend(
        [
            "",
            "",
            'if __name__ == "__main__":',
            "    from pywps.app.Service import Service",
            "",
            "    processes = [Model()]",
            "    application = Service(processes)",
        ]
    )
    return "\n".join(lines) + "\n"


def jinja_default_literal(value):
    """Get the Jinja literal for a placeholder default value.

    The GUI actinia export writes the default unquoted, which Jinja
    evaluates as an undefined name for textual values; quoting makes it
    a string literal.
    """
    if is_number(value):
        return value
    return '"{}"'.format(value.replace('"', '\\"'))


def actinia_placeholder(name, default):
    """Get the Jinja placeholder for a templated actinia value"""
    if default:
        return "{{{{ {}|default({}) }}}}".format(name, jinja_default_literal(default))
    return "{{{{ {} }}}}".format(name)


def generate_actinia(model):
    """Generate the actinia process chain JSON text for a model.

    The generated JSON has the same structure as the actinia export of
    the GUI Graphical Modeler (a process chain with parameterized
    options as Jinja placeholders, wrapped in a template when
    placeholders are present), with the deviations documented in the
    tool manual.
    """
    interfaces = {}
    variables = model["variables"]
    for item in model["items"]:
        if item["kind"] == "loop":
            gs.fatal(
                _("Loop ({id}) cannot be exported to the actinia format").format(
                    id=item["id"]
                )
            )
        if item["kind"] == "condition":
            gs.fatal(
                _(
                    "If-else condition ({id}) cannot be exported to the actinia format"
                ).format(id=item["id"])
            )

    process_list = []
    templated = False
    for action in model_actions(model):
        if not action["enabled"]:
            gs.warning(
                _(
                    "Disabled action ({id}) {label} is not included in the"
                    " actinia process chain"
                ).format(id=action["id"], label=action["label"])
            )
            continue
        iface = get_interface(action["module"], interfaces)
        flags = ""
        for flag in action["flags"]:
            if flag["parameterized"]:
                gs.warning(
                    _(
                        "Parameterized flag <{flag}> of action ({id}) {label}"
                        " is exported with its current state (actinia does"
                        " not support parameterized flags)"
                    ).format(flag=flag["name"], id=action["id"], label=action["label"])
                )
            if not flag["enabled"]:
                continue
            if len(flag["name"]) == 1:
                flags += flag["name"]
            else:
                gs.warning(
                    _(
                        "Flag <{flag}> of action ({id}) {label} has no"
                        " actinia equivalent and is skipped"
                    ).format(flag=flag["name"], id=action["id"], label=action["label"])
                )
        entry = {"module": action["module"], "id": action_nickname(action)}
        if flags:
            entry["flags"] = flags
        inputs = []
        outputs = []
        for param in action["params"]:
            if param["parameterized"]:
                templated = True
                value = actinia_placeholder(
                    option_key(action, param["name"]), param["value"]
                )
            elif param["value"]:
                pieces = []
                for kind, part in split_references(param["value"], list(variables)):
                    if kind == "text":
                        unresolved = find_unresolved_variable(part)
                        if unresolved:
                            gs.fatal(
                                _(
                                    "Undefined variable <{variable}> in option"
                                    " <{option}> of action ({id}) {label}"
                                ).format(
                                    variable=unresolved,
                                    option=param["name"],
                                    id=action["id"],
                                    label=action["label"],
                                )
                            )
                        pieces.append(part)
                    else:
                        templated = True
                        pieces.append(
                            actinia_placeholder(part, variables[part]["value"])
                        )
                value = "".join(pieces)
            else:
                continue
            info = iface.get_param(param["name"], raiseError=False) or {}
            record = {"param": param["name"], "value": value}
            if info.get("age") == "new":
                outputs.append(record)
            else:
                inputs.append(record)
        if inputs:
            entry["inputs"] = inputs
        if outputs:
            entry["outputs"] = outputs
        process_list.append(entry)

    chain = {
        "id": "model",
        "description": model["properties"]["description"],
        "version": "1",
    }
    if templated:
        chain["template"] = {"list": process_list}
    else:
        chain["list"] = process_list
    return json.dumps(chain, indent=2) + "\n"


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

    for action in model_actions(model):
        if len(action["loop_ids"]) + len(action["condition_ids"]) > 1:
            gs.fatal(
                _(
                    "Action ({id}) {label} belongs to more than one loop or"
                    " if-else condition; nested blocks are not supported"
                ).format(id=action["id"], label=action["label"])
            )

    output = pathlib.Path(options["output"])
    if output.exists() and not gs.overwrite():
        gs.fatal(
            _("File <{}> already exists. Use --overwrite to replace it.").format(output)
        )

    generators = {
        "python": generate_python,
        "pywps": generate_pywps,
        "actinia": generate_actinia,
    }
    script = generators[options["format"]](model)
    try:
        output.write_text(script, encoding="utf-8")
    except OSError as error:
        gs.fatal(
            _("Unable to write <{name}>: {error}").format(name=output, error=error)
        )
    if options["format"] != "actinia":
        # Make the script executable for the owner (it starts with a shebang).
        output.chmod(output.stat().st_mode | stat.S_IXUSR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
