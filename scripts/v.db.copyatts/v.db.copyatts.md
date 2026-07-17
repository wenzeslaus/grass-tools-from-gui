## DESCRIPTION

*v.db.copyatts* copies the attribute row of one feature, identified by
its category in a given layer, to one or more target categories in the
same vector map. All columns except the key column are copied; the key
column of each new row is set to the target category.

The typical use is duplicating a feature: after the geometry is copied
and a new category assigned (e.g., with *v.edit* or *v.category*), this
tool copies the attributes of the original feature to the new category.

## NOTES

The key column (by default `cat`) is taken from the database connection
of the given layer as reported by `v.db.connect -g`.

By default, the tool ends with an error when an attribute row for any
of the target categories already exists, and no rows are changed. With
the **-f** flag, existing rows of target categories are replaced by a
copy of the source row.

The row is copied inside the database with a single
`INSERT ... SELECT` statement per target category, so the values never
pass through a textual representation: NULL values, quotes in text
values, and the precision of floating-point numbers are all preserved
exactly.

The source category must have exactly one attribute row; the tool ends
with an error when the row is missing or when the table contains
multiple rows with that category. The source category cannot be one of
the target categories. Duplicate target categories are copied only
once.

The tool changes only the attribute table. It does not check that
features with the target categories exist and it does not assign
categories to features; use *v.category* or *v.edit* for that.

## EXAMPLES

Copy the attributes of the feature with category 5 to category 21:

```sh
v.db.copyatts map=mypoints from_category=5 to_category=21
```

Copy the attributes of category 5 in layer 2 to several new categories:

```sh
v.db.copyatts map=mypoints layer=2 from_category=5 to_category=21,22,23
```

Replace the existing attributes of category 3 with those of category 5:

```sh
v.db.copyatts -f map=mypoints from_category=5 to_category=3
```

## SEE ALSO

*[db.execute](db.execute.md), [v.category](v.category.md),
[v.db.connect](v.db.connect.md), [v.db.select](v.db.select.md),
[v.db.update](v.db.update.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics
