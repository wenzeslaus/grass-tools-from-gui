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
# %flag
# % key: t
# % description: Create attribute table even when no columns are specified (table contains only the key column)
# % guisection: Table
# %end

import os
import sys

import grass.script as gs
from grass.exceptions import CalledModuleError


def main():
    options, flags = gs.parser()
    output = options["output"]
    columns = options["columns"]
    create_table = bool(columns) or flags["t"]

    try:
        gs.run_command("v.edit", map=output, tool="create", quiet=True)
    except CalledModuleError:
        gs.fatal(_("Unable to create vector map <{}>").format(output))

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
