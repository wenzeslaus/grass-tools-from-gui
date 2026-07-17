## DESCRIPTION

*r.li.config* creates configuration files for the *r.li* landscape
structure analysis tools without the interactive *g.gui.rlisetup*
wizard. The configuration file describes the sampling frame (the part
of the raster map to analyze) and the sample areas within it.

The sampling frame is either the whole map (**frame=whole**, the
default) or a rectangular sub-region given by its edge coordinates in
map units (**frame=region** with **north**, **south**, **east**, and
**west**).

The sample areas are selected with the **method** option:

- **whole**: one sample area covering the whole sampling frame; the
  *r.li* tools write one result value to a text file.
- **moving_window**: a rectangular moving window of **width** x
  **height** cells; the *r.li* tools write an output raster map where
  each cell holds the index computed from the window centered on it.
- **units**: rectangular sample units of **width** x **height** cells
  placed in the sampling frame; the *r.li* tools write one result value
  per unit to a text file. The placement is controlled by
  **distribution**: **random** places **count** non-overlapping units
  at random (with a fixed seed, so the placement is reproducible),
  **systematic_contiguous** fills the frame with a contiguous grid of
  units.

The generated file uses the same format as *g.gui.rlisetup*: a
`SAMPLINGFRAME` line followed by a `SAMPLEAREA` line and, for sample
units and moving window, a line with the placement (`MOVINGWINDOW`,
`RANDOMNONOVERLAPPING n`, or `SYSTEMATICCONTIGUOUS`). All positions and
sizes are stored relative to the reference raster map given by the
**raster** option (see the NOTES section).

## NOTES

The configuration file is created in the `r.li` subdirectory of the
GRASS configuration directory (`~/.grass8/r.li/` on Linux,
`%APPDATA%\GRASS8\r.li\` on Windows), because that is the only place
where the *r.li* tools look for it. The **output** option is therefore
a file name, not a path. The *r.li* tools also accept the full path of
a file in this directory, but not paths outside of it. The directory
honors the `GRASS_CONFIG_DIR` environment variable when set.

The file does not store map coordinates: positions and sizes are stored
as fractions of the rows and columns of the reference raster map
(**raster**), and edge coordinates given with **frame=region** are
first aligned to the cells of that raster. This makes the file
independent of a specific raster map, and the *r.li* tools resolve the
fractions against the current computation region at analysis time. For
meaningful results, run the *r.li* tools with the computation region
set to match the reference raster map (`g.region raster=...`).

Circular sample areas offered by the *g.gui.rlisetup* wizard are not
supported: the masked sample areas they are based on do not work
reliably in *r.li.daemon* (results depend on the process environment
and configurations combining them with moving window or sample unit
placement fail). Sampling based on vector maps or interactively drawn
regions is also not covered; use *g.gui.rlisetup* for those.

## EXAMPLES

The examples use the `landclass96` map of the North Carolina sample
dataset:

```sh
g.region raster=landclass96
```

One sample area covering the whole map, result in a text file:

```sh
r.li.config raster=landclass96 output=whole_map
r.li.patchdensity input=landclass96 config=whole_map output=patchdensity_whole
```

Analysis limited to a rectangular sub-region:

```sh
r.li.config raster=landclass96 output=sub_region \
    frame=region north=228500 south=215000 east=644000 west=630000
r.li.patchdensity input=landclass96 config=sub_region output=patchdensity_sub
```

A 7x7 cell moving window producing a raster map of patch densities:

```sh
r.li.config raster=landclass96 output=window7 \
    method=moving_window width=7 height=7
r.li.patchdensity input=landclass96 config=window7 output=patchdensity_window7
```

Ten randomly placed sample units of 10x10 cells, one result per unit:

```sh
r.li.config raster=landclass96 output=random10 \
    method=units width=10 height=10 distribution=random count=10
r.li.patchdensity input=landclass96 config=random10 output=patchdensity_random
```

A systematic contiguous grid of 20x20 cell sample units:

```sh
r.li.config raster=landclass96 output=grid20 \
    method=units width=20 height=20 distribution=systematic_contiguous
r.li.patchdensity input=landclass96 config=grid20 output=patchdensity_grid
```

## SEE ALSO

*[g.gui.rlisetup](g.gui.rlisetup.md), [r.li](r.li.md),
[r.li.daemon](r.li.daemon.md), [r.li.patchdensity](r.li.patchdensity.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics

Based on the configuration file writing code of *g.gui.rlisetup* by
Luca Delucchi.
