#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       i.scatter
# AUTHOR(S):    Vaclav Petras (with behavior derived from the wxGUI
#               interactive scatter plot by Stepan Turek)
# PURPOSE:      Compute scatter plot data (2D histogram counts) for a pair
#               of raster maps, optionally per category of a training raster
# COPYRIGHT:    (C) 2026 by the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Computes scatter plot data (2D histogram counts) for a pair of raster maps.
# % keyword: imagery
# % keyword: statistics
# % keyword: scatterplot
# % keyword: histogram
# % keyword: classification
# %end
# %option G_OPT_R_INPUTS
# % description: Names of two input raster maps (first is the x axis, second is the y axis)
# %end
# %option G_OPT_R_INPUT
# % key: training
# % required: no
# % label: Name of integer raster map with training areas
# % description: Counts are reported separately for each category; cells with null training values are not counted
# %end
# %option
# % key: bins
# % type: integer
# % required: no
# % multiple: yes
# % options: 1-
# % label: Number of bins per axis (one value for both axes or two values for x and y)
# % description: Default is one bin per integer value for integer maps when range is not set, otherwise 255
# %end
# %option
# % key: range
# % type: double
# % required: no
# % key_desc: xmin,xmax,ymin,ymax
# % label: Value range used for binning
# % description: Default is the range of values in cells where both inputs are non-null
# %end
# %option G_OPT_F_OUTPUT
# % required: no
# % description: Name for output file (default: standard output)
# %end
# %option G_OPT_F_FORMAT
# % options: json,csv
# % answer: json
# % descriptions: json;JSON (JavaScript Object Notation);csv;CSV (Comma Separated Values)
# %end

import json
import pathlib
import sys

import numpy as np

import grass.script as gs
from grass.exceptions import CalledModuleError
from grass.script import array as garray

# Maximum number of bins (product of both axes) for the automatic one bin
# per integer value; the same limit as MAX_SCATT_SIZE of the wxGUI
# interactive scatter plot.
MAX_AUTO_BINS = 4100 * 4100


def raster_datatype(name):
    """Return the datatype of a raster map, aborting if it is not accessible."""
    try:
        return gs.raster_info(name)["datatype"]
    except CalledModuleError:
        gs.fatal(_("Raster map <{name}> not found").format(name=name))


def read_as_flat_array(name):
    """Read a raster as a flat float64 array with nulls as NaN."""
    values = garray.array(name, null=np.nan, dtype=np.float64)
    return np.asarray(values).ravel()


def parse_bins(option_value):
    """Parse the bins option into a pair of per-axis bin counts."""
    bins = [int(value) for value in option_value.split(",")]
    if len(bins) == 1:
        return [bins[0], bins[0]]
    if len(bins) == 2:
        return bins
    gs.fatal(
        _("Option bins requires one or two values, {count} given").format(
            count=len(bins)
        )
    )


def parse_range(option_value):
    """Parse the range option into ((xmin, xmax), (ymin, ymax))."""
    values = [float(value) for value in option_value.split(",")]
    # The parser enforces only a multiple of four values.
    if len(values) != 4:
        gs.fatal(
            _("Option range requires exactly four values, {count} given").format(
                count=len(values)
            )
        )
    x_range = (values[0], values[1])
    y_range = (values[2], values[3])
    for axis, (low, high) in zip(("x", "y"), (x_range, y_range), strict=True):
        if low >= high:
            gs.fatal(
                _(
                    "Minimum must be lower than maximum for the {axis} axis "
                    "in option range ({low} >= {high})"
                ).format(axis=axis, low=low, high=high)
            )
    return x_range, y_range


def format_json(rasters, training, bins, x_edges, y_edges, categories):
    """Format results as a JSON document."""
    data = {
        "input": rasters,
        "training": training or None,
        "bins": bins,
        "x_edges": [float(edge) for edge in x_edges],
        "y_edges": [float(edge) for edge in y_edges],
        "categories": [
            {
                "category": category,
                "cells": int(counts.sum()),
                "counts": counts.tolist(),
            }
            for category, counts in categories
        ],
    }
    return json.dumps(data) + "\n"


