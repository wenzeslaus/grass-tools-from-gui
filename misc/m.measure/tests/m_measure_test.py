"""Tests for m.measure with bearing output"""

import json
import math
import os
import shlex
from pathlib import Path

import pytest

import grass.script as gs
from grass.tools import Tools

ORIGINAL_OUTPUT_FILE = Path(__file__).parent / "original_output.txt"


@pytest.fixture
def session(tmp_path):
    """Active session in an XY project (scope: function)"""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        yield session


@pytest.mark.parametrize(
    ("coordinates", "length", "bearing"),
    [
        ((0, 0, 0, 1), 1, 0),  # north
        ((0, 0, 1, 0), 1, 90),  # east
        ((0, 0, 0, -1), 1, 180),  # south
        ((0, 0, -1, 0), 1, 270),  # west
        ((0, 0, 1, 1), math.sqrt(2), 45),  # northeast
        ((0, 0, -1, -1), math.sqrt(2), 225),  # southwest, normalized to 0-360
    ],
    ids=["north", "east", "south", "west", "northeast", "southwest"],
)
def test_single_segment(session, coordinates, length, bearing):
    """Check distance and bearing of a single segment in JSON output"""
    tools = Tools(session=session)
    result = tools.m_measure(
        coordinates=coordinates, units="meters", format="json"
    ).json
    assert result["length"] == pytest.approx(length)
    assert result["bearings"] == pytest.approx([bearing])
    assert result["units"]["length"] == "meters"
    assert result["units"]["bearing"] == "degrees"


def test_multiple_segments_and_area(session):
    """Check per-segment bearings and area for a closed square"""
    tools = Tools(session=session)
    result = tools.m_measure(
        coordinates=(0, 0, 2, 0, 2, 2, 0, 2), units="meters", format="json"
    ).json
    assert result["length"] == pytest.approx(6)
    assert result["bearings"] == pytest.approx([90, 0, 270])
    assert result["area"] == pytest.approx(4)


def test_plain_format(session):
    """Check the exact plain text output including the bearing line"""
    tools = Tools(session=session)
    result = tools.m_measure(coordinates=(0, 0, 1, 1), units="meters")
    assert result.text == ("Length:    1.414214 meters\nBearing:  45.000000 degrees")


def test_shell_format(session):
    """Check the exact shell script style output including the bearing line"""
    tools = Tools(session=session)
    result = tools.m_measure(
        coordinates=(0, 0, 0, 1, 1, 1), units="meters", format="shell"
    )
    assert result.text == (
        "units=meters,square meters\nlength=2.000000\nbearing=0.000000,90.000000"
    )


def read_original_outputs():
    """Read commands and their outputs captured from the original m.measure"""
    cases = []
    command = None
    lines = []
    for line in ORIGINAL_OUTPUT_FILE.read_text().splitlines():
        if line.startswith("# command: "):
            if command:
                cases.append((command, lines))
            command = line.removeprefix("# command: ")
            lines = []
        else:
            lines.append(line)
    cases.append((command, lines))
    return cases


@pytest.mark.parametrize(
    ("command", "original_lines"),
    read_original_outputs(),
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_original_output_preserved(session, command, original_lines):
    """Check that every line the original m.measure printed is still printed

    The file original_output.txt was captured by running m.measure
    before the bearing change. The tool must produce all of these
    lines unchanged; bearing output is only added. JSON is compared
    semantically because adding a key changes the comma placement of the
    preceding line.
    """
    tools = Tools(session=session)
    new_text = tools.run_cmd(shlex.split(command)).text
    if "format=json" in command:
        original = json.loads("\n".join(original_lines))
        new = json.loads(new_text)
        assert original["length"] == new["length"]
        assert original["area"] == new["area"]
        assert original["units"]["length"] == new["units"]["length"]
        assert original["units"]["area"] == new["units"]["area"]
    else:
        new_lines = new_text.splitlines()
        for line in original_lines:
            assert line in new_lines
