"""Tests for i.gcp.manage"""

import os
import pathlib

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

# Image and target coordinates of four points where the fourth target
# point is shifted 10 north. The least squares affine (order 1) fit
# distributes the misfit so that every forward error is exactly 2.5
# (all in the north direction). The backward errors follow from the
# inverse fit; the expected values below were derived by hand from the
# normal equations and confirmed by running m.transform.
IMAGE_COORDINATES = (0, 0, 100, 0, 0, 100, 100, 100)
TARGET_COORDINATES = (0, 0, 100, 0, 0, 100, 100, 110)
FORWARD_ERRORS = [2.5, 2.5, 2.5, 2.5]
BACKWARD_ERRORS = [2.488688, 2.262443, 2.488688, 2.262443]
FORWARD_RMS = 2.5
BACKWARD_RMS = 2.378257


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


def points_path(session):
    """Return the path of the POINTS file of the test group"""
    env = gs.gisenv(env=session.env)
    return (
        pathlib.Path(env["GISDBASE"], env["LOCATION_NAME"], env["MAPSET"])
        / "group"
        / "test"
        / "POINTS"
    )


def test_add_and_list_plain(session):
    """Added points are listed in plain format with 1-based numbers"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    lines = tools.i_gcp_manage(group="test", operation="list").text.splitlines()
    assert len(lines) == 4
    for i, line in enumerate(lines, start=1):
        fields = line.split()
        assert int(fields[0]) == i
        assert [float(fields[1]), float(fields[2])] == pytest.approx(
            [IMAGE_COORDINATES[2 * i - 2], IMAGE_COORDINATES[2 * i - 1]]
        )
        assert [float(fields[3]), float(fields[4])] == pytest.approx(
            [TARGET_COORDINATES[2 * i - 2], TARGET_COORDINATES[2 * i - 1]]
        )
        assert int(fields[5]) == 1


def test_add_and_list_json(session):
    """Added points are listed in JSON format with all attributes"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert len(result["points"]) == 4
    for i, point in enumerate(result["points"], start=1):
        assert point["number"] == i
        assert point["image_east"] == pytest.approx(IMAGE_COORDINATES[2 * i - 2])
        assert point["image_north"] == pytest.approx(IMAGE_COORDINATES[2 * i - 1])
        assert point["target_east"] == pytest.approx(TARGET_COORDINATES[2 * i - 2])
        assert point["target_north"] == pytest.approx(TARGET_COORDINATES[2 * i - 1])
        assert point["status"] == 1


def test_list_empty_group(session):
    """A group without a POINTS file lists as no points"""
    tools = Tools(session=session)
    # Tools returns None when a tool produces no standard output.
    assert tools.i_gcp_manage(group="test", operation="list") is None
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert result["points"] == []


def test_disable_and_enable(session):
    """Disable and enable change only the status of the given points"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    tools.i_gcp_manage(group="test", operation="disable", points=[1, 4])
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert [point["status"] for point in result["points"]] == [0, 1, 1, 0]
    tools.i_gcp_manage(group="test", operation="enable", points=4)
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert [point["status"] for point in result["points"]] == [0, 1, 1, 1]


def test_remove_renumbers_remaining_points(session):
    """Remove deletes the given points and remaining points are renumbered"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    tools.i_gcp_manage(group="test", operation="remove", points=[1, 3])
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert [point["number"] for point in result["points"]] == [1, 2]
    # Former points 2 and 4 remain, identified by their image east.
    assert [point["image_east"] for point in result["points"]] == pytest.approx(
        [100, 100]
    )
    assert [point["target_north"] for point in result["points"]] == pytest.approx(
        [0, 110]
    )


