#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       i.gcp.manage
# AUTHOR(S):    Vaclav Petras
# PURPOSE:      Manage ground control points (GCPs) of an imagery group
# COPYRIGHT:    (C) 2026 by Vaclav Petras and the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Manages ground control points (GCPs) of an imagery group.
# % keyword: imagery
# % keyword: GCP
# % keyword: ground control points
# % keyword: georectification
# % keyword: orthorectify
# %end
# %option G_OPT_I_GROUP
# %end
# %option
# % key: operation
# % type: string
# % required: yes
# % options: list,add,remove,enable,disable,clear,rms
# % description: Operation to be performed
# % descriptions: list;List points;add;Add new points;remove;Remove points;enable;Mark points as active (status 1);disable;Mark points as inactive (status 0);clear;Remove all points;rms;Compute per-point and total RMS errors
# %end
# %option
# % key: points_file
# % type: string
# % required: no
# % options: points,control_points
# % answer: points
# % label: Points file of the group to manage
# % description: POINTS holds 2D points for georectification, CONTROL_POINTS holds 3D points for orthorectification
# % descriptions: points;2D points in the POINTS file;control_points;3D points in the CONTROL_POINTS file
# %end
# %option G_OPT_M_COORDS
# % key: image_coordinates
# % multiple: yes
# % label: Image (source) coordinates of new points
# % description: One east,north pair per point (used by operation=add)
# %end
# %option G_OPT_M_COORDS
# % key: target_coordinates
# % multiple: yes
# % label: Target coordinates of new points
# % description: One east,north pair per point (used by operation=add)
# %end
# %option
# % key: image_heights
# % type: double
# % required: no
# % multiple: yes
# % label: Image (source) heights of new points
# % description: One height per point, defaults to 0 (used by operation=add with points_file=control_points)
# %end
# %option
# % key: target_heights
# % type: double
# % required: no
# % multiple: yes
# % label: Target heights (elevations) of new points
# % description: One height per point, defaults to 0 (used by operation=add with points_file=control_points)
# %end
# %option
# % key: points
# % type: integer
# % required: no
# % multiple: yes
# % description: Point numbers as reported by operation=list, first point is 1 (used by operation=remove, enable, and disable)
# %end
# %option
# % key: order
# % type: integer
# % required: no
# % options: 1-3
# % answer: 1
# % description: Transformation polynomial order (used by operation=rms with points_file=points)
# %end
# %option G_OPT_F_FORMAT
# % guisection: Print
# %end

import json
import math
from pathlib import Path

import grass.script as gs

# Minimum number of active points required by each polynomial order
# (same limits as in I_compute_georef_equations and the wxGUI GCP manager).
MIN_POINTS = {1: 3, 2: 6, 3: 10}

# Minimum number of active 3D points required by the ortho camera model
# unless an initial camera position exists (see I_compute_ortho_equations
# in imagery/i.ortho.photo/lib/orthoref.c).
ORTHO_MIN_POINTS = 4

# File name in the group directory for each points_file option value.
FILE_NAMES = {"points": "POINTS", "control_points": "CONTROL_POINTS"}

# Coordinate attributes of one point, in file column order, for each
# points_file option value (the last file column, status, is not listed).
POINT_KEYS = {
    "points": ("image_east", "image_north", "target_east", "target_north"),
    "control_points": (
        "image_east",
        "image_north",
        "image_height",
        "target_east",
        "target_north",
        "target_height",
    ),
}


def points_file_path(group, file_name):
    """Return the path of a points file of a group in the current mapset.

    Calls gs.fatal() when the group is not in the current mapset or
    does not exist. The points file itself may not exist yet.
    """
    name = group
    env = gs.gisenv()
    if "@" in group:
        name, mapset = group.split("@", maxsplit=1)
        if mapset != env["MAPSET"]:
            gs.fatal(
                _(
                    "Group <{group}> is not in the current mapset ({mapset}) "
                    "and only groups in the current mapset can be managed"
                ).format(group=group, mapset=env["MAPSET"])
            )
    group_dir = (
        Path(env["GISDBASE"]) / env["LOCATION_NAME"] / env["MAPSET"] / "group" / name
    )
    if not group_dir.is_dir():
        gs.fatal(_("Group <{}> not found in the current mapset").format(name))
    return group_dir / file_name


def read_points(path, keys):
    """Read points from a points file into a list of dictionaries.

    The keys parameter gives the coordinate attributes in file column
    order. A missing file is treated as an empty list of points which
    is how a group without any points stored yet is represented.
    """
    points = []
    if not path.exists():
        return points
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        try:
            if len(fields) != len(keys) + 1:
                raise ValueError
            values = [float(value) for value in fields[:-1]]
            status = int(fields[-1])
        except ValueError:
            gs.fatal(
                _("Invalid point on line {line_number} of file {path}: {line}").format(
                    line_number=line_number, path=path, line=line
                )
            )
        point = dict(zip(keys, values, strict=True))
        point["status"] = status
        points.append(point)
    return points


