#!/usr/bin/env python3

############################################################################
#
# MODULE:    r.li.config
# AUTHOR(S): Vaclav Petras
#
# PURPOSE:   Create configuration files for r.li tools without the GUI
# COPYRIGHT: (C) 2026 by Vaclav Petras and the GRASS Development Team
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#############################################################################

"""Create configuration files for r.li tools without the GUI"""

# %module
# % description: Creates a configuration file for r.li landscape structure analysis tools.
# % keyword: raster
# % keyword: landscape structure analysis
# % keyword: sampling
# % overwrite: yes
# %end
# %option G_OPT_R_INPUT
# % key: raster
# % description: Reference raster map used to convert the sampling setup to relative coordinates
# %end
# %option
# % key: output
# % type: string
# % required: yes
# % description: Name for the configuration file (created in the r.li configuration directory)
# %end
# %option
# % key: frame
# % type: string
# % required: yes
# % options: whole,region
# % answer: whole
# % description: Sampling frame
# % descriptions: whole;Whole raster map;region;Sub-region given by north, south, east, and west
# % guisection: Sampling frame
# %end
# %option
# % key: north
# % type: double
# % required: no
# % description: Northern edge of the sampling frame (map units, with frame=region)
# % guisection: Sampling frame
# %end
# %option
# % key: south
# % type: double
# % required: no
# % description: Southern edge of the sampling frame (map units, with frame=region)
# % guisection: Sampling frame
# %end
# %option
# % key: east
# % type: double
# % required: no
# % description: Eastern edge of the sampling frame (map units, with frame=region)
# % guisection: Sampling frame
# %end
# %option
# % key: west
# % type: double
# % required: no
# % description: Western edge of the sampling frame (map units, with frame=region)
# % guisection: Sampling frame
# %end
# %option
# % key: method
# % type: string
# % required: yes
# % options: whole,moving_window,units,vector
# % answer: whole
# % description: Sampling method
# % descriptions: whole;One sample area covering the whole sampling frame;moving_window;Moving window analysis producing an output raster map;units;Sample units placed in the sampling frame;vector;Masked sample areas from the areas of a vector map
# % guisection: Sample areas
# %end
# %option
# % key: shape
# % type: string
# % required: no
# % options: rectangle,circle
# % answer: rectangle
# % description: Shape of the moving window or sample units (with method=moving_window or method=units)
# % descriptions: rectangle;Rectangle of width x height cells;circle;Circle with the given radius
# % guisection: Sample areas
# %end
# %option
# % key: width
# % type: integer
# % required: no
# % description: Width of the moving window or sample unit in cells (with method=moving_window or method=units)
# % guisection: Sample areas
# %end
# %option
# % key: height
# % type: integer
# % required: no
# % description: Height of the moving window or sample unit in cells (with method=moving_window or method=units)
# % guisection: Sample areas
# %end
# %option
# % key: distribution
# % type: string
# % required: no
# % options: random,systematic_contiguous
# % description: Distribution of sample units (with method=units)
# % descriptions: random;Random non-overlapping placement;systematic_contiguous;Systematic contiguous placement
# % guisection: Sample areas
# %end
# %option
# % key: count
# % type: integer
# % required: no
# % description: Number of sample units to place (with distribution=random)
# % guisection: Sample areas
# %end
# %option
# % key: radius
# % type: double
# % required: no
# % description: Radius of the circular sample area in map units (with shape=circle)
# % guisection: Sample areas
# %end
# %option G_OPT_R_OUTPUT
# % key: mask
# % required: no
# % description: Name for the circle mask raster map to create (with shape=circle)
# % guisection: Sample areas
# %end
# %option G_OPT_V_INPUT
# % key: vector
# % required: no
# % label: Vector map with areas used as sample areas (with method=vector)
# % description: One mask raster map named <raster>_<vector>_<category> is created per area
# % guisection: Sample areas
# %end
# %option G_OPT_V_FIELD
# % guisection: Sample areas
# %end

import os
import sys
from pathlib import Path

import grass.script as gs
from grass.exceptions import CalledModuleError


