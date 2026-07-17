# t.rast.render

## DESCRIPTION

*t.rast.render* renders each raster map registered in a space time raster
dataset (STRDS) as one image frame and exports the frames as an animated
GIF, an AVI video, or a sequence of numbered PNG images. It provides a
scripted, headless alternative to the export functionality of the wxGUI
Animation tool (*g.gui.animation*).

The maps are rendered in the order of their start time using the current
computation region, so use *g.region* to set the rendered extent and
*r.colors* to set the color tables before running the tool.

The **format** option selects the output:

- **gif**: an animated GIF written to the file given by **output**
- **avi**: an AVI video (MPEG-4 codec) written to the file given by
  **output**; requires the `ffmpeg` command line tool
- **frames**: a sequence of PNG images; **output** is used as a base name
  and frames are written as `<output>_001.png`, `<output>_002.png`, etc.
  (a trailing `.png` extension in **output** is dropped)

The **fps** option sets the number of frames per second for the gif and
avi formats; it is ignored for frames. The **size** option sets the pixel
dimensions of each frame. With the **-t** flag, the temporal extent of
each map (start time, or start and end time for interval data) is drawn
as a label near the bottom left corner of the frame. The **where** option
limits the rendered maps with an SQL WHERE condition applied to the
temporal database (e.g., `start_time >= '2020-01-01'`).

Each frame can be composed of multiple layers. The **background** option
takes one or more display commands (semicolon separated) rendered below
the series map, so their output is visible where the series map has no
data (e.g., a hillshade or country borders as context). The **overlay**
option works the same way for commands rendered above the series map
(e.g., *d.vect* overlays or *d.barscale*). Only display commands (tools
with the `d.` prefix) are accepted, and the commands are the same for
every frame.

The **legend** option adds a raster legend to each frame. It takes a full
*d.legend* command; when the command does not set the **raster** option,
the series map of the current frame is used, so the legend follows the
data of each frame. Set **raster** (or the *d.legend* **range** option)
explicitly to keep the legend identical across frames.

## NOTES

Frames are rendered with *d.rast* using the cairo display driver; when
the cairo driver is not available, the tool falls back to the PNG driver.
The layers of one frame are drawn into a single image in order
(background commands, the series map, overlay commands, legend), so
overlapping non-transparent output of a higher layer covers the layers
below it.

Commands in the **background** and **overlay** options are separated by
semicolons and their arguments by whitespace; argument values containing
spaces must be quoted within the command (e.g.,
`overlay="d.vect map=roads where=\"type = 'primary'\""`), and a
semicolon inside an argument value cannot be used.

The gif and avi formats and the **-t** flag require the Python Imaging
Library (Pillow). The avi format additionally requires `ffmpeg`. MP4
output is not supported directly; an MP4 video can be created from the
frames format with `ffmpeg` (e.g.,
`ffmpeg -r 5 -i basename_%03d.png output.mp4`).

This tool covers a single STRDS rendered with *d.rast*, optionally
combined with background and overlay display commands and a legend as
described above. The 3D view animation of *g.gui.animation* (rendering
with *m.nviz.image*) remains out of scope: it requires an OpenGL
rendering context, which is not available in the headless environments
this tool targets and cannot be exercised by automated tests. Features
beyond that (multiple animations side by side, image and free-text
decorations) are also not covered; render such frames with custom
scripting using the display tools instead.

## EXAMPLES

Create an animated GIF from a precipitation time series with time stamp
labels:

```sh
g.region raster=precip_1 -p
t.rast.render -t input=precipitation output=precipitation.gif fps=2
```

Export an AVI video at a higher resolution:

```sh
t.rast.render input=precipitation output=precipitation.avi format=avi \
    size=1280,720 fps=10
```

Export individual frames for one year only:

```sh
t.rast.render input=precipitation output=frames/precip format=frames \
    where="start_time >= '2020-01-01' and start_time < '2021-01-01'"
```

Render precipitation over a hillshade with roads and a legend on top:

```sh
t.rast.render input=precipitation output=precipitation.gif \
    background="d.rast map=elevation_shade" \
    overlay="d.vect map=roads color=black; d.barscale at=1,5" \
    legend="d.legend at=5,50,2,5 range=0,500"
```

## SEE ALSO

*[d.legend](d.legend.md),
[d.rast](d.rast.md),
[g.gui.animation](g.gui.animation.md),
[r.out.mpeg](r.out.mpeg.md),
[t.rast.colors](t.rast.colors.md),
[t.rast.list](t.rast.list.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics

Based on the export functionality of the wxGUI Animation tool by Anna
Petrasova, Czech Technical University in Prague.