def write_points(path, points, points_file):
    """Write points to a POINTS or CONTROL_POINTS file.

    The headers and the line formats replicate I_write_control_points()
    from lib/imagery and I_write_con_points() from the i.ortho.photo
    library so that the resulting file is byte-identical to what the
    C tools (re)write.
    """
    if points_file == "control_points":
        lines = [
            "# {:>7s} {:>15s} {:>30s} {:>15s} {:>9s} status".format(
                "", "photo", "", "control", ""
            ),
            "# {:>15s} {:>15s}  {:>15s} {:>15s} {:>15s} {:>15s}   (1=ok)".format(
                "x", "y", "-cfl", "east", "north", "elev."
            ),
            "#",
        ]
        line_format = (
            "  {image_east:15f} {image_north:15f} {image_height:15f}"
            " {target_east:15f} {target_north:15f} {target_height:15f}"
            " {status:4d}"
        )
    else:
        lines = [
            "# {:7s} {:>15s} {:>15s} {:>15s} {:>9s} status".format(
                "", "image", "", "target", ""
            ),
            "# {:>15s} {:>15s} {:>15s} {:>15s}   (1=ok)".format(
                "east", "north", "east", "north"
            ),
            "#",
        ]
        line_format = (
            "  {image_east:15f} {image_north:15f}"
            " {target_east:15f} {target_north:15f} {status:4d}"
        )
    for point in points:
        lines.append(line_format.format(**point))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_coord_pairs(option_value, option_key):
    """Parse a list of east,north pairs from a comma-separated option value"""
    values = [float(value) for value in option_value.split(",")]
    # The parser guarantees full east,north pairs (key_desc), so this
    # is just a safety net.
    if len(values) % 2:
        gs.fatal(
            _("Option {option} requires complete east,north pairs").format(
                option=option_key
            )
        )
    return [(values[i], values[i + 1]) for i in range(0, len(values), 2)]


def parse_heights(option_value, option_key, count):
    """Parse one height per point from a comma-separated option value.

    An empty option value means zero height for every point, which is
    also what the wxGUI GCP managers use for points without a height.
    """
    if not option_value:
        return [0.0] * count
    heights = [float(value) for value in option_value.split(",")]
    if len(heights) != count:
        gs.fatal(
            _(
                "Option {option} must have one height per point "
                "({heights} heights versus {points} points)"
            ).format(option=option_key, heights=len(heights), points=count)
        )
    return heights


def parse_point_numbers(option_value, operation, count):
    """Parse and validate 1-based point numbers from the points option"""
    if not option_value:
        gs.fatal(
            _("Operation <{operation}> requires the points option").format(
                operation=operation
            )
        )
    numbers = sorted({int(value) for value in option_value.split(",")})
    for number in numbers:
        if number < 1 or number > count:
            gs.fatal(
                _(
                    "Point number {number} is out of range: "
                    "group has {count} points (numbered from 1)"
                ).format(number=number, count=count)
            )
    return numbers


def add_points(path, points, points_file, options):
    """Append new active points given by the coordinate and height options"""
    image_coordinates = options["image_coordinates"]
    target_coordinates = options["target_coordinates"]
    if not image_coordinates or not target_coordinates:
        gs.fatal(
            _(
                "Operation <add> requires both image_coordinates "
                "and target_coordinates options"
            )
        )
    image_pairs = parse_coord_pairs(image_coordinates, "image_coordinates")
    target_pairs = parse_coord_pairs(target_coordinates, "target_coordinates")
    if len(image_pairs) != len(target_pairs):
        gs.fatal(
            _(
                "Options image_coordinates and target_coordinates must have "
                "the same number of east,north pairs ({image} versus {target})"
            ).format(image=len(image_pairs), target=len(target_pairs))
        )
    if points_file == "control_points":
        image_heights = parse_heights(
            options["image_heights"], "image_heights", len(image_pairs)
        )
        target_heights = parse_heights(
            options["target_heights"], "target_heights", len(target_pairs)
        )
    else:
        for option_key in ("image_heights", "target_heights"):
            if options[option_key]:
                gs.fatal(
                    _(
                        "Option {option} applies only to points_file=control_points"
                    ).format(option=option_key)
                )
    for index, ((image_east, image_north), (target_east, target_north)) in enumerate(
        zip(image_pairs, target_pairs, strict=True)
    ):
        if points_file == "control_points":
            point = {
                "image_east": image_east,
                "image_north": image_north,
                "image_height": image_heights[index],
                "target_east": target_east,
                "target_north": target_north,
                "target_height": target_heights[index],
                "status": 1,
            }
        else:
            point = {
                "image_east": image_east,
                "image_north": image_north,
                "target_east": target_east,
                "target_north": target_north,
                "status": 1,
            }
        points.append(point)
    write_points(path, points, points_file)
    gs.message(
        _("Points added: {new} (total: {total})").format(
            new=len(image_pairs), total=len(points)
        )
    )


