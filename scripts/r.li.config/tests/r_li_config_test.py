"""Tests for r.li.config configuration files and their use by r.li tools"""

import os
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


def read_result(rli_dir, name):
    """Read a text result written by an r.li tool"""
    return (rli_dir / "output" / name).read_text()


def patches_in_unit(value, cells):
    """Patch count in a sample unit from a patch density result value

    The result value is patches per cell scaled by 1e6 and printed by
    the r.li tool with limited precision, so it is converted back to
    the whole number of patches before comparing.
    """
    patches = value * cells / 1e6
    assert patches == pytest.approx(round(patches))
    return round(patches)


def test_whole_frame_whole_area(session, rli_dir):
    """Whole region config is written and accepted by r.li.patchdensity"""
    tools = Tools(session=session)
    tools.r_li_config(raster="land", output="conf_whole")
    assert (rli_dir / "conf_whole").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\nSAMPLEAREA 0.0|0.0|1.0|1.0\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_whole", output="res_whole")
    # 3 patches per 100 cells of unit size, scaled by 1e6 by the tool.
    assert read_result(rli_dir, "res_whole") == "RESULT 1|30000\n"


def test_region_frame(session, rli_dir):
    """Sub-region frame stores relative coordinates of the frame"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_region",
        frame="region",
        north=8,
        south=2,
        east=9,
        west=2,
    )
    # Cell offsets x=2, y=2 and lengths rows=6, cols=7 relative to 10x10.
    assert (rli_dir / "conf_region").read_text() == (
        "SAMPLINGFRAME 0.2|0.2|0.6|0.7\nSAMPLEAREA 0.2|0.2|0.6|0.7\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_region", output="res_region")
    # 3 patches per 42 cells (6x7 frame), scaled by 1e6 by the tool.
    assert read_result(rli_dir, "res_region") == "RESULT 1|71428.5714285714\n"


def test_moving_window(session, rli_dir):
    """Moving window config produces an output raster map"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land", output="conf_window", method="moving_window", width=3, height=3
    )
    assert (rli_dir / "conf_window").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\nSAMPLEAREA -1|-1|0.3|0.3\nMOVINGWINDOW\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_window", output="density")
    stats = tools.r_univar(map="density", flags="g").keyval
    # A 3x3 window fits at 8x8 positions in a 10x10 raster.
    assert stats["n"] == 64
    # 1 to 3 patches in 9 cells, scaled by 1e6 by the tool.
    assert stats["min"] == pytest.approx(1e6 / 9)
    assert stats["max"] == pytest.approx(3e6 / 9)


def test_units_random(session, rli_dir):
    """Randomly placed sample units give one result per unit"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_random",
        method="units",
        width=3,
        height=3,
        distribution="random",
        count=4,
    )
    assert (rli_dir / "conf_random").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\nSAMPLEAREA -1|-1|0.3|0.3\nRANDOMNONOVERLAPPING 4\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_random", output="res_random")
    lines = read_result(rli_dir, "res_random").splitlines()
    assert len(lines) == 4
    for i, line in enumerate(lines, start=1):
        aid, value = line.replace("RESULT ", "").split("|")
        assert int(aid) == i
        # 1 to 3 patches in a 3x3 unit.
        assert 1 <= patches_in_unit(float(value), cells=9) <= 3


def test_region_frame_with_units(session, rli_dir):
    """Sample units are placed within a sub-region sampling frame"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_regsys",
        frame="region",
        north=8,
        south=2,
        east=9,
        west=2,
        method="units",
        width=3,
        height=3,
        distribution="systematic_contiguous",
    )
    assert (rli_dir / "conf_regsys").read_text() == (
        "SAMPLINGFRAME 0.2|0.2|0.6|0.7\nSAMPLEAREA -1|-1|0.3|0.3\n"
        "SYSTEMATICCONTIGUOUS\n"
    )
    tools.r_li_patchdensity(input="land", config="conf_regsys", output="res_regsys")
    # 2x2 units of 3x3 cells fit into the 6x7 frame.
    assert len(read_result(rli_dir, "res_regsys").splitlines()) == 4


