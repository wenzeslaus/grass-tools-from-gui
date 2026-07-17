"""Tests for i.gcp.manage support of CONTROL_POINTS (points_file=control_points)"""

import math
import os
import pathlib

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

# Photo and target coordinates of six 3D points of a synthetic vertical
# photo taken from position (500, 500, 1000) with a calibrated focal
# length of 150: photo x and y are 0.15 times the target offsets from
# (500, 500), all target elevations are 0. i.ortho.transform recovers
# this camera position from any 4+ of the points, so the points support
# rms tests without hand-picked expected error values.
IMAGE_COORDINATES = (-75, -75, 75, -75, -75, 75, 75, 75, 0, 0, -45, 30)
TARGET_COORDINATES = (0, 0, 1000, 0, 0, 1000, 1000, 1000, 500, 500, 200, 700)

# Three points with heights exercising negative, fractional, and large
# values for the byte-format test and the coordinate listing tests.
FORMAT_IMAGE_COORDINATES = (-75, -75, 10.5, -20.25, 0, 0)
FORMAT_IMAGE_HEIGHTS = (0, 1.5, -153.24)
FORMAT_TARGET_COORDINATES = (0, 0, 200000, 750000.125, 500, 500)
FORMAT_TARGET_HEIGHTS = (0, 145, 120.5)

# Exact content of the CONTROL_POINTS file for the three points above
# with the second point disabled, as written by I_write_con_points()
# from imagery/i.ortho.photo/lib/conz_points.c (obtained by compiling
# a small program against libgrass_iortho and running it with these
# point values during test development).
EXPECTED_FILE_CONTENT = (
    "#                   photo                                        "
    "control           status\n"
    "#               x               y             -cfl            east"
    "           north           elev.   (1=ok)\n"
    "#\n"
    "       -75.000000      -75.000000        0.000000        0.000000"
    "        0.000000        0.000000    1\n"
    "        10.500000      -20.250000        1.500000   200000.000000"
    "   750000.125000      145.000000    0\n"
    "         0.000000        0.000000     -153.240000      500.000000"
    "      500.000000      120.500000    1\n"
)


@pytest.fixture
def session(tmp_path):
    """Active session in an XY project with a group named test (scope: function)"""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        tools = Tools(session=session)
        tools.g_region(s=0, n=100, w=0, e=100, res=10)
        tools.r_mapcalc(expression="img = row()")
        tools.i_group(group="test", input="img")
        yield session


@pytest.fixture
def ortho_session(tmp_path, session):
    """Session extended by the orthophoto setup i.ortho.transform requires"""
    gs.create_project(tmp_path / "target_project", epsg="3358")
    tools = Tools(session=session)
    tools.i_ortho_camera(
        group="test", camera="cam", name="cam", id="c1", clf=150, pp=(0, 0)
    )
    tools.i_ortho_target(
        group="test", target_project="target_project", target_mapset="PERMANENT"
    )
    # No tool writes REF_POINTS (only g.gui.photo2image does), so write
    # an identity image-to-photo mapping directly in the format read by
    # I_read_ref_points() from imagery/i.ortho.photo/lib/ref_points.c.
    group_file_path(session, "REF_POINTS").write_text(
        "# image east, image north, photo x, photo y, status\n"
        "  0 0 0 0 1\n"
        "  100 0 100 0 1\n"
        "  0 100 0 100 1\n"
        "  100 100 100 100 1\n",
        encoding="utf-8",
    )
    return session


def group_file_path(session, file_name):
    """Return the path of a file of the test group"""
    env = gs.gisenv(env=session.env)
    return (
        pathlib.Path(env["GISDBASE"], env["LOCATION_NAME"], env["MAPSET"])
        / "group"
        / "test"
        / file_name
    )


def add_format_points(tools):
    """Add the three points of the byte-format test"""
    tools.i_gcp_manage(
        group="test",
        operation="add",
        points_file="control_points",
        image_coordinates=FORMAT_IMAGE_COORDINATES,
        image_heights=FORMAT_IMAGE_HEIGHTS,
        target_coordinates=FORMAT_TARGET_COORDINATES,
        target_heights=FORMAT_TARGET_HEIGHTS,
    )


