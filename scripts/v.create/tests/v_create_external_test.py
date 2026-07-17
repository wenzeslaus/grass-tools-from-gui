"""Tests of the v.create type option and external output formats."""

import os
import pathlib

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools


@pytest.fixture
def session(tmp_path):
    """Active session in a new XY project (scope: function)."""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        yield session


def test_native_accepts_and_ignores_type(session):
    """With the native format, type is accepted and a native map is created."""
    tools = Tools(session=session)
    tools.v_create(output="plain", type="line")
    assert tools.v_info(map="plain", format="json").json["format"] == "native"


def test_create_point_layer_in_geopackage(tmp_path, session):
    """The new layer is created in the datasource and linked in the mapset."""
    tools = Tools(session=session)
    dsn = str(tmp_path / "data.gpkg")
    tools.v_external_out(output=dsn, format="GPKG")
    # The default type is point.
    tools.v_create(output="points")
    info = tools.v_info(map="points", format="json").json
    assert info["format"] == "OGR"
    assert info["feature_type"] == "point"
    assert info["ogr_layer"] == "points"
    assert info["ogr_dsn"] == dsn
    assert tools.v_external(input=dsn, flags="l").text.splitlines() == ["points"]


def test_feature_types(tmp_path, session):
    """Each type value creates a layer of the corresponding geometry type."""
    tools = Tools(session=session)
    # A directory-based Shapefile datasource holds one layer per file, so
    # several maps can be created into the same datasource.
    dsn = tmp_path / "shapes"
    dsn.mkdir()
    tools.v_external_out(output=str(dsn), format="ESRI_Shapefile")
    for map_type, feature_type in (
        ("point", "point"),
        ("line", "linestring"),
        ("boundary", "polygon"),
    ):
        tools.v_create(output=map_type, type=map_type)
        assert (
            tools.v_info(map=map_type, format="json").json["feature_type"]
            == feature_type
        )


def test_table_options_rejected_for_external(tmp_path, session):
    """Table creation options fail with external format and create nothing."""
    tools = Tools(session=session)
    dsn = str(tmp_path / "data.gpkg")
    tools.v_external_out(output=dsn, format="GPKG")
    with pytest.raises(ToolError):
        tools.v_create(output="tabled", columns="name varchar(20)")
    with pytest.raises(ToolError):
        tools.v_create(output="tabled", flags="t")
    assert not gs.find_file("tabled", element="vector", env=session.env)["name"]
    # The tool fails before the datasource is even created.
    assert not pathlib.Path(dsn).exists()


def test_overwrite_external_layer(tmp_path, session):
    """An existing external layer is replaced only with overwrite."""
    tools = Tools(session=session)
    dsn = str(tmp_path / "data.gpkg")
    tools.v_external_out(output=dsn, format="GPKG")
    tools.v_create(output="points")
    with pytest.raises(ToolError):
        tools.v_create(output="points", type="line")
    tools.v_create(output="points", type="line", overwrite=True)
    assert tools.v_info(map="points", format="json").json["feature_type"] == (
        "linestring"
    )


def test_overwrite_layer_without_mapset_link(tmp_path, session):
    """A layer present only in the datasource still requires overwrite."""
    tools = Tools(session=session)
    dsn = str(tmp_path / "data.gpkg")
    tools.v_external_out(output=dsn, format="GPKG")
    tools.v_create(output="points")
    # This removes the link from the mapset, not the layer in the datasource.
    tools.g_remove(type="vector", name="points", flags="f")
    assert tools.v_external(input=dsn, flags="l").text.splitlines() == ["points"]
    with pytest.raises(ToolError):
        tools.v_create(output="points")
    tools.v_create(output="points", overwrite=True)
    found = gs.find_file("points", element="vector", env=session.env)
    assert found["name"] == "points"
