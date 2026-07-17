"""Tests for v.in.dxf with the format option for the layer listing"""

import json
import os
from io import StringIO

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

# Output of the unmodified vector/v.in.dxf for the DXF file created by the
# fixture, captured from the original tool before this extension. The plain
# format output must stay byte-identical to it.
ORIGINAL_PLAIN_LISTING = "Layer 1: point\nLayer 2: point_label\n"


@pytest.fixture
def session_and_dxf(tmp_path):
    """Active session in an XY project and a path to a two-layer DXF file

    The DXF file is created by exporting a small point vector map with
    v.out.dxf, which writes the points to a "point" layer and their
    labels to a "point_label" layer.
    """
    project = tmp_path / "xy_test"
    dxf_path = tmp_path / "points.dxf"
    gs.create_project(project)
    with (
        gs.setup.init(project, env=os.environ.copy()) as session,
        Tools(session=session) as tools,
    ):
        tools.v_in_ascii(
            input=StringIO("10.0,20.0\n30.0,40.0\n"),
            output="points",
            format="point",
            separator="comma",
        )
        tools.v_out_dxf(input="points", output=str(dxf_path))
        yield session, dxf_path


def test_list_plain_matches_original(session_and_dxf):
    """Plain listing must be byte-identical to the original tool's output"""
    session, dxf_path = session_and_dxf
    tools = Tools(session=session)
    result = tools.v_in_dxf(input=str(dxf_path), flags="l")
    assert result.stdout == ORIGINAL_PLAIN_LISTING
    # The plain format is the default, so an explicit request must match too.
    result = tools.v_in_dxf(input=str(dxf_path), flags="l", format="plain")
    assert result.stdout == ORIGINAL_PLAIN_LISTING


def test_list_json(session_and_dxf):
    """JSON listing contains the layer names with one-based indices"""
    session, dxf_path = session_and_dxf
    tools = Tools(session=session)
    result = tools.v_in_dxf(input=str(dxf_path), flags="l", format="json")
    layers = json.loads(result.stdout)
    assert layers == [
        {"index": 1, "name": "point"},
        {"index": 2, "name": "point_label"},
    ]


def test_json_without_list_flag_fails(session_and_dxf):
    """format=json is an error in import mode which has no listing output"""
    session, dxf_path = session_and_dxf
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="format option"):
        tools.v_in_dxf(input=str(dxf_path), output="imported", format="json")


def test_import(session_and_dxf):
    """Importing a single layer still works"""
    session, dxf_path = session_and_dxf
    tools = Tools(session=session)
    tools.v_in_dxf(input=str(dxf_path), layers="point", output="imported")
    info = tools.v_info(map="imported", flags="t")
    assert info.keyval["points"] == 2
