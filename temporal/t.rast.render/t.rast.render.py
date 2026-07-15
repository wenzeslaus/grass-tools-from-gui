#!/usr/bin/env python3

############################################################################
#
# MODULE:    t.rast.render
# AUTHOR(S): Vaclav Petras
#
# PURPOSE:   Render maps of a space time raster dataset as an animation
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

"""Render maps of a space time raster dataset as an animation"""

# %module
# % description: Renders each map of a space time raster dataset and exports the result as an animated GIF, AVI video, or image sequence.
# % keyword: temporal
# % keyword: raster
# % keyword: animation
# % keyword: export
# % keyword: visualization
# %end

# %option G_OPT_STRDS_INPUT
# %end

# %option G_OPT_F_OUTPUT
# % description: Name of the output file (gif, avi) or base name of the image sequence (frames)
# %end

# %option
# % key: format
# % type: string
# % required: no
# % multiple: no
# % options: gif,frames,avi
# % answer: gif
# % description: Format of the rendered animation
# % descriptions: gif;Animated GIF;frames;Sequence of numbered PNG images;avi;AVI video encoded by ffmpeg
# %end

# %option
# % key: size
# % type: integer
# % required: no
# % multiple: no
# % key_desc: width,height
# % answer: 640,480
# % description: Width and height of the rendered frames in pixels
# %end

# %option
# % key: fps
# % type: integer
# % required: no
# % multiple: no
# % answer: 5
# % description: Frames per second (applies to gif and avi formats)
# %end

# %option G_OPT_T_WHERE
# %end

# %option
# % key: background
# % type: string
# % required: no
# % multiple: no
# % label: Display command(s) drawn below the series map in each frame
# % description: One or more d.* commands separated by semicolons (e.g., "d.rast map=elevation_shade")
# %end

# %option
# % key: overlay
# % type: string
# % required: no
# % multiple: no
# % label: Display command(s) drawn above the series map in each frame
# % description: One or more d.* commands separated by semicolons (e.g., "d.vect map=roads; d.barscale at=1,5")
# %end

# %option
# % key: legend
# % type: string
# % required: no
# % multiple: no
# % label: d.legend command drawing a raster legend on each frame
# % description: The map of the current frame is used unless raster= is given (e.g., "d.legend at=5,50,2,5")
# %end

# %flag
# % key: t
# % description: Draw the time stamp of each map as a label on the frame
# %end

import json
import os
import pathlib
import shlex
import shutil
import sys

import grass.script as gs
from grass.exceptions import CalledModuleError


def get_maps(strds, where):
    """Return a list of (id, start time, end time) tuples for registered maps.

    The maps are ordered by start time. Times of maps with absolute time are
    returned as strings, times of maps with relative time as numbers.
    """
    kwargs = {}
    if where:
        kwargs["where"] = where
    data = json.loads(
        gs.read_command(
            "t.rast.list",
            input=strds,
            columns="id,start_time,end_time",
            order="start_time",
            format="json",
            **kwargs,
        )
    )
    return [(row["id"], row["start_time"], row["end_time"]) for row in data["data"]]


def parse_display_commands(value, option_key):
    """Parse semicolon-separated display commands into argument lists."""
    commands = []
    for command_text in value.split(";"):
        command_text = command_text.strip()
        if not command_text:
            continue
        try:
            command = shlex.split(command_text)
        except ValueError as error:
            gs.fatal(
                _("Cannot parse command <{cmd}> in option <{option}>: {error}").format(
                    cmd=command_text, option=option_key, error=error
                )
            )
        if not command[0].startswith("d."):
            gs.fatal(
                _(
                    "Option <{option}> accepts only display commands (d.*), not <{cmd}>"
                ).format(option=option_key, cmd=command[0])
            )
        commands.append(command)
    return commands


def parse_legend_command(value):
    """Parse the legend option into a d.legend argument list."""
    try:
        command = shlex.split(value)
    except ValueError as error:
        gs.fatal(
            _("Cannot parse option <{option}>: {error}").format(
                option="legend", error=error
            )
        )
    if not command or command[0] != "d.legend":
        gs.fatal(
            _("Option <{option}> must be a {tool} command, not <{value}>").format(
                option="legend", tool="d.legend", value=value
            )
        )
    return command


def frame_commands(map_id, background, overlay, legend):
    """Build the stack of display commands for the frame of one map.

    The commands are ordered from bottom to top: background commands, the
    series map itself, overlay commands, and the legend.
    """
    commands = [list(command) for command in background]
    commands.append(["d.rast", f"map={map_id}", "--quiet"])
    commands.extend(list(command) for command in overlay)
    if legend:
        command = list(legend)
        if not any(arg.startswith("raster=") for arg in command[1:]):
            command.append(f"raster={map_id}")
        commands.append(command)
    return commands


def render_frame(commands, path, env):
    """Run the display commands of one frame on top of each other.

    The first command starts a new image file; the following commands draw
    over the result of the previous ones (GRASS_RENDER_FILE_READ).
    """
    env["GRASS_RENDER_FILE"] = path
    for i, command in enumerate(commands):
        env["GRASS_RENDER_FILE_READ"] = "FALSE" if i == 0 else "TRUE"
        try:
            process = gs.Popen(command, env=env)
        except OSError:
            gs.fatal(_("Cannot find the command <{}>").format(command[0]))
        returncode = process.wait()
        if returncode != 0:
            raise CalledModuleError(command[0], " ".join(command), returncode)


