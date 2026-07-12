## DESCRIPTION

*i.gcp.manage* manages the ground control points (GCPs) of an imagery
group without a graphical session. The points are stored in the POINTS
file of the group and are the same points used by *g.gui.gcp*,
*m.transform*, and *i.rectify*, so the tool can prepare, inspect, and
adjust points for image rectification in scripts.

The **operation** option selects what to do:

- **list** prints all points. In plain format, each line contains the
  point number, image east, image north, target east, target north,
  and status. JSON format (**format=json**) provides the same values
  as attributes.
- **add** appends new active points. The **image_coordinates** and
  **target_coordinates** options each take one east,north pair per
  point and must contain the same number of pairs.
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

Points are numbered from 1 in the order in which they are stored,
which is the same numbering *g.gui.gcp* displays. After **remove**,
the remaining points are renumbered, so subsequent calls must use the
new numbers as reported by **operation=list**.

## NOTES

The points are stored in the text file
`$GISDBASE/$PROJECT/$MAPSET/group/<group>/POINTS`. Comment lines start
with `#`; every other line is one point given as image east, image
north, target east, target north, and status (1 for used, 0 for
ignored). *i.gcp.manage* writes the file in the exact format used by
the GRASS imagery library, so the file stays interchangeable with
*g.gui.gcp*, *m.transform*, and *i.rectify*.

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

The CONTROL_POINTS file used for 3D ground control points in
orthophoto workflows (*g.gui.image2target*, *g.gui.photo2image*,
*i.ortho.photo*) has a different format and is not supported; managing
it is a possible future extension.

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

## SEE ALSO

*[g.gui.gcp](g.gui.gcp.md), [i.group](i.group.md),
[i.rectify](i.rectify.md), [i.target](i.target.md),
[m.transform](m.transform.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics
