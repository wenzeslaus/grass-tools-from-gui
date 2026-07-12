#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       v.create
# AUTHOR(S):    Vaclav Petras
# PURPOSE:      Create a new empty vector map, optionally with an
#               attribute table
# COPYRIGHT:    (C) 2026 by Vaclav Petras and the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Creates a new empty vector map, optionally with an attribute table.
# % keyword: vector
# % keyword: editing
# % keyword: attribute table
# %end
# %option G_OPT_V_OUTPUT
# %end
# %option
# % key: columns
# % type: string
# % label: Name and type of the new column(s) ('name type [,name type, ...]')
# % description: Types depend on database backend, but all support VARCHAR(), INT, DOUBLE PRECISION and DATE. Example: 'label varchar(250), value integer'
# % required: no
# % multiple: yes
# % key_desc: name type
# % guisection: Table
# %end
# %option G_OPT_DB_KEYCOLUMN
# % guisection: Table
# %end
# %option
# % key: layer
# % type: integer
# % description: Layer number to which the new attribute table is connected
# % answer: 1
# % required: no
# % guisection: Table
# %end
# %option
# % key: type
# % type: string
# % options: point,line,boundary
# % answer: point
# % required: no
# % label: Feature type of the new layer in external output formats
# % description: A new OGR or PostGIS layer (output format set by v.external.out) stores a single feature type; ignored for the native format
# %end
# %flag
# % key: t
# % description: Create attribute table even when no columns are specified (table contains only the key column)
# % guisection: Table
# %end

import os
import sys

import grass.script as gs
from grass.exceptions import CalledModuleError


def external_layers(dsn):
    """Return names of layers in an external OGR datasource.

    A datasource which does not exist yet (or cannot be opened) has no
    layers to collide with, so an empty list is returned in that case,
    with the error output discarded (a datasource which is truly broken
    fails later in v.edit with its own error message).
    """
    process = gs.pipe_command("v.external", flags="l", input=dsn, stderr=gs.PIPE)
    output = process.communicate()[0]
    if process.returncode != 0:
        return []
    return gs.decode(output).splitlines()


def main():
    options, flags = gs.parser()
    output = options["output"]
    columns = options["columns"]
    create_table = bool(columns) or flags["t"]

    external = gs.parse_command("v.external.out", flags="g")
    is_native = external["format"] == "native"

    create_args = {}
    if not is_native:
        if create_table:
            gs.fatal(
                _(
                    "Creating an attribute table (columns or -t) is not"
                    " supported for the external output format {} set with"
                    " v.external.out (the new layer gets a table managed by"
                    " the external format)"
                ).format(external["format"])
            )
        # An external layer stores a single feature type, so v.edit
        # needs one; for the native format, v.edit ignores type.
        create_args["type"] = options["type"]
        # v.edit does not check for an existing layer in the external
        # datasource and would replace it, so check here.
        if not gs.overwrite() and output in external_layers(external["dsn"]):
            gs.fatal(
                _(
                    "Vector map <{}> already exists in the external"
                    " datasource. To overwrite, use the --overwrite flag"
                ).format(output)
            )

    try:
        gs.run_command("v.edit", map=output, tool="create", quiet=True, **create_args)
    except CalledModuleError:
        gs.fatal(_("Unable to create vector map <{}>").format(output))

    if (
        not is_native
        and not gs.find_file(output, element="vector", mapset=gs.gisenv()["MAPSET"])[
            "name"
        ]
    ):
        # v.edit registers the new external layer in the mapset itself;
        # this is a safeguard for backends where it does not, mirroring
        # the GUI new-vector-map dialog.
        try:
            gs.run_command(
                "v.external", input=external["dsn"], layer=output, quiet=True
            )
        except CalledModuleError:
            gs.fatal(
                _("Unable to register vector map <{}> in the mapset").format(output)
            )

    if create_table:
        # The map is empty, so v.db.addtable's warning about overwriting
        # values in the key column does not apply. Suppress messages and
        # warnings for the subprocesses; errors are still reported.
        env = os.environ.copy()
        env["GRASS_VERBOSE"] = "-1"
        addtable_args = {"key": options["key"], "layer": options["layer"]}
        if columns:
            addtable_args["columns"] = columns
        try:
            gs.run_command("v.db.addtable", map=output, env=env, **addtable_args)
        except CalledModuleError:
            # Remove the new map so that either the complete map with its
            # table is created or nothing is.
            gs.run_command(
                "g.remove", type="vector", name=output, flags="f", quiet=True
            )
            gs.fatal(
                _("Unable to create attribute table for vector map <{}>").format(output)
            )

    # Record this command (rather than only the underlying ones) in the
    # vector map history.
    gs.vector_history(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
