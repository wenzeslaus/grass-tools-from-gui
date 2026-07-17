#!/usr/bin/env python3
#
############################################################################
#
# MODULE:       ps.render
# AUTHOR(S):    Vaclav Petras (with conversion logic extracted from
#               the wxGUI Cartographic Composer)
# PURPOSE:      Render a ps.map instruction file to PDF, PNG, or PostScript
# COPYRIGHT:    (C) 2026 by the GRASS Development Team
#
#               This program is free software under the GNU General Public
#               License (>=v2). Read the file COPYING that comes with GRASS
#               for details.
#
#############################################################################

# %module
# % description: Renders a ps.map instruction file to PDF, PNG, or PostScript.
# % keyword: postscript
# % keyword: map
# % keyword: printing
# % keyword: export
# %end
# %option G_OPT_F_INPUT
# % description: File containing mapping instructions
# %end
# %option G_OPT_F_OUTPUT
# % description: Name for output file
# %end
# %option
# % key: format
# % type: string
# % description: Format of the output file
# % options: pdf,png,ps,eps
# % answer: pdf
# %end
# %option
# % key: resolution
# % type: integer
# % description: Resolution of PNG output in DPI
# % answer: 300
# % options: 1-
# %end
# %flag
# % key: r
# % description: Rotate plot 90 degrees
# %end

import atexit
import sys

import grass.script as gs
from grass.exceptions import CalledModuleError

tmp_ps = None


def cleanup():
    if tmp_ps:
        gs.try_remove(tmp_ps)


def ghostscript_program_name():
    """Return the platform-specific Ghostscript executable name"""
    if sys.platform == "win32":
        import platform

        return "gswin64c" if "64" in platform.architecture()[0] else "gswin32c"
    return "gs"


def convert(command):
    """Run an external conversion command and exit on failure"""
    program = command[0]
    try:
        returncode = gs.call(command)
    except OSError as error:
        gs.fatal(
            _(
                "Program {program} is not available."
                " Please install Ghostscript first ({error})."
            ).format(program=program, error=error)
        )
    if returncode != 0:
        gs.fatal(
            _("Program {program} exited with return code {code}").format(
                program=program, code=returncode
            )
        )


def main():
    instructions = options["input"]
    output = options["output"]
    output_format = options["format"]
    resolution = options["resolution"]

    ps_map_flags = ""
    if flags["r"]:
        ps_map_flags += "r"
    if output_format == "eps":
        ps_map_flags += "e"

    if output_format in {"ps", "eps"}:
        ps_file = output
    else:
        global tmp_ps
        tmp_ps = gs.tempfile()
        ps_file = tmp_ps

    # The parser already enforced the overwrite check on the final output,
    # and the temporary file created by gs.tempfile() must always be
    # writable, so ps.map runs with overwrite enabled.
    try:
        gs.run_command(
            "ps.map",
            flags=ps_map_flags,
            input=instructions,
            output=ps_file,
            overwrite=True,
        )
    except CalledModuleError:
        gs.fatal(
            _("Rendering of instruction file <{}> with ps.map failed").format(
                instructions
            )
        )

    if output_format == "pdf":
        if sys.platform == "win32":
            # Same Ghostscript invocation as ps2pdf on other platforms,
            # spelled out because the ps2pdf wrapper script is not
            # available on Windows.
            command = [
                ghostscript_program_name(),
                "-P-",
                "-dSAFER",
                "-dCompatibilityLevel=1.4",
                "-q",
                "-P-",
                "-dNOPAUSE",
                "-dBATCH",
                "-sDEVICE=pdfwrite",
                "-dPDFSETTINGS=/prepress",
                "-r1200",
                "-sstdout=%stderr",
                "-sOutputFile=" + output,
                "-P-",
                "-dSAFER",
                "-dCompatibilityLevel=1.4",
                "-c",
                "30000000",
                "setvmthreshold",
                "-f",
                ps_file,
            ]
        else:
            command = [
                "ps2pdf",
                "-dPDFSETTINGS=/prepress",
                "-r1200",
                ps_file,
                output,
            ]
        convert(command)
    elif output_format == "png":
        # Page size is taken from the PostScript file itself
        # (ps.map includes a setpagedevice call), so only the
        # resolution needs to be specified.
        command = [
            ghostscript_program_name(),
            "-q",
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=png16m",
            "-r" + resolution,
            "-sOutputFile=" + output,
            ps_file,
        ]
        convert(command)


if __name__ == "__main__":
    options, flags = gs.parser()
    atexit.register(cleanup)
    main()
