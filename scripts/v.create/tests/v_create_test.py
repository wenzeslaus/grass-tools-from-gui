"""Tests of v.create."""

import os

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


def test_create_without_table(session):
    """Without columns, the map exists and has no database connection."""
    tools = Tools(session=session)
    tools.v_create(output="plain")
    found = gs.find_file("plain", element="vector", env=session.env)
    assert found["name"] == "plain"
    # Tools returns None when the tool produces no output, i.e., when
    # v.db.connect -g has no connections to report.
    assert tools.v_db_connect(map="plain", flags="g") is None


def test_create_with_columns(session):
    """With columns, the table is connected and has key and user columns."""
    tools = Tools(session=session)
    tools.v_create(output="points", columns="name varchar(20),value integer")
    columns = tools.v_info(map="points", flags="c").text.splitlines()
    assert columns == ["INTEGER|cat", "CHARACTER|name", "INTEGER|value"]
    connection = tools.v_db_connect(map="points", flags="g").text
    assert connection.startswith("1/points|points|cat|")


def test_create_key_column_only_table(session):
    """The -t flag creates a table with only the key column."""
    tools = Tools(session=session)
    tools.v_create(output="keyonly", flags="t")
    columns = tools.v_info(map="keyonly", flags="c").text.splitlines()
    assert columns == ["INTEGER|cat"]


def test_insert_and_select(session):
    """A row inserted into the new table can be read back."""
    tools = Tools(session=session)
    tools.v_create(output="points", columns="name varchar(20),value integer")
    tools.db_execute(sql="INSERT INTO points (cat, name, value) VALUES (1, 'one', 42)")
    selected = tools.v_db_select(map="points").text.splitlines()
    assert selected == ["cat|name|value", "1|one|42"]


def test_overwrite(session):
    """An existing map is overwritten only with the overwrite flag."""
    tools = Tools(session=session)
    tools.v_create(output="points", columns="name varchar(20)")
    with pytest.raises(ToolError):
        tools.v_create(output="points")
    tools.v_create(output="points", overwrite=True)
    # The overwritten map should not have the old table connected
    # (no connections means no output and a None result).
    assert tools.v_db_connect(map="points", flags="g") is None


def test_failed_table_removes_map(session):
    """When table creation fails, the new map is removed (atomicity)."""
    tools = Tools(session=session)
    with pytest.raises(ToolError):
        tools.v_create(output="broken", columns="name nosuchtype((")
    found = gs.find_file("broken", element="vector", env=session.env)
    assert not found["name"]
