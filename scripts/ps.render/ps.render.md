## DESCRIPTION

*ps.render* renders a *[ps.map](ps.map.md)* mapping instruction file
directly to PDF, PNG, PostScript (PS), or Encapsulated PostScript (EPS).
It runs *ps.map* to produce PostScript and, for PDF and PNG output,
converts the result with Ghostscript, so a separate conversion step is
not needed.

The **input** option takes a file with *ps.map* mapping instructions and
the **output** option is the file to create. The **format** option
selects the output format (default is `pdf`). The **resolution** option
sets the resolution in DPI for PNG output (default is 300); it has no
effect on the other formats. The **-r** flag is passed through to
*ps.map* and rotates the plot 90 degrees on the page.

## NOTES

PDF and PNG output require Ghostscript. On Linux and macOS, PDF
conversion uses the *ps2pdf* script and PNG conversion uses the *gs*
program, both part of Ghostscript. On Windows, the Ghostscript console
executable (*gswin64c* or *gswin32c*) must be on PATH. PS and EPS output
do not require Ghostscript.

The page size of the PDF and PNG output is taken from the `paper`
instruction in the input file (A4 if not specified), as recorded by
*ps.map* in the generated PostScript.

## EXAMPLES

Render an instruction file to PDF (the default format):

```sh
ps.render input=map.psmap output=map.pdf
```

Render to PNG at 150 DPI:

```sh
ps.render input=map.psmap output=map.png format=png resolution=150
```

Render to plain PostScript, rotating the plot to landscape:

```sh
ps.render -r input=map.psmap output=map.ps format=ps
```

## SEE ALSO

*[g.region](g.region.md), [ps.map](ps.map.md)*

## AUTHORS

Vaclav Petras, NC State University, Center for Geospatial Analytics

Conversion logic extracted from the wxGUI Cartographic Composer
by various authors.
