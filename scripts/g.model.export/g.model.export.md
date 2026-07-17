## DESCRIPTION

*g.model.export* converts a model created in the wxGUI Graphical
Modeler (*g.gui.gmodeler*) and stored in a GRASS Model file (`.gxm`)
into a runnable script or process definition. The **format** option
selects the output:

- `python` (default): a Python script with a GRASS parser interface
  which runs the model actions with `grass.script.run_command`,
  equivalent to the *Python* export of the Graphical Modeler.
- `pywps`: a Python script with a PyWPS `Process` subclass whose
  handler runs the model actions, equivalent to the *PyWPS* export of
  the Graphical Modeler.
- `actinia`: an actinia process chain in JSON, equivalent to the
  *actinia* export of the Graphical Modeler.

Model variables and options marked as parameterized in the model become
options of the generated script (`python`), process inputs (`pywps`),
or Jinja template placeholders (`actinia`). A parameterized option of
an action is named after the action and the option (e.g., the
parameterized **color** option of an *r.colors* action with id 7
becomes `rcolors7_color`); variables keep their names. Default values
from the model become the option, input, or placeholder defaults.
Parameterized flags become `True`/`False` options or inputs of the
script (`python` and `pywps`; actinia does not support parameterized
flags and they are exported in their current state with a warning).

With `format=python`, data marked as intermediate in the model is
removed by a `cleanup()` function registered to run at the end of the
generated script.

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
  variables are not supported and cause an error.
- If-else conditions: supported for the `python` and `pywps` formats.
  The condition text is a Python expression; model variable references
  in it become option or input lookups converted to the variable's type
  (e.g., `%{threshold} > 5` with an integer variable becomes
  `int(options["threshold"]) > 5`), so the branch is selected by the
  value given at run time. The `if` branch actions run when the
  condition is true, the `else` branch actions otherwise.
- Blocks cannot be nested: an action belonging to more than one loop or
  if-else condition causes an error.
- Intermediate data: raster, vector, and 3D raster data items marked as
  intermediate are removed in `cleanup()`; names containing a variable
  reference cannot be resolved there and are listed in a comment
  instead.
- Actions disabled in the model are included as commented-out code
  (`python` and `pywps`); the actinia export leaves them out with a
  warning because JSON has no comments.
- Layout-only elements (positions, sizes, comment items) are ignored.

The generated output is not byte-identical to the output of the
Graphical Modeler's exports, but it is equivalent: the same interface
(option keys, types, and defaults; process inputs and outputs; process
chain entries) and the same commands. Unlike the GUI exports, this tool
skips (comments out) disabled actions instead of running them, exports
loops and if-else conditions instead of silently dropping them, and
writes only the option values stored in the model (the GUI exports add
interface defaults such as `nprocs=0`).

The tool needs the interface descriptions of the tools used by the
model, so those tools must be installed when exporting.

PyWPS format details, following the `ModelToPyWPS` export of the
Graphical Modeler (`gui/wxpython/gmodeler/model_convert.py`):

- Parameterized options become `LiteralInput` objects, or
  `ComplexInput` objects when the option name contains `input` and the
  data type is raster (GeoTIFF) or vector (GML); model variables become
  `LiteralInput` objects (the GUI export leaves variable references
  unresolved in the generated commands).
- New non-intermediate raster and vector outputs of actions outside
  loops and conditions become `ComplexOutput` objects; the handler
  exports them with *r.out.gdal* (GeoTIFF) or *v.out.ogr* (GML) to the
  temporary directory and assigns the file to the process response.
  Outputs of other data types, and outputs inside loops or conditions,
  are skipped with a warning (the GUI export writes non-compiling
  `WRITE YOUR ...` placeholders for other data types).
- There is no cleanup of intermediate data (same as the GUI export);
  a PyWPS process is expected to run in a disposable mapset.

actinia format details, following the `ModelToActinia` export of the
Graphical Modeler:

- The output is a process chain with one entry per enabled action, in
  execution order, with the stored option values split into `inputs`
  and `outputs` by the option direction in the tool interface.
- Parameterized options and model variable references become Jinja
  placeholders (`{{ name }}`) and the process list is wrapped in a
  `template` object when any placeholder is present. Placeholder
  defaults are quoted as Jinja string literals when they are not
  numbers (the GUI export writes them unquoted, which Jinja evaluates
  as undefined names).
- Loops and if-else conditions cannot be represented in a process
  chain and cause an error; long flags (e.g., `overwrite`) have no
  process chain equivalent and are skipped with a warning.

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

Convert the same model to a PyWPS process and to an actinia process
chain:

```sh
g.model.export input=zipcodes_avg_elevation.gxm output=avg_elevation_wps.py format=pywps
g.model.export input=zipcodes_avg_elevation.gxm output=avg_elevation.json format=actinia
```

## SEE ALSO

*[g.gui.gmodeler](g.gui.gmodeler.md), [g.model.run](g.model.run.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics,
with substantial AI assistance\
Based on the wxGUI Graphical Modeler by Martin Landa and Ondrej Pesek