def test_units_systematic_contiguous(session, rli_dir):
    """Systematic contiguous sample units cover the frame in a grid"""
    tools = Tools(session=session)
    tools.r_li_config(
        raster="land",
        output="conf_systematic",
        method="units",
        width=3,
        height=3,
        distribution="systematic_contiguous",
    )
    assert (rli_dir / "conf_systematic").read_text() == (
        "SAMPLINGFRAME 0|0|1|1\nSAMPLEAREA -1|-1|0.3|0.3\nSYSTEMATICCONTIGUOUS\n"
    )
    tools.r_li_patchdensity(
        input="land", config="conf_systematic", output="res_systematic"
    )
    lines = read_result(rli_dir, "res_systematic").splitlines()
    # 3x3 units of 3x3 cells fit into 10x10.
    assert len(lines) == 9
    for line in lines:
        value = float(line.split("|")[1])
        # 1 to 3 patches in a 3x3 unit.
        assert 1 <= patches_in_unit(value, cells=9) <= 3


def test_config_path_accepted_by_r_li(session, rli_dir):
    """r.li tools accept the full path of a file in the configuration directory"""
    tools = Tools(session=session)
    tools.r_li_config(raster="land", output="conf_path")
    tools.r_li_patchdensity(
        input="land", config=str(rli_dir / "conf_path"), output="res_path"
    )
    assert read_result(rli_dir, "res_path") == "RESULT 1|30000\n"


def test_overwrite_required(session, rli_dir):
    """Existing file is preserved without --overwrite and replaced with it"""
    tools = Tools(session=session)
    tools.r_li_config(raster="land", output="conf_once")
    with pytest.raises(CalledModuleError, match="overwrite"):
        tools.r_li_config(raster="land", output="conf_once")
    tools.r_li_config(
        raster="land",
        output="conf_once",
        method="moving_window",
        width=3,
        height=3,
        overwrite=True,
    )
    assert "MOVINGWINDOW" in (rli_dir / "conf_once").read_text()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frame": "region", "north": 8, "south": 2, "east": 9},  # west missing
        {"north": 8, "south": 2, "east": 9, "west": 2},  # needs frame=region
        {"method": "moving_window", "width": 3},  # height missing
        {"method": "moving_window", "width": 30, "height": 3},  # wider than raster
        {"method": "units", "width": 3, "height": 3},  # distribution missing
        {"method": "units", "width": 3, "height": 3, "distribution": "random"},
        {"method": "whole", "count": 4},  # count needs units
        {"frame": "region", "north": 2, "south": 8, "east": 9, "west": 2},
        {"frame": "region", "north": 12, "south": 2, "east": 9, "west": 2},
        {
            # Only 3x3 units of 3x3 cells fit into the 10x10 raster.
            "method": "units",
            "width": 3,
            "height": 3,
            "distribution": "random",
            "count": 10,
        },
    ],
    ids=[
        "missing_west",
        "missing_frame_region",
        "missing_height",
        "too_wide",
        "missing_distribution",
        "missing_count",
        "count_without_units",
        "north_below_south",
        "frame_outside_raster",
        "count_too_large",
    ],
)
def test_invalid_option_combinations(session, kwargs):
    """Invalid or incomplete option combinations end with an error"""
    tools = Tools(session=session)
    with pytest.raises(CalledModuleError):
        tools.r_li_config(raster="land", output="conf_invalid", **kwargs)


def test_nonexistent_raster(session):
    """A missing reference raster map ends with an error"""
    tools = Tools(session=session)
    with pytest.raises(CalledModuleError, match="not found"):
        tools.r_li_config(raster="does_not_exist", output="conf_missing")