def rli_config_dir(env):
    """Return the r.li configuration directory.

    Mirrors G_config_path() in lib/gis/home.c combined with the "r.li"
    subdirectory used by r.li.daemon, so that r.li tools find the file.
    """
    base = env.get("GRASS_CONFIG_DIR")
    if not base:
        base = env.get("APPDATA") if sys.platform == "win32" else env.get("HOME")
    if not base:
        gs.fatal(_("Unable to determine the configuration directory"))
    if sys.platform == "win32":
        config = os.path.join(base, "GRASS8")
    elif sys.platform == "darwin":
        config = os.path.join(base, "Library", "GRASS8")
    else:
        config = os.path.join(base, ".grass8")
    return os.path.join(config, "r.li")


def required_for(options, names, condition):
    """Fatal error unless all options in names are set"""
    for name in names:
        if not options[name]:
            gs.fatal(
                _("Option <{option}> is required for {condition}").format(
                    option=name, condition=condition
                )
            )


def rejected_for(options, names, condition):
    """Fatal error if any option in names is set"""
    for name in names:
        if options[name]:
            gs.fatal(
                _("Option <{option}> is not allowed with {condition}").format(
                    option=name, condition=condition
                )
            )


def compute_frame(options, info):
    """Compute the sampling frame in cells of the reference raster.

    Returns the SAMPLINGFRAME line and the frame as cell offsets and
    lengths (x, y, number of rows, number of columns).
    """
    rows = int(info["rows"])
    cols = int(info["cols"])
    if options["frame"] == "whole":
        rejected_for(options, ["north", "south", "east", "west"], "frame=whole")
        # g.gui.rlisetup writes this special form instead of computed values.
        return "SAMPLINGFRAME 0|0|1|1", 0, 0, rows, cols
    required_for(options, ["north", "south", "east", "west"], "frame=region")
    north = float(options["north"])
    south = float(options["south"])
    east = float(options["east"])
    west = float(options["west"])
    if north <= south:
        gs.fatal(_("Value of north must be larger than value of south"))
    if east <= west:
        gs.fatal(_("Value of east must be larger than value of west"))
    # Align the frame edges to the raster grid by converting to whole cells.
    sf_y = round((info["north"] - north) / info["nsres"])
    sf_x = round((west - info["west"]) / info["ewres"])
    sf_rl = round((north - south) / info["nsres"])
    sf_cl = round((east - west) / info["ewres"])
    if sf_rl < 1 or sf_cl < 1:
        gs.fatal(_("The sampling frame is smaller than one raster cell"))
    if sf_y < 0 or sf_x < 0 or sf_y + sf_rl > rows or sf_x + sf_cl > cols:
        gs.fatal(_("The sampling frame extends outside of the raster map"))
    line = (
        f"SAMPLINGFRAME {sf_x / cols!r}|{sf_y / rows!r}"
        f"|{sf_rl / rows!r}|{sf_cl / cols!r}"
    )
    return line, sf_x, sf_y, sf_rl, sf_cl


def sample_size(options, sf_rl, sf_cl):
    """Validate and return sample area width and height in cells"""
    required_for(options, ["width", "height"], f"method={options['method']}")
    width = int(options["width"])
    height = int(options["height"])
    if width < 1 or height < 1:
        gs.fatal(_("Sample area width and height must be at least one cell"))
    if height > sf_rl or width > sf_cl:
        gs.fatal(_("The sample area is larger than the sampling frame"))
    return width, height


def circle_size(options, info, sf_rl, sf_cl):
    """Validate and return the bounding box of the circle in cells.

    Replicates RLIWizard._value_for_circle in
    gui/wxpython/rlisetup/wizard.py: the box is the rounded diameter in
    cells, increased to the next odd number. The wizard derives the row
    count from the east-west resolution and the column count from the
    north-south resolution; this is kept for byte-identical output (the
    values are equal for square cells).
    """
    required_for(options, ["radius", "mask"], "shape=circle")
    radius = float(options["radius"])
    if radius <= 0:
        gs.fatal(_("Option <radius> must be positive"))
    cir_rl = round((2 * radius) / info["ewres"])
    cir_cl = round((2 * radius) / info["nsres"])
    if not cir_rl % 2:
        cir_rl += 1
    if not cir_cl % 2:
        cir_cl += 1
    if cir_rl > sf_rl or cir_cl > sf_cl:
        gs.fatal(_("The circle is larger than the sampling frame"))
    return cir_rl, cir_cl


