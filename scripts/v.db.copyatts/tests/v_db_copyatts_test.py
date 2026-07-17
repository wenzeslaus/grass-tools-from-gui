"""Tests of v.db.copyatts."""

import os
from io import StringIO

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


@pytest.fixture
def tools(session):
    """Tools object with a small point map with attributes.

    The table has integer, double precision, and text columns and
    contains NULLs and a text value with an apostrophe:

    cat 1: Alice, 100, 1.5
    cat 2: O'Brien, NULL, NULL
    cat 3: NULL, NULL, 2.25
    """
    tools = Tools(session=session)
    data = "10|10|1|Alice|100|1.5\n20|20|2|O'Brien||\n30|30|3|||2.25\n"
    tools.v_in_ascii(
        input=StringIO(data),
        output="points",
        cat=3,
        columns=(
            "x double precision, y double precision, cat integer,"
            " name varchar(30), value integer, ratio double precision"
        ),
    )
    return tools


def row(tools, cat):
    """Return the attribute row of a category as a list of values."""
    text = tools.v_db_select(map="points", where=f"cat={cat}", flags="c").text
    return text.split("|")


def assert_same_attributes(tools, source_cat, target_cat):
    """Assert two rows are identical except for the key column (index 2)."""
    source = row(tools, source_cat)
    target = row(tools, target_cat)
    assert source[2] == str(source_cat)
    assert target[2] == str(target_cat)
    del source[2], target[2]
    assert source == target


def test_copy_single_target(tools):
    """Integer, double, and text values are copied to the target row."""
    tools.v_db_copyatts(map="points", from_category=1, to_category=5)
    assert row(tools, 5) == ["10", "10", "5", "Alice", "100", "1.5"]


def test_copy_preserves_nulls_and_quotes(tools):
    """NULL values stay NULL and text with an apostrophe is copied exactly."""
    tools.v_db_copyatts(map="points", from_category=2, to_category=6)
    assert row(tools, 6) == ["20", "20", "6", "O'Brien", "", ""]
    nulls = tools.db_select(
        sql="SELECT value IS NULL, ratio IS NULL FROM points WHERE cat=6",
        flags="c",
    ).text
    assert nulls == "1|1"


def test_copy_multiple_targets(tools):
    """One call copies the source row to several target categories."""
    tools.v_db_copyatts(map="points", from_category=3, to_category=[6, 7, 8])
    for cat in (6, 7, 8):
        assert_same_attributes(tools, 3, cat)


def test_duplicate_targets_copied_once(tools):
    """A repeated target category results in a single new row."""
    tools.v_db_copyatts(map="points", from_category=1, to_category=[5, 5])
    count = tools.db_select(
        sql="SELECT count(*) FROM points WHERE cat=5", flags="c"
    ).text
    assert count == "1"


def test_existing_target_fails_by_default(tools):
    """An existing target row causes an error and stays unchanged."""
    with pytest.raises(ToolError, match="already"):
        tools.v_db_copyatts(map="points", from_category=1, to_category=2)
    assert row(tools, 2) == ["20", "20", "2", "O'Brien", "", ""]


def test_existing_target_fails_before_any_change(tools):
    """When one target exists, rows for the other targets are not created."""
    with pytest.raises(ToolError, match="already"):
        tools.v_db_copyatts(map="points", from_category=1, to_category=[5, 2])
    count = tools.db_select(
        sql="SELECT count(*) FROM points WHERE cat=5", flags="c"
    ).text
    assert count == "0"


def test_force_replaces_existing_target(tools):
    """With -f, the existing target row is replaced by the source values."""
    tools.v_db_copyatts(map="points", from_category=1, to_category=2, flags="f")
    assert_same_attributes(tools, 1, 2)


def test_force_mixes_new_and_existing_targets(tools):
    """With -f, existing and new target categories are both written."""
    tools.v_db_copyatts(map="points", from_category=1, to_category=[2, 5], flags="f")
    assert_same_attributes(tools, 1, 2)
    assert_same_attributes(tools, 1, 5)


def test_missing_source_fails(tools):
    """A source category without an attribute row causes an error."""
    with pytest.raises(ToolError, match="No attribute row"):
        tools.v_db_copyatts(map="points", from_category=99, to_category=5)


def test_source_as_target_fails(tools):
    """The source category among the targets causes an error, no row added."""
    with pytest.raises(ToolError, match="target"):
        tools.v_db_copyatts(map="points", from_category=1, to_category=[1, 5])
    count = tools.db_select(
        sql="SELECT count(*) FROM points WHERE cat=5", flags="c"
    ).text
    assert count == "0"


def test_unconnected_layer_fails(tools):
    """A layer without a table connection causes an error."""
    with pytest.raises(ToolError, match="no table"):
        tools.v_db_copyatts(map="points", layer=3, from_category=1, to_category=5)


def test_nonexistent_map_fails(tools):
    """A map missing from the current mapset causes an error."""
    with pytest.raises(ToolError, match="not found"):
        tools.v_db_copyatts(map="does_not_exist", from_category=1, to_category=5)