def list_points(points, keys, output_format):
    """Print the point list in plain or JSON format"""
    if output_format == "json":
        result = {"points": []}
        for number, point in enumerate(points, start=1):
            result["points"].append({"number": number, **point})
        print(json.dumps(result, indent=4))
        return
    for number, point in enumerate(points, start=1):
        values = " ".join(str(point[key]) for key in keys)
        print(f"{number} {values} {point['status']}")


def compute_rms(group, path, points, order, output_format, points_file):
    """Compute per-point and total RMS errors and print them.

    Runs m.transform (POINTS) or i.ortho.transform (CONTROL_POINTS)
    which reads the points file of the group and reports the forward
    and reverse (backward) error for each active point. The total RMS
    errors are computed from the per-point values in the same way as
    m.transform computes the RMS values in its summary output (and as
    the wxGUI GCP managers do).
    """
    active = [point for point in points if point["status"] > 0]
    if points_file == "control_points":
        if order != 1:
            gs.fatal(
                _(
                    "Option order applies only to points_file=points "
                    "(the camera model used with CONTROL_POINTS has "
                    "no polynomial order)"
                )
            )
        # I_compute_ortho_equations() adjusts the camera position only
        # with at least 4 active points; with fewer it needs the initial
        # camera position from i.ortho.init (the INIT_EXP group file).
        if len(active) < ORTHO_MIN_POINTS and not (path.parent / "INIT_EXP").exists():
            gs.fatal(
                _(
                    "Insufficient active points for the camera model: "
                    "{active} active, {required} required (fewer need an "
                    "initial camera position created with i.ortho.init)"
                ).format(active=len(active), required=ORTHO_MIN_POINTS)
            )
        transform_tool = "i.ortho.transform"
        output = gs.read_command(transform_tool, group=group, errors="fatal")
    else:
        required = MIN_POINTS[order]
        if len(active) < required:
            gs.fatal(
                _(
                    "Insufficient active points for transformation order {order}: "
                    "{active} active, {required} required"
                ).format(order=order, active=len(active), required=required)
            )
        transform_tool = "m.transform"
        output = gs.read_command(
            transform_tool, group=group, order=order, errors="fatal"
        )
    errors = [line.split() for line in output.splitlines() if line.strip()]
    if len(errors) != len(active):
        gs.fatal(
            _(
                "Unexpected {tool} output: {lines} error lines "
                "for {active} active points"
            ).format(tool=transform_tool, lines=len(errors), active=len(active))
        )
    error_iterator = iter(errors)
    for point in points:
        if point["status"] > 0:
            forward, backward = next(error_iterator)
            point["forward"] = float(forward)
            point["backward"] = float(backward)
        else:
            point["forward"] = None
            point["backward"] = None
    count = len(active)
    forward_rms = math.sqrt(sum(point["forward"] ** 2 for point in active) / count)
    backward_rms = math.sqrt(sum(point["backward"] ** 2 for point in active) / count)
    if output_format == "json":
        result = {}
        if points_file == "points":
            # The camera model used with CONTROL_POINTS has no order.
            result["order"] = order
        result["active"] = count
        result["points"] = []
        for number, point in enumerate(points, start=1):
            result["points"].append({"number": number, **point})
        result["forward_rms"] = forward_rms
        result["backward_rms"] = backward_rms
        print(json.dumps(result, indent=4))
        return
    for number, point in enumerate(points, start=1):
        if point["status"] > 0:
            print(f"{number} {point['forward']:.6f} {point['backward']:.6f}")
    print(f"total {forward_rms:.6f} {backward_rms:.6f}")


def main():
    options, unused_flags = gs.parser()
    group = options["group"]
    operation = options["operation"]
    points_file = options["points_file"]

    path = points_file_path(group, FILE_NAMES[points_file])
    keys = POINT_KEYS[points_file]
    points = read_points(path, keys)

    if operation == "list":
        list_points(points, keys, options["format"])
    elif operation == "add":
        add_points(path, points, points_file, options)
    elif operation in {"remove", "enable", "disable"}:
        numbers = parse_point_numbers(options["points"], operation, len(points))
        if operation == "remove":
            for number in reversed(numbers):
                del points[number - 1]
            message = _("Points removed: {changed} (remaining: {total})")
        else:
            status = 1 if operation == "enable" else 0
            for number in numbers:
                points[number - 1]["status"] = status
            if operation == "enable":
                message = _("Points enabled: {changed} (total: {total})")
            else:
                message = _("Points disabled: {changed} (total: {total})")
        write_points(path, points, points_file)
        gs.message(message.format(changed=len(numbers), total=len(points)))
    elif operation == "clear":
        write_points(path, [], points_file)
        gs.message(_("Removed all points from group <{}>").format(group))
    elif operation == "rms":
        compute_rms(
            group, path, points, int(options["order"]), options["format"], points_file
        )


if __name__ == "__main__":
    main()
