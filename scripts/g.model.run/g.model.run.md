## DESCRIPTION

*g.model.run* runs a model created in the wxGUI Graphical Modeler
(*g.gui.gmodeler*) and stored in a GRASS Model file (`.gxm`) without
starting the GUI. Actions (tool runs) are executed in the order defined
by the model; actions disabled in the model are skipped. When the model
has the overwrite property set, all actions run with overwriting
enabled.

Model variables are used with their default values from the model file.
The defaults can be overridden with the **variables** option, e.g.,
`variables="raster=elevation"`. Every variable must end up with a
value; the tool ends with an error otherwise, matching the behavior of
the GUI dialog which requires values for all variables before a run.

Options and flags marked as parameterized in the model are set with the
**parameters** option using `action.option=value` keys, where `action`
is either the numeric action id or the tool name of the action, e.g.,
`parameters="r.colors.color=bgyr"` or `parameters="7.color=bgyr"`.
Parameterized flags take the values `true` and `false`. This mirrors
the GUI, which asks for parameterized options grouped by action in a
dialog before the run; the action id makes the reference unambiguous
when the same tool is used by several actions (the tool asks for the id
when a tool name is ambiguous). Parameterized options without a default
value in the model must be given a value; the tool ends with an error
listing the missing keys otherwise. Values for options which are not
parameterized in the model are rejected.

Data marked as intermediate in the model is removed at the end of a
successful run, in the same way the GUI removes it when the *Delete
intermediate data* option is checked. The **-i** flag keeps the
intermediate data instead.

## NOTES

Coverage of the `.gxm` format:

- Variables: supported, including the `%variable` and `%{variable}`
  reference forms in option values. Values of string-typed variables
  are quoted when substituted into loop conditions (like in the GUI).
- Parameterized options and flags: supported through the **parameters**
  option, including parameterized long flags such as `overwrite`.
- Loops: supported for both condition forms the Graphical Modeler
  writes: a list of values (e.g., `map in ["a", "b"]`) and a command in
  backticks whose output lines are the values (e.g.,
  ``map in `g.list type=raster pattern=x*` ``). The list form is
  evaluated as a Python literal only (no expressions). An action
  belonging to more than one loop (nested loops) causes an error.
- If-else conditions: not supported; the tool ends with an error when
  the model contains an if-else item. Note that the GUI's own model run
  (`Model.Run` in `gui/wxpython/gmodeler/model.py`) does not execute
  if-else items either.
- Intermediate data: raster, vector, and 3D raster data items marked as
  intermediate are removed with *g.remove*; other types are reported
  and kept. Intermediate names which still contain an unresolved
  variable (e.g., a loop variable) are reported and kept.
- Layout-only elements (positions, sizes, comment items) are ignored.

Because **variables** and **parameters** accept multiple values, values
containing commas cannot be passed through them (the standard GRASS
parser splits multiple values on commas).

The `.gxm` parsing code is duplicated in *g.model.export* because
scripts install as standalone files. As a follow-up, the parser should
move to a Python library location (e.g., a new `grass.models` package)
which the GUI Graphical Modeler can use as well.

## EXAMPLES

Run a model with the variable and parameterized option defaults stored
in the model:

```sh
g.model.run input=zipcodes_avg_elevation.gxm
```

Override a model variable and a parameterized option (the **color**
option of the *r.colors* action):

```sh
g.model.run input=zipcodes_avg_elevation.gxm \
    variables="raster=/data/elevation.tif" \
    parameters="r.colors.color=viridis"
```

Keep the intermediate data for inspection:

```sh
g.model.run -i input=zipcodes_avg_elevation.gxm
```

## SEE ALSO

*[g.gui.gmodeler](g.gui.gmodeler.md), [g.model.export](g.model.export.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics,
with substantial AI assistance\
Based on the wxGUI Graphical Modeler by Martin Landa and Ondrej Pesek