def test_remove_out_of_range(session):
    """Point numbers outside 1..count are rejected"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    with pytest.raises(ToolError, match="out of range"):
        tools.i_gcp_manage(group="test", operation="remove", points=5)


def test_rms(session):
    """RMS errors match the values hand-derived and confirmed with m.transform"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    result = tools.i_gcp_manage(
        group="test", operation="rms", order=1, format="json"
    ).json
    assert result["order"] == 1
    assert result["active"] == 4
    assert [point["forward"] for point in result["points"]] == pytest.approx(
        FORWARD_ERRORS
    )
    assert [point["backward"] for point in result["points"]] == pytest.approx(
        BACKWARD_ERRORS
    )
    assert result["forward_rms"] == pytest.approx(FORWARD_RMS)
    assert result["backward_rms"] == pytest.approx(BACKWARD_RMS, rel=1e-5)
    # The per-point values must be exactly the ones m.transform reports.
    m_transform_lines = tools.m_transform(group="test", order=1).text.splitlines()
    expected = [[float(value) for value in line.split()] for line in m_transform_lines]
    actual = [[point["forward"], point["backward"]] for point in result["points"]]
    assert actual == expected


def test_rms_skips_inactive_points(session):
    """Inactive points get null errors and do not enter the totals"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    # Without the misfitting fourth point, the remaining three points
    # define an exact identity transformation.
    tools.i_gcp_manage(group="test", operation="disable", points=4)
    result = tools.i_gcp_manage(
        group="test", operation="rms", order=1, format="json"
    ).json
    assert result["active"] == 3
    assert [point["forward"] for point in result["points"]] == pytest.approx(
        [0, 0, 0, None]
    )
    assert result["forward_rms"] == pytest.approx(0)
    assert result["backward_rms"] == pytest.approx(0)


def test_rms_insufficient_active_points(session):
    """Too few active points for the requested order is a clear error"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    with pytest.raises(ToolError, match="Insufficient active points"):
        tools.i_gcp_manage(group="test", operation="rms", order=2)


def test_clear(session):
    """Clear removes all points"""
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    tools.i_gcp_manage(group="test", operation="clear")
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert result["points"] == []


def test_points_file_matches_lib_imagery_format(session):
    """The written POINTS file is byte-identical to what lib/imagery writes

    m.transform rewrites the POINTS file through I_put_control_points()
    when it runs, so comparing the file before and after proves the
    formats match exactly.
    """
    tools = Tools(session=session)
    tools.i_gcp_manage(
        group="test",
        operation="add",
        image_coordinates=IMAGE_COORDINATES,
        target_coordinates=TARGET_COORDINATES,
    )
    path = points_path(session)
    before = path.read_text(encoding="utf-8")
    tools.m_transform(group="test", order=1)
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_reads_gui_written_points_file(session):
    """A POINTS file written by the wxGUI GCP manager is read correctly

    The wxGUI SaveGCPs() writes its own comment header and separates the
    values by plain spaces (gui/wxpython/gcp/manager.py).
    """
    tools = Tools(session=session)
    gui_content = (
        "# Ground Control Points File\n"
        "# \n"
        "# target location: xy_target\n"
        "# target mapset: PERMANENT\n"
        "#\tsource\t\ttarget\t\tstatus\n"
        "#\teast\tnorth\teast\tnorth\t(1=ok, 0=ignore)\n"
        "#-----------------------     -----------------------     "
        "---------------\n"
        "0.0 0.0     10.0 20.0     1\n"
        "5.0 5.0     15.0 25.0     0\n"
    )
    points_path(session).write_text(gui_content, encoding="utf-8")
    result = tools.i_gcp_manage(group="test", operation="list", format="json").json
    assert len(result["points"]) == 2
    assert result["points"][0]["target_east"] == pytest.approx(10)
    assert result["points"][0]["status"] == 1
    assert result["points"][1]["image_north"] == pytest.approx(5)
    assert result["points"][1]["status"] == 0


def test_missing_group(session):
    """A nonexistent group is a clear error"""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="not found"):
        tools.i_gcp_manage(group="does_not_exist", operation="list")
