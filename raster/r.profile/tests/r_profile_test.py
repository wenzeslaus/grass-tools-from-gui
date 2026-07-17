"""Tests for r.profile with the -s statistics extension.

The raster is a 3x6 grid and the profile runs west to east through the
middle row, sampling the cells at eastings 0.5 to 5.5 (the last cell is
null). The expected statistics are hand-computed from the sampled
values 10, 20, 30, 40, 50: the variance is the population variance
(sum of squared deviations divided by n), matching numpy's default and
the wxGUI profile statistics.
"""

import math
import os
from io import StringIO

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

ASCII_GRID = """\
north: 3
south: 0
east: 6
west: 0
rows: 3
cols: 6
1 2 3 4 5 6
10 20 30 40 50 *
7 8 9 10 11 12
"""

PROFILE_COORDINATES = (0.5, 1.5, 6, 1.5)

# Output of the original r.profile (built from raster/r.profile) for the
# raster, region, and coordinates above, captured from the original binary
# before this version replaced it in the local build.
ORIGINAL_PLAIN_OUTPUT = (
    " 0.000000 10\n"
    " 1.000000 20\n"
    " 2.000000 30\n"
    " 3.000000 40\n"
    " 4.000000 50\n"
    " 5.000000 *\n"
)
ORIGINAL_PLAIN_G_OUTPUT = (
    "0.500000 1.500000 0.000000 10\n"
    "1.500000 1.500000 1.000000 20\n"
    "2.500000 1.500000 2.000000 30\n"
    "3.500000 1.500000 3.000000 40\n"
    "4.500000 1.500000 4.000000 50\n"
    "5.500000 1.500000 5.000000 *\n"
)
ORIGINAL_JSON_OUTPUT = [
    {"distance": 0, "value": 10},
    {"distance": 1, "value": 20},
    {"distance": 2, "value": 30},
    {"distance": 3, "value": 40},
    {"distance": 4, "value": 50},
    {"distance": 5, "value": None},
]

EXPECTED_STATS = {
    "n": 5,
    "nulls": 1,
    "min": 10,
    "max": 50,
    "range": 40,
    "mean": 30,
    "stddev": math.sqrt(200),
    "variance": 200,
    "coeff_var": math.sqrt(200) / 30,
    "sum": 150,
    "median": 30,
}


@pytest.fixture
def session(tmp_path):
    """Active session in an XY project with the test raster"""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with (
        gs.setup.init(project, env=os.environ.copy()) as session,
        Tools(session=session) as tools,
    ):
        tools.g_region(n=3, s=0, e=6, w=0, res=1)
        tools.r_in_ascii(input=StringIO(ASCII_GRID), output="values", null_value="*")
        yield session


def test_default_plain_output_matches_original(session):
    """Plain output without -s is identical to the original tool's output"""
    tools = Tools(session=session)
    result = tools.r_profile(input="values", coordinates=PROFILE_COORDINATES)
    assert result.stdout == ORIGINAL_PLAIN_OUTPUT


def test_default_plain_g_output_matches_original(session):
    """Plain -g output without -s is identical to the original tool's output"""
    tools = Tools(session=session)
    result = tools.r_profile(input="values", coordinates=PROFILE_COORDINATES, flags="g")
    assert result.stdout == ORIGINAL_PLAIN_G_OUTPUT


def test_default_json_output_matches_original(session):
    """JSON output without -s is identical to the original tool's output"""
    tools = Tools(session=session)
    result = tools.r_profile(
        input="values", coordinates=PROFILE_COORDINATES, format="json"
    )
    assert result.json == ORIGINAL_JSON_OUTPUT


def test_stats_plain(session):
    """Plain -s output contains only the statistics as key=value lines"""
    tools = Tools(session=session)
    result = tools.r_profile(input="values", coordinates=PROFILE_COORDINATES, flags="s")
    stats = result.keyval
    assert set(stats.keys()) == set(EXPECTED_STATS.keys())
    for key, value in EXPECTED_STATS.items():
        # Plain output is rounded to six decimal places by %f.
        assert stats[key] == pytest.approx(value, abs=1e-6), key


def test_stats_json(session):
    """JSON -s output contains the points and a statistics object"""
    tools = Tools(session=session)
    result = tools.r_profile(
        input="values", coordinates=PROFILE_COORDINATES, flags="s", format="json"
    )
    data = result.json
    assert set(data.keys()) == {"points", "statistics"}
    assert data["points"] == ORIGINAL_JSON_OUTPUT
    stats = data["statistics"]
    assert set(stats.keys()) == set(EXPECTED_STATS.keys())
    for key, value in EXPECTED_STATS.items():
        assert stats[key] == pytest.approx(value), key


def test_stats_csv_rejected(session):
    """The -s flag is not supported with CSV output"""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="csv"):
        tools.r_profile(
            input="values",
            coordinates=PROFILE_COORDINATES,
            flags="s",
            format="csv",
        )