def create_circle_mask(options, info, sf_x, sf_y, cir_rl, cir_cl):
    """Create the circular mask raster map like RLIWizard._circle.

    The mask is a binary r.circle raster covering the bounding box of
    the circle at the north-west corner of the sampling frame, with the
    circle centered in the box. r.li.daemon reads sample area masks at
    the absolute position of the mask raster (see the NOTES in the
    documentation for the consequences).
    """
    sf_n = info["north"] - sf_y * info["nsres"]
    sf_w = info["west"] + sf_x * info["ewres"]
    # The row count with the east-west resolution and the column count
    # with the north-south resolution replicate RLIWizard._circle.
    east_edge = sf_w + cir_rl * info["ewres"]
    south_edge = sf_n - cir_cl * info["nsres"]
    gs.use_temp_region()
    try:
        # Resolution of the reference raster, extent of the circle box.
        gs.run_command("g.region", raster=options["raster"], quiet=True)
        gs.run_command(
            "g.region", n=sf_n, s=south_edge, e=east_edge, w=sf_w, quiet=True
        )
        center = gs.region(complete=True)
        gs.run_command(
            "r.circle",
            flags="b",
            output=options["mask"],
            max=options["radius"],
            coordinates=(center["center_easting"], center["center_northing"]),
            quiet=True,
        )
    finally:
        gs.del_temp_region()


def vector_areas(options, info):
    """Compute MASKEDOVERLAYAREA lines from the areas of a vector map.

    Replicates sampleAreaVector and convertFeature in
    gui/wxpython/rlisetup/functions.py: each area category is converted
    to a raster mask covering the bounding box of the area aligned to
    the reference raster, and one MASKEDOVERLAYAREA line per mask is
    followed by the RASTERMAP and VECTORMAP lines.
    """
    vector = options["vector"]
    layer = options["layer"]
    raster = options["raster"]
    try:
        cats_text = gs.read_command(
            "v.category",
            input=vector,
            layer=layer,
            option="print",
            type="centroid",
            quiet=True,
        )
    except CalledModuleError:
        gs.fatal(_("Vector map <{}> not found").format(vector))
    cats = sorted(
        {int(cat) for line in cats_text.splitlines() for cat in line.split("/")}
    )
    if not cats:
        gs.fatal(
            _("Vector map <{vector}> has no areas in layer <{layer}>").format(
                vector=vector, layer=layer
            )
        )
    lines = []
    prefix = "{rast}_{vect}_".format(
        rast=raster.split("@")[0], vect=vector.split("@")[0]
    )
    gs.use_temp_region()
    try:
        for cat in cats:
            mask_name = f"{prefix}{cat}"
            tmp_vector = f"tmp_{mask_name}"
            gs.run_command(
                "v.extract",
                input=vector,
                cats=cat,
                type="area",
                layer=layer,
                output=tmp_vector,
                flags="d",
                quiet=True,
            )
            # Bounding box of the area aligned to the reference raster.
            gs.run_command("g.region", raster=raster, quiet=True)
            gs.run_command("g.region", vector=tmp_vector, quiet=True)
            gs.run_command("g.region", align=raster, quiet=True)
            gs.run_command(
                "v.to.rast",
                input=tmp_vector,
                type="area",
                layer=layer,
                use="value",
                value=cat,
                output=mask_name,
                quiet=True,
            )
            gs.run_command(
                "g.remove", flags="f", type="vector", name=tmp_vector, quiet=True
            )
            region = gs.region()
            lines.append(
                "MASKEDOVERLAYAREA {name}|{n}|{s}|{e}|{w}".format(
                    name=mask_name,
                    n=region["n"],
                    s=region["s"],
                    e=region["e"],
                    w=region["w"],
                )
            )
    finally:
        gs.del_temp_region()
    # r.li.daemon compares the RASTERMAP value with the input raster
    # name given to the r.li tool, so the names must match exactly.
    lines.extend([f"RASTERMAP {raster}", f"VECTORMAP {vector}"])
    return lines