def test_add_and_list_plain(session):
    """Added 3D points are listed with heights in plain format"""
    tools = Tools(session=session)
    add_format_points(tools)
    lines = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points"
    ).text.splitlines()
    assert len(lines) == 3
    for i, line in enumerate(lines, start=1):
        fields = line.split()
        assert len(fields) == 8
        assert int(fields[0]) == i
        assert [float(field) for field in fields[1:7]] == pytest.approx(
            [
                FORMAT_IMAGE_COORDINATES[2 * i - 2],
                FORMAT_IMAGE_COORDINATES[2 * i - 1],
                FORMAT_IMAGE_HEIGHTS[i - 1],
                FORMAT_TARGET_COORDINATES[2 * i - 2],
                FORMAT_TARGET_COORDINATES[2 * i - 1],
                FORMAT_TARGET_HEIGHTS[i - 1],
            ]
        )
        assert int(fields[7]) == 1


def test_add_and_list_json(session):
    """Added 3D points are listed in JSON format with height attributes"""
    tools = Tools(session=session)
    add_format_points(tools)
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert len(result["points"]) == 3
    for i, point in enumerate(result["points"], start=1):
        assert point["number"] == i
        assert point["image_east"] == pytest.approx(FORMAT_IMAGE_COORDINATES[2 * i - 2])
        assert point["image_north"] == pytest.approx(
            FORMAT_IMAGE_COORDINATES[2 * i - 1]
        )
        assert point["image_height"] == pytest.approx(FORMAT_IMAGE_HEIGHTS[i - 1])
        assert point["target_east"] == pytest.approx(
            FORMAT_TARGET_COORDINATES[2 * i - 2]
        )
        assert point["target_north"] == pytest.approx(
            FORMAT_TARGET_COORDINATES[2 * i - 1]
        )
        assert point["target_height"] == pytest.approx(FORMAT_TARGET_HEIGHTS[i - 1])
        assert point["status"] == 1


def test_add_default_heights(session):
    """Omitted height options default to zero heights"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        points_file="control_points",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert len(result["points"]) == 6
    assert all(point["image_height"] == 0 for point in result["points"])
    assert all(point["target_height"] == 0 for point in result["points"])


def test_add_heights_count_mismatch(session):
    """A height count different from the point count is a clear error"""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="one height per point"):
        tools.i_gcp_manage(
            group="test",
            operation="add",
            points_file="control_points",
            image_coordinates=(0, 0, 10, 10),
            target_coordinates=(0, 0, 10, 10),
            target_heights=(5,),
        )


def test_heights_require_control_points(session):
    """Height options are rejected for the default POINTS file"""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="control_points"):
        tools.i_gcp_manage(
            group="test",
            operation="add",
            image_coordinates=(0, 0),
            target_coordinates=(10, 10),
            image_heights=(5,),
        )


def test_disable_enable_and_remove(session):
    """Status changes and removal work on CONTROL_POINTS with renumbering"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        points_file="control_points",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    tools.i_gcp_manage(
        group="test", operation="disable", points_file="control_points", points=[2, 5]
    )
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert [point["status"] for point in result["points"]] == [1, 0, 1, 1, 0, 1]
    tools.i_gcp_manage(
        group="test", operation="enable", points_file="control_points", points=5
    )
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert [point["status"] for point in result["points"]] == [1, 0, 1, 1, 1, 1]
    tools.i_gcp_manage(
        group="test", operation="remove", points_file="control_points", points=[1, 2]
    )
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert [point["number"] for point in result["points"]] == [1, 2, 3, 4]
    # Former points 3 to 6 remain, identified by their image east.
    assert [point["image_east"] for point in result["points"]] == pytest.approx(
        [-75, 75, 0, -45]
    )


def test_clear(session):
    """Clear removes all points from the CONTROL_POINTS file"""
    tools = Tools(session=session)
    add_format_points(tools)
    tools.i_gcp_manage(group="test", operation="clear", points_file="control_points")
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert result["points"] == []


def test_control_points_file_matches_ortho_lib_format(session):
    """The written CONTROL_POINTS file is byte-identical to the C library output

    The expected content was generated by I_write_con_points() from the
    i.ortho.photo library for the same three points (second disabled).
    """
    tools = Tools(session=session)
    add_format_points(tools)
    tools.i_gcp_manage(
        group="test", operation="disable", points_file="control_points", points=2
    )
    path = group_file_path(session, "CONTROL_POINTS")
    assert path.read_text(encoding="utf-8") == EXPECTED_FILE_CONTENT


