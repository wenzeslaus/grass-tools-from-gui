## DESCRIPTION

*i.gcp.manage* manages the ground control points (GCPs) of an imagery
group without a graphical session. By default, the points are stored in
the POINTS file of the group and are the same points used by
*g.gui.gcp*, *m.transform*, and *i.rectify*, so the tool can prepare,
inspect, and adjust points for image rectification in scripts. With
**points_file=control_points**, the tool manages the 3D points stored
in the CONTROL_POINTS file of the group instead, which are the points
used by *g.gui.image2target*, *i.ortho.transform*, and
*i.ortho.rectify* in orthophoto workflows.

The **operation** option selects what to do:

- **list** prints all points. In plain format, each line contains the
  point number, image east, image north, target east, target north,
  and status. With **points_file=control_points**, the image height
  follows the image coordinates and the target height follows the
  target coordinates. JSON format (**format=json**) provides the same
  values as attributes.
- **add** appends new active points. The **image_coordinates** and
  **target_coordinates** options each take one east,north pair per
  point and must contain the same number of pairs. With
  **points_file=control_points**, the **image_heights** and
  **target_heights** options each take one value per point; when
  omitted, all heights are zero (the same default the wxGUI GCP
  managers use).
- **remove** deletes the points given by the **points** option.
- **enable** and **disable** set the status of the points given by the
  **points** option to 1 (used) or 0 (ignored) without deleting them.
- **clear** removes all points from the group.
- **rms** computes the forward and backward (reverse) error of every
  active point and the total forward and backward RMS error for the
  transformation of the given **order**. In plain format, each line
  contains the point number, forward error, and backward error,
  followed by a final `total` line; inactive points are skipped. JSON
  format includes all points, with `null` errors for inactive points.
  With **points_file=control_points**, the errors come from the camera
  model of *i.ortho.transform* instead of a polynomial transformation,
  so **order** does not apply.

Points are numbered from 1 in the order in which they are stored,
which is the same numbering *g.gui.gcp* displays. After **remove**,
the remaining points are renumbered, so subsequent calls must use the
new numbers as reported by **operation=list**.

## NOTES

The points are stored in the text file
`$GISDBASE/$PROJECT/$MAPSET/group/<group>/POINTS` (or `CONTROL_POINTS`
with **points_file=control_points**). Comment lines start with `#`;
every other line is one point given as image east, image north, target
east, target north, and status (1 for used, 0 for ignored), with the
image height inserted after the image coordinates and the target
height after the target coordinates in the CONTROL_POINTS file.
*i.gcp.manage* writes each file in the exact format used by the GRASS
imagery library, so the files stay interchangeable with *g.gui.gcp*,
*m.transform*, and *i.rectify* (POINTS) and with *g.gui.image2target*,
*i.ortho.transform*, and *i.ortho.rectify* (CONTROL_POINTS).

The image coordinates are coordinates in the project (location) of the
imagery group, typically an XY project holding the unreferenced image,
while the target coordinates are coordinates in the target project set
with *i.target*. *i.gcp.manage* itself does not require the target to
be set. The group must be in the current mapset.

The per-point errors for **operation=rms** are computed by
*m.transform*, and the total RMS errors are the square root of the
mean of the squared per-point errors, matching both the *m.transform*
summary output and the wxGUI GCP manager. A transformation of
polynomial order 1, 2, or 3 requires at least 3, 6, or 10 active
points respectively; with fewer active points, **operation=rms** ends
with an error. Note that *i.rectify* has the same requirement.

With **points_file=control_points**, **operation=rms** runs
*i.ortho.transform*, which additionally requires the reference points
(REF_POINTS, created with *g.gui.photo2image*), a camera reference
file (*i.ortho.camera*), and a target project (*i.ortho.target*) for
the group. The camera model requires at least 4 active points; fewer
are enough when an initial camera position has been created with
*i.ortho.init*. Only the file management operations work without this
orthophoto setup.

In the CONTROL_POINTS file, the image coordinates are coordinates of
the source image (*i.ortho.transform* converts them to photo
coordinates through the reference points), the image height is the
elevation used by the forward transformation, and the target height is
the elevation used by the backward transformation, matching the
columns of the *g.gui.image2target* GCP list.

## EXAMPLES

Create a group for an unreferenced image and add three points in one
call (image coordinates 0,0 and 1000,0 and 0,1000):

```sh
i.group group=scan input=scan
i.gcp.manage group=scan operation=add \
    image_coordinates=0,0,1000,0,0,1000 \
    target_coordinates=635000,215000,637000,215000,635000,217000
```

List the points as JSON:

```sh
i.gcp.manage group=scan operation=list format=json
```

Report per-point errors and the total RMS error for a first-order
transformation:

```sh
i.gcp.manage group=scan operation=rms order=1
```

Ignore the second point without deleting it and remove the third one:

```sh
i.gcp.manage group=scan operation=disable points=2
i.gcp.manage group=scan operation=remove points=3
```

Add two 3D points for orthorectification with target elevations 145
and 152 (photo coordinates -75,-75 and 75,-75) and list them:

```sh
i.gcp.manage group=scan operation=add points_file=control_points \
    image_coordinates=-75,-75,75,-75 \
    target_coordinates=635000,215000,637000,215000 \
    target_heights=145,152
i.gcp.manage group=scan operation=list points_file=control_points
```

## SEE ALSO

*[g.gui.gcp](g.gui.gcp.md), [g.gui.image2target](g.gui.image2target.md),
[g.gui.photo2image](g.gui.photo2image.md), [i.group](i.group.md),
[i.ortho.photo](i.ortho.photo.md),
[i.ortho.transform](i.ortho.transform.md), [i.rectify](i.rectify.md),
[i.target](i.target.md), [m.transform](m.transform.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics
