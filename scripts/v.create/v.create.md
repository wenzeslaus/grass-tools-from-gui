## DESCRIPTION

*v.create* creates a new empty vector map in the current mapset.
Optionally, it also creates a new attribute table and connects it to
the new map in a single call.

An attribute table is created when column definitions are given with
the **columns** option or when the **-t** flag is set. The table
always contains the key column (**key** option, `cat` by default) of
type integer; with **columns**, the user-defined columns are added.
Without **columns** and without **-t**, only the vector map is created
and no table is connected to it.

The whole operation behaves atomically: if creating or connecting the
attribute table fails, the new vector map is removed again, so a
failed call does not leave a map without the requested table behind.

## NOTES

The new map is created by *v.edit* with `tool=create` and the table is
created and connected by *v.db.addtable*, so the **columns**, **key**,
and **layer** options have the same semantics as in *v.db.addtable*.
The table is named after the vector map (for **layer** higher than 1,
the layer number is appended to the table name).

An existing map of the same name is overwritten only when the
`--overwrite` flag is used.

## EXAMPLES

Create a new empty vector map without an attribute table:

```sh
v.create output=new_points
```

Create a new empty vector map with an attribute table with only the
default key column (`cat`):

```sh
v.create -t output=new_points
```

Create a new empty vector map with an attribute table with two
user-defined columns:

```sh
v.create output=new_points columns="name varchar(20),value double precision"
```

The new map can then be edited interactively, e.g., in the GUI
digitizer, or programmatically with *v.edit*.

## SEE ALSO

*[v.db.addtable](v.db.addtable.md), [v.db.connect](v.db.connect.md),
[v.edit](v.edit.md), [v.in.ascii](v.in.ascii.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics
