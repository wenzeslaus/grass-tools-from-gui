"""Tests of ps.render output formats"""

import os

import pytest

import grass.script as gs
from grass.tools import Tools

PDF_MAGIC = b"%PDF"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PS_MAGIC = b"%!PS"
EPS_MAGIC = b"%!PS-Adobe-3.0 EPSF"


@pytest.fixture
def session(tmp_path):
    """Active session in an XY project with a small raster"""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        tools = Tools(session=session)
        tools.g_region(s=0, n=5, w=0, e=6, res=1)
        tools.r_mapcalc(expression="test_raster = row()")
        yield session


@pytest.fixture
def instruction_file(tmp_path):
    """Minimal ps.map instruction file showing the test raster"""
    path = tmp_path / "instructions.psmap"
    path.write_text("raster test_raster\nend\n")
    return path


def test_pdf_output(session, instruction_file, tmp_path):
    """Check that the default format produces a PDF file"""
    output = tmp_path / "map.pdf"
    Tools(session=session).ps_render(input=instruction_file, output=output)
    assert output.read_bytes().startswith(PDF_MAGIC)


def test_png_output(session, instruction_file, tmp_path):
    """Check that format=png produces a PNG file"""
    output = tmp_path / "map.png"
    Tools(session=session).ps_render(
        input=instruction_file, output=output, format="png", resolution=100
    )
    assert output.read_bytes().startswith(PNG_MAGIC)


def test_ps_output(session, instruction_file, tmp_path):
    """Check that format=ps produces a PostScript file"""
    output = tmp_path / "map.ps"
    Tools(session=session).ps_render(input=instruction_file, output=output, format="ps")
    content = output.read_bytes()
    assert content.startswith(PS_MAGIC)
    assert not content.startswith(EPS_MAGIC)


def test_eps_output(session, instruction_file, tmp_path):
    """Check that format=eps produces an Encapsulated PostScript file"""
    output = tmp_path / "map.eps"
    Tools(session=session).ps_render(
        input=instruction_file, output=output, format="eps"
    )
    assert output.read_bytes().startswith(EPS_MAGIC)