def test_points_files_are_independent(session):
    """POINTS and CONTROL_POINTS are managed separately"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=(0, 0),
        target_coordinates=(10, 20),
    )
    points_path = group_file_path(session, "POINTS")
    points_before = points_path.read_text(encoding="utf-8")
    add_format_points(tools)
    tools.i_gcp_manage(
        group="test", operation="disable", points_file="control_points", points=1
    )
    assert points_path.read_text(encoding="utf-8") == points_before
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert len(result["points"]) == 1
    assert result["points"][0]["status"] == 1
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert len(result["points"]) == 3
    assert result["points"][0]["status"] == 0


def test_reads_gui_written_control_points_file(session):
    """A CONTROL_POINTS file written by the wxGUI GCP manager is read correctly

    The wxGUI SaveGCPs() writes its own comment header and separates the
    values by plain spaces (gui/wxpython/image2target/ii2t_manager.py).
    """
    tools = Tools(session=session)
    gui_content = (
        "# Ground Control Points File\n"
        "# \n"
        "# target location: tgt\n"
        "# target mapset: PERMANENT\n"
        "#\tsource\t\t\ttarget\t\t\tstatus\n"
        "#\teast\tnorth\theight\teast\tnorth\theight\t(1=ok, 0=ignore)\n"
        "#----------------------------     ---------------------------     "
        "---------------\n"
        "0.0 0.0     0.0 10.0     20.0     145.0     1\n"
        "5.0 5.0     1.0 15.0     25.0     150.0     0\n"
    )
    group_file_path(session, "CONTROL_POINTS").write_text(gui_content, encoding="utf-8")
    result = tools.i_gcp_manage(
        group="test", operation="list", points_file="control_points", format="json"
    ).json
    assert len(result["points"]) == 2
    assert result["points"][0]["target_east"] == pytest.approx(10)
    assert result["points"][0]["target_height"] == pytest.approx(145)
    assert result["points"][0]["status"] == 1
    assert result["points"][1]["image_north"] == pytest.approx(5)
    assert result["points"][1]["image_height"] == pytest.approx(1)
    assert result["points"][1]["status"] == 0


def test_rms(ortho_session):
    """RMS errors are exactly the per-point errors of i.ortho.transform"""
    tools = Tools(session=ortho_session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        points_file="control_points",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    tools.i_gcp_manage(
        group="test", operation="disable", points_file="control_points", points=5
    )
    result = tools.i_gcp_manage(
        group="test", operation="rms", points_file="control_points", format="json"
    ).json
    # The camera model has no polynomial order.
    assert "order" not in result
    assert result["active"] == 5
    assert result["points"][4]["forward"] is None
    assert result["points"][4]["backward"] is None
    active = [point for point in result["points"] if point["status"] > 0]
    transform_lines = tools.i_ortho_transform(group="test").text.splitlines()
    expected = [[float(value) for value in line.split()] for line in transform_lines]
    assert [[point["forward"], point["backward"]] for point in active] == expected
    assert result["forward_rms"] == pytest.approx(
        math.sqrt(sum(point["forward"] ** 2 for point in active) / len(active))
    )
    assert result["backward_rms"] == pytest.approx(
        math.sqrt(sum(point["backward"] ** 2 for point in active) / len(active))
    )


def test_rms_insufficient_active_points(session):
    """Fewer than 4 active points without i.ortho.init is a clear error"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        points_file="control_points",
        image_coordinates=IMAGE_COORDINATES[:6],
        target_coordinates=TARGET_COORDINATES[:6],
    )
    with pytest.raises(ToolError, match="Insufficient active points"):
        tools.i_gcp_manage(group="test", operation="rms", points_file="control_points")


def test_rms_order_not_applicable(session):
    """A non-default order with CONTROL_POINTS is a clear error"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        points_file="control_points",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    with pytest.raises(ToolError, match="order applies only"):
        tools.i_gcp_manage(
            group="test", operation="rms", points_file="control_points", order=2
        )
