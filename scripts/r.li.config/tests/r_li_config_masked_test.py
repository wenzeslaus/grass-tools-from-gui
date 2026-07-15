"""Tests for circle and vector-based sampling in r.li.config

The expected configuration file contents replicate what the
g.gui.rlisetup wizard writes: MASKEDSAMPLEAREA lines as in
RLIWizard._write_area for a circular moving window
(gui/wxpython/rlisetup/wizard.py) and MASKEDOVERLAYAREA, RASTERMAP,
and VECTORMAP lines as in obtainAreaVector and _write_area for vector
sampling (gui/wxpython/rlisetup/functions.py). The r.li runs rely on
the r.li.daemon sample area mask fixes; without them the r.li tools
abort on circle configurations or silently drop the masks.
"""

import os
from io import StringIO
from pathlib import Path

import pytest

import grass.script as gs
from grass.exceptions import CalledModuleError
from grass.tools import Tools


@pytest.fixture
def session(tmp_path):
    """Active session in an XY project with a 10x10 test landscape

    HOME (and the variables which can override it) points to a directory
    under tmp_path, so the r.li configuration directory used by both
    r.li.config and the r.li tools is isolated and writable.
    """
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("GRASS_CONFIG_DIR", None)
    env.pop("APPDATA", None)
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=env) as session:
        tools = Tools(session=session)
        tools.g_region(n=10, s=0, e=10, w=0, res=1)
        # Three rectangular patches (categories 1, 2, and 3).
        tools.r_mapcalc(expression="land = if(row() < 5, 1, if(col() < 5, 2, 3))")
        yield session


@pytest.fixture
def rli_dir(session):
    """The r.li configuration directory under the test HOME"""
    return Path(session.env["HOME"]) / ".grass8" / "r.li"


@pytest.fixture
def vector_areas(session):
    """A vector map with a square area (cat 1) and a triangular area (cat 2)

    The triangle makes the bounding box differ from the area, so results
    show whether the r.li tools honor the mask.
    """
    tools = Tools(session=session)
    areas = """\
B 5
 1 1
 1 4
 4 4
 4 1
 1 1
C 1 1
 2.5 2.5
 1 1
B 4
 5 5
 9 5
 5 9
 5 5
C 1 1
 6 6
 1 2
"""
    tools.v_in_ascii(
        input=StringIO(areas), output="sareas", format="standard", flags="n"
    )
    return "sareas"


def mask_grid(tools, name):
    """The mask raster in the current region as a list of rows of tokens"""
    text = tools.r_out_ascii(input=name, flags="h").text
    return [line.split() for line in text.splitlines()]


def plus_shape_grid(top_row, left_col):
    """10x10 token grid with a 5-cell plus of ones in a 3x3 box"""
    grid = [["*"] * 10 for _ in range(10)]
    for row, col in [(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)]:
        grid[top_row + row][left_col + col] = "1"
    return grid


def test_circle_moving_window_config(session, rli_dir):
    """Circular moving window writes the wizard's MASKEDSAMPLEAREA line

    Radius 1.2 with resolution 1 gives a rounded diameter of 2 cells,
    increased to the next odd number: a 3x3 box, so 0.3 of the 10 rows
    and columns. The mask raster is the wizard's r.circle plus shape in
    the box at the north-west corner of the sampling frame.
    """
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_circle_mw",
        method="moving_window",
        shape="circle",
        radius=1.2,
        mask="circle_mask",
    )
    assert (rli_dir / "conf_circle_mw").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\n"
        "MASKEDSAMPLEAREA -1|-1|0.3|0.3|circle_mask\n"
        "MOVINGWINDOW\n"
    )
    assert mask_grid(tools, "circle_mask") == plus_shape_grid(0, 0)


def test_circle_moving_window_run(session, rli_dir):
    """r.li computes an output raster map from a circular moving window

    Only window positions overlapping the extent of the mask raster
    contribute (r.li.daemon reads the mask at the absolute position of
    each window), so 8 cells get values: the number of patches under
    the unmasked window cells divided by their count, scaled by 1e6.
    The corner window covers all 5 mask cells in one patch (200000),
    partial overlaps give 250000, 333333.33, or 1000000.
    """
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_circle_mw",
        method="moving_window",
        shape="circle",
        radius=1.2,
        mask="circle_mask",
    )
    tools.r_li_patchdensity(input="land", config="conf_circle_mw", output="density")
    stats = tools.r_univar(map="density", flags="g").keyval
    assert stats["n"] == 8
    assert stats["min"] == 200000
    assert stats["max"] == 1000000
    assert stats["sum"] == pytest.approx(5033333.333333, rel=1e-9)


