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

## NOTES

Frames are rendered with *d.rast* using the cairo display driver; when
the cairo driver is not available, the tool falls back to the PNG driver.

The gif and avi formats and the **-t** flag require the Python Imaging
Library (Pillow). The avi format additionally requires `ffmpeg`. MP4
output is not supported directly; an MP4 video can be created from the
frames format with `ffmpeg` (e.g.,
`ffmpeg -r 5 -i basename_%03d.png output.mp4`).

This tool deliberately covers only a single STRDS rendered with *d.rast*.
Multi-layer composition, legends, and other decorations available in
*g.gui.animation* are out of scope; render such frames with custom
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

## SEE ALSO

*[d.rast](d.rast.md),
[g.gui.animation](g.gui.animation.md),
[r.out.mpeg](r.out.mpeg.md),
[t.rast.colors](t.rast.colors.md),
[t.rast.list](t.rast.list.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics

Based on the export functionality of the wxGUI Animation tool by Anna
Petrasova, Czech Technical University in Prague.
