"""Tests of i.scatter"""

import json
import os
from io import StringIO

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

# The 3x4 test rasters are designed so that the 2D histogram is known by
# hand: with the columns raster as x and the rows raster as y, every
# (column, row) value pair occurs exactly once.
COLUMNS_RASTER = """\
north: 3
south: 0
east: 4
west: 0
rows: 3
cols: 4
1 2 3 4
1 2 3 4
1 2 3 4
"""

ROWS_RASTER = """\
north: 3
south: 0
east: 4
west: 0
rows: 3
cols: 4
1 1 1 1
2 2 2 2
3 3 3 3
"""

# Category 1 covers the top-left 2x2 block, category 2 the bottom-right
# 1x2 block, the rest is null.
TRAINING_RASTER = """\
north: 3
south: 0
east: 4
west: 0
rows: 3
cols: 4
1 1 * *
1 1 * *
* * 2 2
"""

# Same as the columns raster, but with a null in the top-right cell.
COLUMNS_WITH_NULL_RASTER = """\
north: 3
south: 0
east: 4
west: 0
rows: 3
cols: 4
1 2 3 *
1 2 3 4
1 2 3 4
"""

# One bin per integer value of the 3x4 test rasters (bins=4,3).
INTEGER_RANGE = "0.5,4.5,0.5,3.5"


@pytest.fixture
def session(tmp_path):
    """Active session in an XY project with the test rasters"""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        with Tools(session=session) as tools:
            tools.g_region(s=0, n=3, w=0, e=4, res=1)
            tools.r_in_ascii(input=StringIO(COLUMNS_RASTER), output="columns")
            tools.r_in_ascii(input=StringIO(ROWS_RASTER), output="rows")
            tools.r_in_ascii(input=StringIO(TRAINING_RASTER), output="training")
            tools.r_in_ascii(
                input=StringIO(COLUMNS_WITH_NULL_RASTER), output="columns_with_null"
            )
        yield session


def test_json_output(session):
    """Counts, edges, and metadata match the hand-computed histogram"""
    tools = Tools(session=session)
    data = json.loads(
        tools.i_scatter(input="columns,rows", bins=[4, 3], range=INTEGER_RANGE).text
    )
    assert data["input"] == ["columns", "rows"]
    assert data["training"] is None
    assert data["bins"] == [4, 3]
    assert data["x_edges"] == [0.5, 1.5, 2.5, 3.5, 4.5]
    assert data["y_edges"] == [0.5, 1.5, 2.5, 3.5]
    assert len(data["categories"]) == 1
    category = data["categories"][0]
    assert category["category"] is None
    assert category["cells"] == 12
    assert category["counts"] == [[1, 1, 1]] * 4


def test_json_training_categories(session):
    """Counts are reported per category of the training raster"""
    tools = Tools(session=session)
    data = json.loads(
        tools.i_scatter(
            input="columns,rows",
            training="training",
            bins=[4, 3],
            range=INTEGER_RANGE,
        ).text
    )
    assert data["training"] == "training"
    assert [category["category"] for category in data["categories"]] == [1, 2]
    category_1, category_2 = data["categories"]
    # Category 1: value pairs (1,1), (2,1), (1,2), (2,2).
    assert category_1["cells"] == 4
    assert category_1["counts"] == [
        [1, 1, 0],
        [1, 1, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]
    # Category 2: value pairs (3,3), (4,3).
    assert category_2["cells"] == 2
    assert category_2["counts"] == [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 1],
        [0, 0, 1],
    ]


def test_csv_output(session):
    """CSV lists every nonzero bin as zero-based indices with count"""
    tools = Tools(session=session)
    text = tools.i_scatter(
        input="columns,rows", bins=[4, 3], range=INTEGER_RANGE, format="csv"
    ).text
    lines = text.splitlines()
    assert lines[0] == "x_bin,y_bin,count"
    expected = [f"{x},{y},1" for x in range(4) for y in range(3)]
    assert lines[1:] == expected


def test_csv_training_output(session):
    """CSV with training has a category column and ordered rows"""
    tools = Tools(session=session)
    text = tools.i_scatter(
        input="columns,rows",
        training="training",
        bins=[4, 3],
        range=INTEGER_RANGE,
        format="csv",
    ).text
    assert text.splitlines() == [
        "category,x_bin,y_bin,count",
        "1,0,0,1",
        "1,0,1,1",
        "1,1,0,1",
        "1,1,1,1",
        "2,2,2,1",
        "2,3,2,1",
    ]


def test_nulls_excluded_and_default_range(session):
    """Null cells are not counted and the default range is from valid cells"""
    tools = Tools(session=session)
    data = json.loads(tools.i_scatter(input="columns_with_null,rows", bins=3).text)
    # Default range spans the joint non-null cells: x in [1, 4], y in [1, 3].
    assert data["x_edges"] == [1.0, 2.0, 3.0, 4.0]
    assert data["y_edges"] == pytest.approx([1.0, 5 / 3, 7 / 3, 3.0])
    category = data["categories"][0]
    # 11 cells are non-null in both rasters; values 3 and 4 share the
    # last x bin because the bins do not align with the integer values.
    assert category["cells"] == 11
    assert category["counts"] == [
        [1, 1, 1],
        [1, 1, 1],
        [1, 2, 2],
    ]