def format_csv(training, categories):
    """Format nonzero bins as CSV lines."""
    lines = []
    if training:
        lines.append("category,x_bin,y_bin,count")
    else:
        lines.append("x_bin,y_bin,count")
    for category, counts in categories:
        for x_bin, y_bin in zip(*np.nonzero(counts), strict=True):
            row = f"{x_bin},{y_bin},{counts[x_bin, y_bin]}"
            if training:
                row = f"{category},{row}"
            lines.append(row)
    return "\n".join(lines) + "\n"


def main():
    options, unused_flags = gs.parser()

    rasters = options["input"].split(",")
    if len(rasters) != 2:
        gs.fatal(
            _("Option input requires exactly two raster maps, {count} given").format(
                count=len(rasters)
            )
        )
    training = options["training"]
    inputs_are_integer = all(raster_datatype(name) == "CELL" for name in rasters)
    if training:
        training_type = raster_datatype(training)
        if training_type != "CELL":
            gs.fatal(
                _(
                    "Training raster map <{name}> must be integer (CELL type), "
                    "but it is {map_type}"
                ).format(name=training, map_type=training_type)
            )

    x_values = read_as_flat_array(rasters[0])
    y_values = read_as_flat_array(rasters[1])
    valid = ~np.isnan(x_values) & ~np.isnan(y_values)

    if options["range"]:
        x_range, y_range = parse_range(options["range"])
    else:
        if not valid.any():
            gs.fatal(
                _(
                    "No cells with non-null values in both input raster maps "
                    "in the current region; "
                    "the value range cannot be determined (use option range)"
                )
            )
        x_range = (float(x_values[valid].min()), float(x_values[valid].max()))
        y_range = (float(y_values[valid].min()), float(y_values[valid].max()))

    if options["bins"]:
        bins = parse_bins(options["bins"])
    elif inputs_are_integer and not options["range"]:
        # One bin per integer value, centered on the value, as in the wxGUI
        # interactive scatter plot (which serves CELL data only).
        bins = [
            int(x_range[1] - x_range[0]) + 1,
            int(y_range[1] - y_range[0]) + 1,
        ]
        if bins[0] * bins[1] > MAX_AUTO_BINS:
            gs.fatal(
                _(
                    "The input value ranges would give {x_bins} x {y_bins} bins "
                    "(more than {maximum}); reduce the resolution of the "
                    "histogram with options bins and range"
                ).format(x_bins=bins[0], y_bins=bins[1], maximum=MAX_AUTO_BINS)
            )
        x_range = (x_range[0] - 0.5, x_range[1] + 0.5)
        y_range = (y_range[0] - 0.5, y_range[1] + 0.5)
    else:
        # The same default as the nsteps option of r.stats.
        bins = [255, 255]
    # A constant raster gives an empty data-derived range; pad it to get
    # a valid histogram (an explicit range is already validated as nonempty).
    if x_range[0] == x_range[1]:
        x_range = (x_range[0] - 0.5, x_range[1] + 0.5)
    if y_range[0] == y_range[1]:
        y_range = (y_range[0] - 0.5, y_range[1] + 0.5)

    # All categories share the same selection base, bins, and range, so the
    # resulting histograms are directly comparable.
    selections = []
    if training:
        training_values = read_as_flat_array(training)
        category_values = training_values[~np.isnan(training_values)]
        if not category_values.size:
            gs.warning(
                _(
                    "No non-null cells in training raster map <{name}> "
                    "in the current region"
                ).format(name=training)
            )
        for category in np.unique(category_values):
            selections.append((int(category), valid & (training_values == category)))
    else:
        selections.append((None, valid))

    # Passing the edges (rather than counts and range) to histogram2d
    # guarantees that the reported edges are the ones used for counting.
    x_edges = np.linspace(x_range[0], x_range[1], bins[0] + 1)
    y_edges = np.linspace(y_range[0], y_range[1], bins[1] + 1)
    categories = []
    for category, selection in selections:
        counts, unused_x, unused_y = np.histogram2d(
            x_values[selection],
            y_values[selection],
            bins=[x_edges, y_edges],
        )
        categories.append((category, counts.astype(int)))

    if options["format"] == "json":
        text = format_json(rasters, training, bins, x_edges, y_edges, categories)
    else:
        text = format_csv(training, categories)

    output = options["output"]
    if output and output != "-":
        pathlib.Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
