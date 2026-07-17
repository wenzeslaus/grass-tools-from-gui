"""Tests of multi-input r.import"""

import os

import pytest

import grass.script as gs
from grass.exceptions import CalledModuleError
from grass.tools import Tools


@pytest.fixture
def session_with_files(tmp_path):
    """Active session and two GeoTIFF files matching the project CRS

    Yields a tuple (session, files) where files is a list of two GeoTIFF
    paths exported from the project, so importing them back does not need
    reprojection (and thus no network access).
    """
    project = tmp_path / "test_project"
    gs.create_project(project, epsg="3358")
    with (
        gs.setup.init(project, env=os.environ.copy()) as session,
        Tools(session=session) as tools,
    ):
        tools.g_region(s=0, n=10, w=0, e=10, res=1)
        tools.r_mapcalc(expression="row_values = row()")
        tools.r_mapcalc(expression="col_values = col()")
        files = [tmp_path / "first_file.tif", tmp_path / "second_file.tif"]
        tools.r_out_gdal(input="row_values", output=files[0], format="GTiff")
        tools.r_out_gdal(input="col_values", output=files[1], format="GTiff")
        yield session, files


def test_single_input_with_explicit_output(session_with_files):
    """Single input with explicit output behaves as the original tool"""
    session, files = session_with_files
    tools = Tools(session=session)
    tools.r_import(input=files[0], output="explicit_name")
    univar = tools.r_univar(map="explicit_name", flags="g").keyval
    assert univar["n"] == 100
    assert univar["min"] == 1
    assert univar["max"] == 10


def test_multiple_inputs_derive_output_names(session_with_files):
    """Multiple inputs without output create maps named after the files"""
    session, files = session_with_files
    tools = Tools(session=session)
    tools.r_import(input=f"{files[0]},{files[1]}")
    first = tools.r_univar(map="first_file", flags="g").keyval
    assert first["n"] == 100
    assert first["min"] == 1
    assert first["max"] == 10
    second = tools.r_univar(map="second_file", flags="g").keyval
    assert second["n"] == 100
    assert second["min"] == 1
    assert second["max"] == 10


def test_mismatched_output_count_fails(session_with_files):
    """Numbers of inputs and outputs which differ are an error"""
    session, files = session_with_files
    tools = Tools(session=session)
    with pytest.raises(CalledModuleError):
        tools.r_import(input=f"{files[0]},{files[1]}", output="only_one")
