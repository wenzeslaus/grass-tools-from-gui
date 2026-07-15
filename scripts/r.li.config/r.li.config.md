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
- **moving_window**: a moving window; the *r.li* tools write an output
  raster map where each cell holds the index computed from the window
  centered on it.
- **units**: sample units placed in the sampling frame; the *r.li*
  tools write one result value per unit to a text file. The placement
  is controlled by **distribution**: **random** places **count**
  non-overlapping units at random (with a fixed seed, so the placement
  is reproducible), **systematic_contiguous** fills the frame with a
  contiguous grid of units.
- **vector**: one masked sample area per area of the vector map given
  by the **vector** option; the *r.li* tools write one result value
  per area to a text file (see the NOTES section).

With **method=moving_window** and **method=units**, the sample area is
either a rectangle of **width** x **height** cells (**shape=rectangle**,
the default) or a circle with the given **radius** in map units
(**shape=circle**). For a circle, *r.li.config* creates a binary
circular mask raster map named by the **mask** option with *r.circle*
(see the NOTES section).

The generated file uses the same format as *g.gui.rlisetup*: a
`SAMPLINGFRAME` line followed by the sample area lines (`SAMPLEAREA`,
`MASKEDSAMPLEAREA` for circles, or `MASKEDOVERLAYAREA` with `RASTERMAP`
and `VECTORMAP` for vector sampling) and, for sample units and moving
window, a line with the placement (`MOVINGWINDOW`,
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

With **shape=circle**, the circle mask raster map is created in the
box of the rounded circle diameter (in cells, increased to the next
odd number) at the north-west corner of the sampling frame, the same
way *g.gui.rlisetup* creates it. *r.li.daemon* reads sample area masks
at the absolute position of each sample area, so only moving window
positions or sample units overlapping this box produce values; all
other sample areas give NULL results. Unlike *g.gui.rlisetup*, which
creates the circle mask for keyboard-defined sample units but omits it
from the configuration file (so the circle has no effect there),
*r.li.config* always writes the mask into a `MASKEDSAMPLEAREA` line.

With **method=vector**, every area category of **vector** (in
**layer**) becomes one sample area: the area is converted to a raster
mask named `<raster>_<vector>_<category>` covering the bounding box of
the area aligned to the reference raster, like *g.gui.rlisetup* does
with all areas of a vector map. Cells of the bounding box outside the
area are masked out in the analysis. The configuration file records
the reference raster name, and the *r.li* tools accept only that exact
name as their input map. Sampling based on interactively drawn regions
is not covered; use *g.gui.rlisetup* for that.

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

A circular moving window with a radius of 100 meters; the circle mask
raster map `circle100` is created by *r.li.config*:

```sh
r.li.config raster=landclass96 output=circle100_window \
    method=moving_window shape=circle radius=100 mask=circle100
r.li.patchdensity input=landclass96 config=circle100_window \
    output=patchdensity_circle
```

One masked sample area per area of a vector map, one result per area:

```sh
r.li.config raster=landclass96 output=zones \
    method=vector vector=urbanarea
r.li.patchdensity input=landclass96 config=zones output=patchdensity_zones
```

## SEE ALSO

*[g.gui.rlisetup](g.gui.rlisetup.md), [r.circle](r.circle.md),
[r.li](r.li.md), [r.li.daemon](r.li.daemon.md),
[r.li.patchdensity](r.li.patchdensity.md), [v.to.rast](v.to.rast.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics

Based on the configuration file writing code of *g.gui.rlisetup* by
Luca Delucchi.
