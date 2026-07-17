# i.scatter

## DESCRIPTION

*i.scatter* computes scatter plot data for a pair of raster maps,
typically two bands of an imagery group. The result is a 2D histogram:
the value range of each raster is divided into a number of bins
(**bins**) and the tool counts the cells falling into each pair of
bins. The first raster in **input** is the x axis, the second one is
the y axis.

Only cells which are non-null in both input rasters are counted. With
**training**, an integer (CELL) raster with category values, e.g.,
rasterized training areas from supervised classification, counts are
reported separately for each category present in the training raster;
cells where the training raster is null are not counted. All categories
are binned with the same bin edges, so the per-category histograms are
directly comparable.

By default, the value range used for binning is the actual range of
values in the current computational region, computed from the cells
where both inputs are non-null (regardless of the training raster).
A fixed range can be set with **range** to make outputs comparable
across regions, training rasters, or points in time. Cells with values
outside the range are not counted.

When **bins** is not set and both inputs are integer (CELL) rasters and
**range** is not set either, each integer value gets its own bin: for an
axis with values from *min* to *max*, there are *max - min + 1* bins
with edges at *min - 0.5*, *min + 0.5*, ..., *max + 0.5*, so each bin
is centered on an integer value. Otherwise, the default is 255 bins per
axis, evenly dividing the range.

The computational region determines which cells are read and counted
(use *g.region* to set it; an active raster mask is respected).

### Output formats

With **format=json** (the default), the output is a single JSON object:

```json
{
  "input": ["band1", "band2"],
  "training": null,
  "bins": [4, 3],
  "x_edges": [0.5, 1.5, 2.5, 3.5, 4.5],
  "y_edges": [0.5, 1.5, 2.5, 3.5],
  "categories": [
    {"category": null, "cells": 12, "counts": [[1, 1, 1], "..."]}
  ]
}
```

The *counts* item of each category is a 2D array with one row per x
bin and one column per y bin. `counts[i][j]` is the number of counted
cells whose first-raster value falls into x bin `i` and whose
second-raster value falls into y bin `j`. Bin `i` spans
`[x_edges[i], x_edges[i+1])`; the last bin of each axis also includes
its upper edge. *cells* is the sum of *counts*, i.e., the number of
cells counted for the category. Without **training**, there is exactly
one entry in *categories* and its *category* is `null`; with
**training**, *category* is the integer category value and the entries
are sorted by category.

With **format=csv**, only nonzero bins are written, one per line, as
zero-based bin indices and the count. The header line is
`x_bin,y_bin,count`, or `category,x_bin,y_bin,count` when **training**
is given. Lines are ordered by category, then x bin, then y bin.

By default the output goes to standard output; use **output** to write
to a file instead.

## NOTES

With the default one bin per integer value, bin index plus the axis
minimum gives the cell value, and the counts match `r.stats -c` for the
same raster pair. To get the same one-value-one-bin behavior with an
explicit range, align the bins with the integer values manually, e.g.,
for values from 1 to 4 use `bins=4` and range limits `0.5,4.5`.

When the number of bins is determined automatically, *i.scatter*
refuses to create more than 4100 x 4100 bins (integer rasters with a
very wide value range); set **bins**, and optionally **range**, for
such data. If the range of an axis derived from the data is empty
(a constant raster), it is padded by 0.5 in both directions.

*i.scatter* is a standalone counterpart of the data computation done by
the interactive scatter plot of *g.gui.iclass* and the map display
(implemented in C as `I_compute_scatts`). Both count integer data with
one bin per integer value, but the interactive tool works on CELL
rasters only and derives the bins from the whole map's stored range,
while *i.scatter* also accepts floating-point rasters, bins them over
a value range, and by default derives the range from the current
computational region. The interactive tool additionally conditions
counts on areas selected in the plots themselves, which has no
equivalent here.

For integer rasters, *r.stats* already covers unconditioned counting:
`r.stats -c input=band1,band2` reports the count of every occurring
value pair, and adding a category raster as a third input conditions
the counts on its categories. *r.stats* with **nsteps** (default 255,
same as here) can also bin floating-point values, but each raster is
binned by its own map-wide stored range and the bins are reported as
text labels. The value of *i.scatter* is uniform binning across both
axes with explicit numeric bin edges, a fixed user-defined range
independent of the data, and machine-readable JSON output, in
particular for floating-point data and per-category (training area)
counts.

Each input raster is read for the whole computational region as a
disk-backed NumPy array (via *r.out.bin*, 8 bytes per cell per raster),
so available disk space and address space, not RAM, limit the region
size. The histogram itself needs memory proportional to the number of
bins (x bins times y bins per category).

## EXAMPLES

Scatter plot data of two integer bands in JSON, with one bin per
integer value (North Carolina dataset):

```sh
g.region raster=lsat7_2002_10
i.scatter input=lsat7_2002_10,lsat7_2002_20
```

Counts per training area category, written to a CSV file:

```sh
i.scatter input=lsat7_2002_10,lsat7_2002_20 training=landclass96 \
    format=csv output=scatter.csv
```

Plot the counts with matplotlib:

```python
import json
import subprocess

import matplotlib.pyplot as plt
import numpy as np

data = json.loads(
    subprocess.check_output(
        ["i.scatter", "input=lsat7_2002_10,lsat7_2002_20"], text=True
    )
)
counts = np.array(data["categories"][0]["counts"])
plt.pcolormesh(data["x_edges"], data["y_edges"], counts.T)
plt.show()
```

## SEE ALSO

*[g.gui.iclass](g.gui.iclass.md), [g.region](g.region.md),
[r.stats](r.stats.md), [r.univar](r.univar.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics

Based on the behavior of the wxGUI interactive scatter plot by Stepan
Turek.
