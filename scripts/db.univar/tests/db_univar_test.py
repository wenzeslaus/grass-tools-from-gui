"""Test db.univar JSON output"""

import os

import pytest

import grass.script as gs
from grass.tools import Tools


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """Session with a table with values, an all-NULL table, and an empty table"""
    project = tmp_path_factory.mktemp("db_univar") / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        tools = Tools(session=session)
        # Set up the default database connection for the new mapset.
        tools.db_connect(flags="c")
        for sql in [
            "CREATE TABLE data (value DOUBLE PRECISION)",
            "INSERT INTO data VALUES (10.0)",
            "INSERT INTO data VALUES (20.0)",
            "INSERT INTO data VALUES (30.0)",
            "INSERT INTO data VALUES (NULL)",
            "CREATE TABLE null_data (value DOUBLE PRECISION)",
            "INSERT INTO null_data VALUES (NULL)",
            "CREATE TABLE empty_data (value DOUBLE PRECISION)",
        ]:
            tools.db_execute(sql=sql)
        yield session


def test_json_with_values(session):
    """Check JSON output values for a column with data"""
    tools = Tools(session=session)
    data = tools.db_univar(table="data", column="value", format="json").json
    assert data["n"] == 3
    assert data["min"] == 10.0
    assert data["max"] == 30.0
    assert data["sum"] == 60.0
    # The nested statistics object is kept for backward compatibility.
    assert data["statistics"]["n"] == 3


@pytest.mark.parametrize("table", ["null_data", "empty_data"])
@pytest.mark.parametrize("extended", [False, True], ids=["basic", "extended"])
def test_json_shape_without_values(session, table, extended):
    """Check that JSON has the same shape with and without non-null values"""
    tools = Tools(session=session)
    kwargs = {"flags": "e"} if extended else {}
    with_values = tools.db_univar(
        table="data", column="value", format="json", **kwargs
    ).json
    without_values = tools.db_univar(
        table=table, column="value", format="json", **kwargs
    ).json
    assert list(without_values.keys()) == list(with_values.keys())
    assert list(without_values["statistics"].keys()) == list(
        with_values["statistics"].keys()
    )
    assert without_values["n"] == 0
    assert without_values["min"] is None
    assert without_values["sum"] is None
    if extended:
        assert without_values["median"] is None
        assert without_values["percentiles"] == [{"percentile": 90.0, "value": None}]