def render_frames(command_stacks, width, height, tmp_dir):
    """Render each frame command stack into a PNG file and return the paths.

    Rendering uses the current computation region. The cairo driver is used
    when available with the PNG driver as a fallback; for plain raster
    rendering the two drivers produce equivalent images.
    """
    env = os.environ.copy()
    env["GRASS_RENDER_WIDTH"] = str(width)
    env["GRASS_RENDER_HEIGHT"] = str(height)
    env["GRASS_RENDER_TRANSPARENT"] = "FALSE"
    driver = "cairo"
    frame_files = []
    for i, commands in enumerate(command_stacks):
        gs.percent(i, len(command_stacks), 1)
        path = os.path.join(tmp_dir, f"frame_{i:04d}.png")
        env["GRASS_RENDER_IMMEDIATE"] = driver
        try:
            render_frame(commands, path, env)
        except CalledModuleError as error:
            if driver != "cairo":
                gs.fatal(_("Rendering with <{}> failed").format(error.code))
            driver = "png"
            env["GRASS_RENDER_IMMEDIATE"] = driver
            gs.warning(_("Cairo driver failed, falling back to the PNG driver"))
            try:
                render_frame(commands, path, env)
            except CalledModuleError as error:
                gs.fatal(_("Rendering with <{}> failed").format(error.code))
        frame_files.append(path)
    gs.percent(1, 1, 1)
    return frame_files


def format_label(start, end):
    """Format the temporal extent of one map as a label text."""
    if end is not None:
        return f"{start} - {end}"
    return str(start)


def draw_labels(frame_files, labels):
    """Draw a text label near the bottom left corner of each frame."""
    from PIL import Image, ImageDraw, ImageFont

    for path, label in zip(frame_files, labels, strict=True):
        image = Image.open(path).convert("RGB")
        draw = ImageDraw.Draw(image)
        font_size = max(12, image.height // 24)
        try:
            font = ImageFont.load_default(size=font_size)
            # Shrink the font when the label would overflow the frame width
            # (long interval labels on small frames).
            while (
                font_size > 8
                and draw.textlength(label, font=font) > image.width - font_size
            ):
                font_size -= 1
                font = ImageFont.load_default(size=font_size)
        except TypeError:
            # Pillow older than 10.1 does not support the size parameter.
            font = ImageFont.load_default()
            font_size = 11  # Approximate height of the built-in bitmap font.
        margin = font_size // 2
        position = (margin, image.height - font_size - margin)
        bbox = draw.textbbox(position, label, font=font)
        pad = max(2, font_size // 6)
        # Draw a background rectangle to keep the label readable on any map.
        draw.rectangle(
            (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
            fill="white",
        )
        draw.text(position, label, fill="black", font=font)
        image.save(path)


def load_images(frame_files):
    """Load rendered frames as PIL images for the grass.imaging encoders."""
    from PIL import Image

    return [Image.open(path).convert("RGB") for path in frame_files]


def export_frames(frame_files, output):
    """Copy rendered frames to numbered PNG files based on the output name."""
    base, extension = os.path.splitext(output)
    if extension.lower() != ".png":
        base = output
    directory = os.path.dirname(os.path.abspath(base))
    pathlib.Path(directory).mkdir(exist_ok=True, parents=True)
    digits = max(3, len(str(len(frame_files))))
    for i, path in enumerate(frame_files, start=1):
        shutil.copyfile(path, f"{base}_{i:0{digits}d}.png")


def require_pil():
    """Exit with an error when PIL is not importable."""
    try:
        import PIL.Image  # noqa: F401
    except ImportError:
        gs.fatal(
            _(
                "The Python Imaging Library (Pillow) is required"
                " for the requested operation but it could not be imported"
            )
        )


def main(options, flags):
    output = options["output"]
    output_format = options["format"]
    draw_time_labels = flags["t"]

    fps = int(options["fps"])
    if fps < 1:
        gs.fatal(_("Option <{}> must be a positive number").format("fps"))
    try:
        width, height = (int(value) for value in options["size"].split(","))
    except ValueError:
        gs.fatal(_("Option <{}> requires two values: width,height").format("size"))
    if width < 1 or height < 1:
        gs.fatal(_("Width and height in option <{}> must be positive").format("size"))

    if output_format in {"gif", "avi"} or draw_time_labels:
        require_pil()
    if output_format == "avi" and not shutil.which("ffmpeg"):
        gs.fatal(_("The ffmpeg tool is required for the avi format but was not found"))

    background = parse_display_commands(options["background"], "background")
    overlay = parse_display_commands(options["overlay"], "overlay")
    legend = parse_legend_command(options["legend"]) if options["legend"] else None

    maps = get_maps(options["input"], options["where"])
    if not maps:
        gs.fatal(
            _("Space time raster dataset <{}> contains no maps to render").format(
                options["input"]
            )
        )

    tmp_dir = gs.tempdir()
    try:
        gs.message(_("Rendering {} frames...").format(len(maps)))
        frame_files = render_frames(
            [
                frame_commands(map_id, background, overlay, legend)
                for map_id, start, end in maps
            ],
            width,
            height,
            tmp_dir,
        )
        if draw_time_labels:
            draw_labels(
                frame_files, [format_label(start, end) for map_id, start, end in maps]
            )
        gs.message(_("Writing output..."))
        if output_format == "frames":
            export_frames(frame_files, output)
        elif output_format == "gif":
            from grass.imaging import writeGif

            writeGif(
                filename=output,
                images=load_images(frame_files),
                duration=1.0 / fps,
                repeat=True,
            )
        else:
            from grass.imaging import writeAvi

            try:
                writeAvi(
                    filename=output,
                    images=load_images(frame_files),
                    duration=1.0 / fps,
                )
            except RuntimeError:
                # The encoder already printed the ffmpeg output.
                gs.fatal(_("Encoding of the AVI file with ffmpeg failed"))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(*gs.parser()))
