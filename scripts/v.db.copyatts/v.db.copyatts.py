#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       v.db.copyatts
# AUTHOR(S):    Vaclav Petras
# PURPOSE:      Copy the attribute row of one category to other categories
#               in the same vector map
# COPYRIGHT:    (C) 2026 by Vaclav Petras and the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Copies the attribute row of one category to other categories in the same vector map.
# % keyword: vector
# % keyword: attribute table
# % keyword: database
# % keyword: category
# %end
# %option G_OPT_V_MAP
# %end
# %option G_OPT_V_FIELD
# %end
# %option G_OPT_V_CAT
# % key: from_category
# % required: yes
# % description: Category of the feature to copy attributes from
# %end
# %option G_OPT_V_CAT
# % key: to_category
# % multiple: yes
# % required: yes
# % description: Categories to copy attributes to
# %end
# %flag
# % key: f
# % description: Replace existing attribute rows of target categories
# %end

import sys

import grass.script as gs


def main():
    options, flags = gs.parser()
    vector = options["map"]
    try:
        layer = int(options["layer"])
    except ValueError:
        gs.fatal(
            _("Layer must be given as an integer, not <{}>").format(options["layer"])
        )
    from_category = int(options["from_category"])
    # Remove duplicate targets while preserving order.
    to_categories = list(
        dict.fromkeys(int(cat) for cat in options["to_category"].split(","))
    )
    force = flags["f"]

    if from_category in to_categories:
        gs.fatal(
            _("Source category {} cannot also be a target category").format(
                from_category
            )
        )

    mapset = gs.gisenv()["MAPSET"]
    if not gs.find_file(vector, element="vector", mapset=mapset)["file"]:
        gs.fatal(_("Vector map <{}> not found in current mapset").format(vector))

    try:
        connection = gs.vector_db(vector)[layer]
    except KeyError:
        gs.fatal(
            _(
                "There is no table connected to layer <{layer}> of vector map <{map}>"
            ).format(layer=layer, map=vector)
        )
    table = connection["table"]
    database = connection["database"]
    driver = connection["driver"]
    key = connection["key"]

    def select_values(sql):
        """Run a query in the table's database and return lines of values."""
        return gs.read_command(
            "db.select", flags="c", sql=sql, database=database, driver=driver
        ).splitlines()

    source_rows = int(
        select_values(f"SELECT count(*) FROM {table} WHERE {key} = {from_category}")[0]
    )
    if source_rows == 0:
        gs.fatal(
            _("No attribute row for category {category} in table <{table}>").format(
                category=from_category, table=table
            )
        )
    if source_rows > 1:
        gs.fatal(
            _(
                "Multiple attribute rows for category {category} in"
                " table <{table}>; the copy would be ambiguous"
            ).format(category=from_category, table=table)
        )

    target_list = ",".join(str(cat) for cat in to_categories)
    existing = [
        int(value)
        for value in select_values(
            f"SELECT {key} FROM {table} WHERE {key} IN ({target_list})"
        )
    ]
    if existing and not force:
        gs.fatal(
            _(
                "Attribute rows for target categories ({categories}) already"
                " exist in table <{table}> (use -f to replace them)"
            ).format(categories=",".join(str(cat) for cat in existing), table=table)
        )

    columns = [
        name for name in gs.vector_columns(vector, layer) if name.lower() != key.lower()
    ]
    # Copying with INSERT ... SELECT keeps the values inside the database,
    # so NULLs, text with quotes, and numeric precision are preserved
    # without any client-side value formatting.
    statements = [f"DELETE FROM {table} WHERE {key} = {cat}" for cat in existing]
    if columns:
        column_list = ", ".join(columns)
        statements.extend(
            f"INSERT INTO {table} ({key}, {column_list})"
            f" SELECT {cat}, {column_list} FROM {table}"
            f" WHERE {key} = {from_category}"
            for cat in to_categories
        )
    else:
        # The table has only the key column, so only new keys are inserted.
        statements.extend(
            f"INSERT INTO {table} ({key})"
            f" SELECT {cat} FROM {table} WHERE {key} = {from_category}"
            for cat in to_categories
        )
    gs.write_command(
        "db.execute",
        input="-",
        database=database,
        driver=driver,
        stdin=";\n".join(statements),
    )

    gs.vector_history(vector)
    gs.verbose(
        _("Copied attributes of category {source} to {count} categories").format(
            source=from_category, count=len(to_categories)
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