def compute_areas(options, info, sf_x, sf_y, sf_rl, sf_cl):
    """Compute the sample area lines of the configuration file"""
    rows = int(info["rows"])
    cols = int(info["cols"])
    method = options["method"]
    if method != "units":
        rejected_for(options, ["distribution", "count"], f"method={method}")
    if method != "vector":
        rejected_for(options, ["vector"], f"method={method}")
    if options["shape"] == "circle" and method not in {"moving_window", "units"}:
        gs.fatal(_("Option shape=circle requires method=moving_window or method=units"))
    if method == "whole":
        rejected_for(options, ["width", "height", "radius", "mask"], "method=whole")
        return [
            (
                f"SAMPLEAREA {sf_x / cols!r}|{sf_y / rows!r}"
                f"|{sf_rl / rows!r}|{sf_cl / cols!r}"
            )
        ]
    if method == "vector":
        rejected_for(options, ["width", "height", "radius", "mask"], "method=vector")
        required_for(options, ["vector"], "method=vector")
        return vector_areas(options, info)
    if options["shape"] == "circle":
        rejected_for(options, ["width", "height"], "shape=circle")
        unit_rl, unit_cl = circle_size(options, info, sf_rl, sf_cl)
        create_circle_mask(options, info, sf_x, sf_y, unit_rl, unit_cl)
        area = (
            f"MASKEDSAMPLEAREA -1|-1|{unit_rl / rows!r}|{unit_cl / cols!r}"
            f"|{options['mask']}"
        )
    else:
        rejected_for(options, ["radius", "mask"], "shape=rectangle")
        unit_cl, unit_rl = sample_size(options, sf_rl, sf_cl)
        area = f"SAMPLEAREA -1|-1|{unit_rl / rows!r}|{unit_cl / cols!r}"
    if method == "moving_window":
        return [area, "MOVINGWINDOW"]
    required_for(options, ["distribution"], "method=units")
    if options["distribution"] == "systematic_contiguous":
        rejected_for(options, ["count"], "distribution=systematic_contiguous")
        return [area, "SYSTEMATICCONTIGUOUS"]
    required_for(options, ["count"], "distribution=random")
    count = int(options["count"])
    # The same limit is enforced by r.li.daemon at runtime.
    max_count = (sf_rl // unit_rl) * (sf_cl // unit_cl)
    if not 1 <= count <= max_count:
        gs.fatal(
            _(
                "Number of sample units must be between 1 and {max} "
                "for this sample size and sampling frame"
            ).format(max=max_count)
        )
    return [area, f"RANDOMNONOVERLAPPING {count}"]


def main():
    options, unused_flags = gs.parser()
    output = options["output"]
    if os.path.basename(output) != output or not output:
        gs.fatal(
            _("Option <output> must be a file name, not a path: {}").format(output)
        )
    raster = options["raster"]
    try:
        info = gs.raster_info(raster)
    except CalledModuleError:
        gs.fatal(_("Raster map <{}> not found").format(raster))

    config_dir = rli_config_dir(os.environ)
    path = Path(config_dir) / output
    # Check before computing the areas, which may create raster maps.
    if path.exists() and not gs.overwrite():
        gs.fatal(
            _(
                "Configuration file <{}> already exists. Use --overwrite to replace it."
            ).format(path)
        )

    frame_line, sf_x, sf_y, sf_rl, sf_cl = compute_frame(options, info)
    area_lines = compute_areas(options, info, sf_x, sf_y, sf_rl, sf_cl)

    Path(config_dir).mkdir(exist_ok=True, parents=True)
    path.write_text("".join(line + "\n" for line in [frame_line, *area_lines]))
    gs.message(_("Configuration file <{}> created").format(path))


if __name__ == "__main__":
    main()