def test_circle_region_frame_mask_position(session, rli_dir):
    """The circle mask sits at the north-west corner of a sub-region frame"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_circle_frame",
        frame="region",
        north=8,
        south=2,
        east=9,
        west=2,
        method="moving_window",
        shape="circle",
        radius=1.2,
        mask="circle_frame_mask",
    )
    assert (rli_dir / "conf_circle_frame").read_text() == (
        "SAMPLINGFRAME 0.2|0.2|0.6|0.7\n"
        "MASKEDSAMPLEAREA -1|-1|0.3|0.3|circle_frame_mask\n"
        "MOVINGWINDOW\n"
    )
    # Frame offset x=2, y=2 cells puts the 3x3 circle box at rows and
    # columns 2 to 4.
    assert mask_grid(tools, "circle_frame_mask") == plus_shape_grid(2, 2)


def test_circle_units_systematic(session, rli_dir):
    """Circular systematic units give one result per unit

    The g.gui.rlisetup wizard creates the circle mask for keyboard
    sample units but omits the mask name from the SAMPLEAREA line, so
    the circle has no effect there; r.li.config writes the mask name
    using the wizard's own MASKEDSAMPLEAREA format instead. Only the
    first unit overlaps the mask raster at the north-west corner; the
    other units have no unmasked cells and give NULL.
    """
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_circle_sys",
        method="units",
        shape="circle",
        radius=1.2,
        mask="circle_units_mask",
        distribution="systematic_contiguous",
    )
    assert (rli_dir / "conf_circle_sys").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\n"
        "MASKEDSAMPLEAREA -1|-1|0.3|0.3|circle_units_mask\n"
        "SYSTEMATICCONTIGUOUS\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_circle_sys", output="res_sys")
    lines = (rli_dir / "output" / "res_sys").read_text().splitlines()
    # 3x3 units of 3x3 cells fit into 10x10; 1 patch in the 5 masked
    # cells of the first unit.
    assert lines[0] == "RESULT 1|200000"
    assert len(lines) == 9
    assert all(line.endswith("|NULL") for line in lines[1:])


def test_circle_units_random(session, rli_dir):
    """Circular random units write the wizard placement line and run"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_circle_rand",
        method="units",
        shape="circle",
        radius=1.2,
        mask="circle_rand_mask",
        distribution="random",
        count=4,
    )
    assert (rli_dir / "conf_circle_rand").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\n"
        "MASKEDSAMPLEAREA -1|-1|0.3|0.3|circle_rand_mask\n"
        "RANDOMNONOVERLAPPING 4\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_circle_rand", output="res_rand")
    assert len((rli_dir / "output" / "res_rand").read_text().splitlines()) == 4


def test_vector_config(session, rli_dir, vector_areas):
    """Vector sampling writes the wizard's MASKEDOVERLAYAREA lines

    One mask raster per area category, named
    <raster>_<vector>_<category>, with the bounding box of the area
    aligned to the reference raster, followed by the RASTERMAP and
    VECTORMAP lines.
    """
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land", output="conf_vector", method="vector", vector=vector_areas
    )
    assert (rli_dir / "conf_vector").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\n"
        "MASKEDOVERLAYAREA land_sareas_1|4.0|1.0|4.0|1.0\n"
        "MASKEDOVERLAYAREA land_sareas_2|9.0|5.0|9.0|5.0\n"
        "RASTERMAP land\n"
        "VECTORMAP sareas\n"
    )
    # The square is 3x3 cells, the rasterized triangle covers 10 cells
    # of its 4x4 bounding box.
    assert tools.r_univar(map="land_sareas_1", flags="g").keyval["n"] == 9
    assert tools.r_univar(map="land_sareas_2", flags="g").keyval["n"] == 10


def test_vector_run(session, rli_dir, vector_areas):
    """r.li honors the vector area masks, not just the bounding boxes

    The square lies in one patch: 1 patch / 9 cells. The triangle
    covers two patches with 10 unmasked cells: 2 / 10; its 16-cell
    bounding box would give a different value, so this fails if the
    mask is dropped.
    """
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land", output="conf_vector", method="vector", vector=vector_areas
    )
    tools.r_li_patchdensity(input="land", config="conf_vector", output="res_vector")
    assert (rli_dir / "output" / "res_vector").read_text() == (
        "RESULT 1|111111.111111111\nRESULT 2|200000\n"
    )


def test_region_unchanged(session, rli_dir, vector_areas):
    """Creating masks does not change the current region"""
    tools = Tools(session=session)
    before = tools.g_region(flags="g").keyval
    tools.r_li_config(
        raster="land",
        output="conf_region_circle",
        method="moving_window",
        shape="circle",
        radius=1.2,
        mask="region_check_mask",
    )
    tools.r_li_config(
        raster="land", output="conf_region_vector", method="vector", vector=vector_areas
    )
    assert tools.g_region(flags="g").keyval == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "moving_window", "shape": "circle", "radius": 1.2},  # mask missing
        {"method": "units", "shape": "circle", "mask": "m"},  # radius missing
        {"method": "whole", "shape": "circle", "radius": 1.2, "mask": "m"},
        {"method": "moving_window", "width": 3, "height": 3, "radius": 1.2},
        {
            # Rejects width with circle (the circle box comes from radius).
            "method": "moving_window",
            "shape": "circle",
            "radius": 1.2,
            "mask": "m",
            "width": 3,
        },
        {"method": "moving_window", "shape": "circle", "radius": 0, "mask": "m"},
        {
            # Radius 6 gives a 13x13 box, larger than the 10x10 raster.
            "method": "moving_window",
            "shape": "circle",
            "radius": 6,
            "mask": "m",
        },
        {"method": "vector"},  # vector map missing
        {"method": "vector", "vector": "sareas", "width": 3},
        {"method": "units", "width": 3, "height": 3, "vector": "sareas"},
    ],
    ids=[
        "circle_without_mask",
        "circle_without_radius",
        "circle_with_whole",
        "radius_with_rectangle",
        "width_with_circle",
        "zero_radius",
        "circle_larger_than_frame",
        "vector_map_missing",
        "width_with_vector",
        "vector_with_units",
    ],
)
def test_invalid_option_combinations(session, vector_areas, kwargs):
    """Invalid or incomplete option combinations end with an error"""
    tools = Tools(session=session)
    with pytest.raises(CalledModuleError):
        tools.r_li_config(raster="land", output="conf_invalid", **kwargs)
