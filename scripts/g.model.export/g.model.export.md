## DESCRIPTION

*g.model.export* converts a model created in the wxGUI Graphical
Modeler (*g.gui.gmodeler*) and stored in a GRASS Model file (`.gxm`)
into a runnable script. The only **format** currently supported is
`python`: a Python script with a GRASS parser interface which runs the
model actions with `grass.script.run_command`, equivalent to the
*Python* export of the Graphical Modeler.

Model variables and options marked as parameterized in the model become
options of the generated script. A parameterized option of an action is
named after the action and the option (e.g., the parameterized
**color** option of an *r.colors* action with id 7 becomes
`rcolors7_color`); variables keep their names. Default values from the
model become the option defaults. Parameterized flags become
`True`/`False` options of the script.

Data marked as intermediate in the model is removed by a `cleanup()`
function registered to run at the end of the generated script.

## NOTES

Coverage of the `.gxm` format:

- Variables: supported; references in option values become option
  lookups in the generated code, with values mixing text and references
  translated to f-strings.
- Parameterized options and flags: supported. Parameterized long flags
  (e.g., `overwrite`) are not representable in the generated interface
  and are exported as fixed flags with a warning.
- Loops: supported for both condition forms the Graphical Modeler
  writes: a list of values (translated to a Python `for` statement) and
  a command in backticks (translated to iteration over
  `read_command(...).splitlines()`). Loop conditions referencing model
  variables are not supported and cause an error. An action belonging
  to more than one loop (nested loops) causes an error.
- If-else conditions: not supported; the tool ends with an error when
  the model contains an if-else item.
- Intermediate data: raster, vector, and 3D raster data items marked as
  intermediate are removed in `cleanup()`; names containing a variable
  reference cannot be resolved there and are listed in a comment
  instead.
- Actions disabled in the model are included as commented-out code.
- Layout-only elements (positions, sizes, comment items) are ignored.

The generated script is not byte-identical to the output of the
Graphical Modeler's Python export, but it is equivalent: it has the
same parser interface (option keys, types, and defaults) and runs the
same commands. Unlike the GUI export, this tool skips (comments out)
disabled actions instead of running them and exports loops.

The tool needs the interface descriptions of the tools used by the
model, so those tools must be installed when exporting.

Export to PyWPS and actinia formats, which the Graphical Modeler also
offers (`ModelToPyWPS` and `ModelToActinia` in
`gui/wxpython/gmodeler/model_convert.py`), is future work for the
**format** option.

The `.gxm` parsing code is duplicated in *g.model.run* because scripts
install as standalone files. When porting these tools to the main
source tree, the parser should move to a Python library location
(e.g., a new `grass.models` package) which the GUI Graphical Modeler
can use as well.

## EXAMPLES

Convert a model to a Python script and run the script with one of its
option defaults overridden:

```sh
g.model.export input=zipcodes_avg_elevation.gxm output=avg_elevation.py
python3 avg_elevation.py rcolors7_color=viridis
```

## SEE ALSO

*[g.gui.gmodeler](g.gui.gmodeler.md), [g.model.run](g.model.run.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics,
with substantial AI assistance\
Based on the wxGUI Graphical Modeler by Martin Landa and Ondrej Pesek
