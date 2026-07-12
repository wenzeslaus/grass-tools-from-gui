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
# % description: Transformation polynomial order (used by operation=rms)
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


def points_file_path(group):
    """Return the path of the POINTS file of a group in the current mapset.

    Calls gs.fatal() when the group is not in the current mapset or
    does not exist. The POINTS file itself may not exist yet.
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
    return group_dir / "POINTS"


def read_points(path):
    """Read points from a POINTS file into a list of dictionaries.

    A missing file is treated as an empty list of points which is how
    a group without any points stored yet is represented.
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
            if len(fields) != 5:
                raise ValueError
            values = [float(value) for value in fields[:4]]
            status = int(fields[4])
        except ValueError:
            gs.fatal(
                _("Invalid point on line {line_number} of file {path}: {line}").format(
                    line_number=line_number, path=path, line=line
                )
            )
        points.append(
            {
                "image_east": values[0],
                "image_north": values[1],
                "target_east": values[2],
                "target_north": values[3],
                "status": status,
            }
        )
    return points


def write_points(path, points):
    """Write points to a POINTS file.

    The header and the line format replicate I_write_control_points()
    from lib/imagery so that the resulting file is byte-identical to
    what m.transform and other C tools (re)write.
    """
    lines = [
        "# {:7s} {:>15s} {:>15s} {:>15s} {:>9s} status".format(
            "", "image", "", "target", ""
        ),
        "# {:>15s} {:>15s} {:>15s} {:>15s}   (1=ok)".format(
            "east", "north", "east", "north"
        ),
        "#",
    ]
    for point in points:
        lines.append(
            "  {:15f} {:15f} {:15f} {:15f} {:4d}".format(
                point["image_east"],
                point["image_north"],
                point["target_east"],
                point["target_north"],
                point["status"],
            )
        )
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


def add_points(path, points, image_coordinates, target_coordinates):
    """Append new active points given by two coordinate pair lists"""
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
    for (image_east, image_north), (target_east, target_north) in zip(
        image_pairs, target_pairs, strict=True
    ):
        points.append(
            {
                "image_east": image_east,
                "image_north": image_north,
                "target_east": target_east,
                "target_north": target_north,
                "status": 1,
            }
        )
    write_points(path, points)
    gs.message(
        _("Points added: {new} (total: {total})").format(
            new=len(image_pairs), total=len(points)
        )
    )


def list_points(points, output_format):
    """Print the point list in plain or JSON format"""
    if output_format == "json":
        result = {"points": []}
        for number, point in enumerate(points, start=1):
            result["points"].append({"number": number, **point})
        print(json.dumps(result, indent=4))
        return
    for number, point in enumerate(points, start=1):
        print(
            f"{number} {point['image_east']} {point['image_north']}"
            f" {point['target_east']} {point['target_north']} {point['status']}"
        )


def compute_rms(group, points, order, output_format):
    """Compute per-point and total RMS errors and print them.

    Runs m.transform which reads the POINTS file of the group and
    reports the forward and reverse (backward) error for each active
    point. The total RMS errors are computed from the per-point values
    in the same way as m.transform computes the RMS values in its
    summary output (and as the wxGUI GCP manager does).
    """
    active = [point for point in points if point["status"] > 0]
    required = MIN_POINTS[order]
    if len(active) < required:
        gs.fatal(
            _(
                "Insufficient active points for transformation order {order}: "
                "{active} active, {required} required"
            ).format(order=order, active=len(active), required=required)
        )
    output = gs.read_command("m.transform", group=group, order=order, errors="fatal")
    errors = [line.split() for line in output.splitlines() if line.strip()]
    if len(errors) != len(active):
        gs.fatal(
            _(
                "Unexpected m.transform output: {lines} error lines "
                "for {active} active points"
            ).format(lines=len(errors), active=len(active))
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
        result = {"order": order, "active": count, "points": []}
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

    path = points_file_path(group)
    points = read_points(path)

    if operation == "list":
        list_points(points, options["format"])
    elif operation == "add":
        add_points(
            path, points, options["image_coordinates"], options["target_coordinates"]
        )
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
        write_points(path, points)
        gs.message(message.format(changed=len(numbers), total=len(points)))
    elif operation == "clear":
        write_points(path, [])
        gs.message(_("Removed all points from group <{}>").format(group))
    elif operation == "rms":
        compute_rms(group, points, int(options["order"]), options["format"])


if __name__ == "__main__":
    main()
