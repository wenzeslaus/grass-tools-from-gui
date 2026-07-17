"""Tests of multi-input v.import"""

import os
from io import StringIO

import pytest

import grass.script as gs
from grass.exceptions import CalledModuleError
from grass.tools import Tools


@pytest.fixture
def session_with_files(tmp_path):
    """Active session and two GeoJSON files matching the project CRS

    Yields a tuple (session, files) where files is a list of two GeoJSON
    paths exported from the project, so importing them back does not need
    reprojection (and thus no network access). The layer names inside the
    files (points_one, points_two) differ from the file names on purpose,
    so tests can distinguish file-name-derived output names from
    layer-name-derived ones. The source vector maps are removed, leaving
    an empty mapset for the import tests.
    """
    project = tmp_path / "test_project"
    gs.create_project(project, epsg="3358")
    with (
        gs.setup.init(project, env=os.environ.copy()) as session,
        Tools(session=session) as tools,
    ):
        tools.v_in_ascii(
            input=StringIO("100|200\n150|250"), output="points_one", separator="pipe"
        )
        tools.v_in_ascii(
            input=StringIO("300|400\n350|450"), output="points_two", separator="pipe"
        )
        files = [tmp_path / "first_points.geojson", tmp_path / "second_points.geojson"]
        tools.v_out_ogr(input="points_one", output=files[0], format="GeoJSON")
        tools.v_out_ogr(input="points_two", output=files[1], format="GeoJSON")
        tools.g_remove(type="vector", name="points_one,points_two", flags="f")
        yield session, files


def test_single_input_with_explicit_output(session_with_files):
    """Single input with explicit output behaves as the original tool"""
    session, files = session_with_files
    tools = Tools(session=session)
    tools.v_import(input=files[0], output="explicit_name")
    assert tools.v_info(map="explicit_name", flags="t").keyval["points"] == 2


def test_multiple_inputs_derive_output_names(session_with_files):
    """Multiple inputs without output create maps named after the files

    The names are derived from the file names, not from the layer names
    inside the files.
    """
    session, files = session_with_files
    tools = Tools(session=session)
    tools.v_import(input=f"{files[0]},{files[1]}")
    assert tools.v_info(map="first_points", flags="t").keyval["points"] == 2
    assert tools.v_info(map="second_points", flags="t").keyval["points"] == 2


def test_mismatched_output_count_fails(session_with_files):
    """Numbers of inputs and outputs which differ are an error"""
    session, files = session_with_files
    tools = Tools(session=session)
    with pytest.raises(CalledModuleError):
        tools.v_import(input=f"{files[0]},{files[1]}", output="only_one")