def test_default_integer_bins(session):
    """Integer inputs default to one bin per integer value"""
    tools = Tools(session=session)
    data = json.loads(tools.i_scatter(input="columns,rows").text)
    assert data["bins"] == [4, 3]
    assert data["x_edges"] == [0.5, 1.5, 2.5, 3.5, 4.5]
    assert data["y_edges"] == [0.5, 1.5, 2.5, 3.5]
    assert data["categories"][0]["cells"] == 12
    assert data["categories"][0]["counts"] == [[1, 1, 1]] * 4


def test_default_float_bins(session):
    """Floating-point inputs default to 255 bins over the data range"""
    tools = Tools(session=session)
    tools.r_mapcalc(expression="float_columns = float(columns)")
    data = json.loads(tools.i_scatter(input="float_columns,rows").text)
    assert data["bins"] == [255, 255]
    assert len(data["x_edges"]) == 256
    assert data["x_edges"][0] == 1.0
    assert data["x_edges"][-1] == 4.0
    assert data["y_edges"][0] == 1.0
    assert data["y_edges"][-1] == 3.0
    assert data["categories"][0]["cells"] == 12


def test_explicit_range_disables_integer_bins(session):
    """With range set and bins unset, integer inputs get 255 bins"""
    tools = Tools(session=session)
    data = json.loads(tools.i_scatter(input="columns,rows", range=INTEGER_RANGE).text)
    assert data["bins"] == [255, 255]
    assert data["categories"][0]["cells"] == 12


def test_constant_float_input(session):
    """A constant floating-point raster gets a padded range"""
    tools = Tools(session=session)
    tools.r_mapcalc(expression="float_constant = 5.0")
    data = json.loads(tools.i_scatter(input="float_constant,rows").text)
    assert data["x_edges"][0] == 4.5
    assert data["x_edges"][-1] == 5.5
    assert data["categories"][0]["cells"] == 12


def test_output_file(session, tmp_path):
    """Output goes to a file when requested"""
    tools = Tools(session=session)
    output_file = tmp_path / "scatter.json"
    tools.i_scatter(
        input="columns,rows", bins=[4, 3], range=INTEGER_RANGE, output=output_file
    )
    data = json.loads(output_file.read_text())
    assert data["categories"][0]["cells"] == 12


def test_matches_r_stats(session):
    """Default counts agree with r.stats -c for integer rasters"""
    tools = Tools(session=session)
    with Tools(session=session) as setup_tools:
        # Rasters with repeated value pairs for a non-trivial comparison.
        setup_tools.r_in_ascii(
            input=StringIO(
                "north: 3\nsouth: 0\neast: 4\nwest: 0\nrows: 3\ncols: 4\n"
                "1 1 2 3\n2 2 2 3\n3 1 1 1\n"
            ),
            output="values_x",
        )
        setup_tools.r_in_ascii(
            input=StringIO(
                "north: 3\nsouth: 0\neast: 4\nwest: 0\nrows: 3\ncols: 4\n"
                "1 2 2 1\n1 1 2 2\n2 2 1 1\n"
            ),
            output="values_y",
        )
    reference = {}
    for line in tools.r_stats(
        flags="cn", input="values_x,values_y", separator=","
    ).text.splitlines():
        value_x, value_y, count = line.split(",")
        reference[int(value_x), int(value_y)] = int(count)
    data = json.loads(tools.i_scatter(input="values_x,values_y").text)
    # With the default one bin per integer value, bin index plus the
    # minimum value (1 for both rasters) gives the cell value.
    assert data["bins"] == [3, 2]
    computed = {}
    for x_bin, row in enumerate(data["categories"][0]["counts"]):
        for y_bin, count in enumerate(row):
            if count:
                computed[x_bin + 1, y_bin + 1] = count
    assert computed == reference


def test_single_input_fails(session):
    """A single input raster is rejected"""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="two raster maps"):
        tools.i_scatter(input="columns")


def test_missing_input_fails(session):
    """A nonexistent input raster is rejected"""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="does_not_exist"):
        tools.i_scatter(input="columns,does_not_exist")


def test_float_training_fails(session):
    """A floating-point training raster is rejected"""
    tools = Tools(session=session)
    tools.r_mapcalc(expression="float_training = 1.5")
    with pytest.raises(ToolError, match="CELL"):
        tools.i_scatter(input="columns,rows", training="float_training")


def test_extra_range_values_fail(session):
    """More than four range values are rejected"""
    tools = Tools(session=session)
    # The parser itself rejects counts that are not multiples of four.
    with pytest.raises(ToolError, match="four values"):
        tools.i_scatter(input="columns,rows", range="0.5,4.5,0.5,3.5,0.5,4.5,0.5,3.5")
