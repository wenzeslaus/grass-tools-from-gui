"""Tests of g.model.run."""

import importlib.util
import os
from pathlib import Path

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

TOOL_PATH = Path(__file__).parents[1] / "g.model.run.py"
SAMPLE_MODEL = (
    Path(__file__).parents[3]
    / "gui"
    / "wxpython"
    / "gmodeler"
    / "g_gui_gmodeler_zipcodes_avg_elevation.gxm"
)

# Two r.mapcalc actions where the first output is intermediate and the
# second action uses a model variable.
CHAIN_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>chain</name>
        <description>Two-step chain.</description>
    </properties>
    <variables>
        <variable name="offset" type="integer">
            <value>2</value>
            <description>Value added to the base map</description>
        </variable>
    </variables>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <flag name="overwrite" />
            <parameter name="expression">
                <value>step1 = 5</value>
            </parameter>
        </task>
    </action>
    <action id="2" name="r.mapcalc" pos="10,70" size="100,50">
        <task name="r.mapcalc">
            <flag name="overwrite" />
            <parameter name="expression">
                <value>result = step1 + %{offset}</value>
            </parameter>
        </task>
    </action>
    <data pos="10,130" size="100,50">
        <data-parameter prompt="raster">
            <value>step1</value>
        </data-parameter>
        <intermediate />
        <relation dir="to" id="1" name="output">
        </relation>
    </data>
</gxm>
"""

# The second action is disabled and the third has a parameterized flag
# (unset by default) which switches r.univar to shell script output.
MIXED_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>mixed</name>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <flag name="overwrite" />
            <parameter name="expression">
                <value>first = row()</value>
            </parameter>
        </task>
    </action>
    <action id="2" name="r.mapcalc" pos="10,70" size="100,50">
        <task name="r.mapcalc">
            <disabled />
            <parameter name="expression">
                <value>skipped = 1</value>
            </parameter>
        </task>
    </action>
    <action id="3" name="r.univar" pos="10,130" size="100,50">
        <task name="r.univar">
            <flag name="g" value="0" parameterized="1" />
            <parameter name="map">
                <value>first</value>
            </parameter>
        </task>
    </action>
</gxm>
"""

# One action with a parameterized option without a default value.
REQUIRED_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>required</name>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <parameterized />
                <value></value>
            </parameter>
        </task>
    </action>
</gxm>
"""

# A loop over a list literal followed by a loop over command output.
LOOP_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>looping</name>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>%{name} = 1</value>
            </parameter>
        </task>
    </action>
    <loop id="2" pos="10,70" size="100,50">
        <condition>name in ["loop_a", "loop_b"]</condition>
        <item>1</item>
    </loop>
    <action id="3" name="r.mapcalc" pos="10,130" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>copy_%{name} = %{name} + 1</value>
            </parameter>
        </task>
    </action>
    <loop id="4" pos="10,190" size="100,50">
        <condition>name in `g.list type=raster pattern=loop_*`</condition>
        <item>3</item>
    </loop>
</gxm>
"""

IF_ELSE_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>conditional</name>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>first = 1</value>
            </parameter>
        </task>
    </action>
    <if-else id="2" pos="10,70" size="100,50">
        <condition>1 == 1</condition>
        <if>
            <item>1</item>
        </if>
    </if-else>
</gxm>
"""


@pytest.fixture
def session(tmp_path):
    """Active session in a new XY project (scope: function)."""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        Tools(session=session).g_region(s=0, n=2, w=0, e=2, res=1)
        yield session


def write_model(tmp_path, text):
    """Write model text to a file and return the path"""
    path = tmp_path / "model.gxm"
    path.write_text(text)
    return path


def raster_maps(tools):
    """Get names of raster maps in the current mapset"""
    return tools.g_list(type="raster").text.splitlines()


def raster_min_max(tools, name):
    """Get (min, max) of a raster map"""
    info = tools.r_univar(map=name, flags="g").keyval
    return float(info["min"]), float(info["max"])


def test_chain_runs_and_removes_intermediate(session, tmp_path):
    """A two-action chain runs in order and intermediate data is removed."""
    tools = Tools(session=session)
    tools.g_model_run(input=write_model(tmp_path, CHAIN_MODEL))
    assert raster_min_max(tools, "result") == (7, 7)
    assert raster_maps(tools) == ["result"]


def test_variable_override_changes_result(session, tmp_path):
    """A variables option value overrides the model default."""
    tools = Tools(session=session)
    tools.g_model_run(input=write_model(tmp_path, CHAIN_MODEL), variables="offset=10")
    assert raster_min_max(tools, "result") == (15, 15)


def test_keep_intermediate_flag(session, tmp_path):
    """The -i flag keeps the intermediate map."""
    tools = Tools(session=session)
    tools.g_model_run(input=write_model(tmp_path, CHAIN_MODEL), flags="i")
    assert raster_maps(tools) == ["result", "step1"]


def test_unknown_variable_rejected(session, tmp_path):
    """A value for a variable which is not in the model is an error."""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="not defined in the model"):
        tools.g_model_run(input=write_model(tmp_path, CHAIN_MODEL), variables="other=1")


def test_disabled_action_skipped(session, tmp_path):
    """A disabled action does not run while the others do."""
    tools = Tools(session=session)
    tools.g_model_run(input=write_model(tmp_path, MIXED_MODEL))
    maps = raster_maps(tools)
    assert "first" in maps
    assert "skipped" not in maps


def test_parameterized_flag_override(session, tmp_path):
    """A parameterized flag referenced by action id changes the output."""
    tools = Tools(session=session)
    model = write_model(tmp_path, MIXED_MODEL)
    default_output = tools.g_model_run(input=model).text
    assert "n=4" not in default_output
    flag_output = tools.g_model_run(input=model, parameters="3.g=true").text
    assert "n=4" in flag_output


def test_missing_parameterized_value_fatal(session, tmp_path):
    """A parameterized option without a value is a clear error."""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match=r"1\.expression"):
        tools.g_model_run(input=write_model(tmp_path, REQUIRED_MODEL))


def test_parameterized_option_override(session, tmp_path):
    """A parameters option value fills a parameterized option."""
    tools = Tools(session=session)
    tools.g_model_run(
        input=write_model(tmp_path, REQUIRED_MODEL),
        parameters="1.expression=given = 4",
    )
    assert raster_min_max(tools, "given") == (4, 4)


def test_not_parameterized_option_rejected(session, tmp_path):
    """A value for an option which is not parameterized is an error."""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match=r"not.*parameterized"):
        tools.g_model_run(
            input=write_model(tmp_path, REQUIRED_MODEL), parameters="1.region=n=10"
        )


def test_loops(session, tmp_path):
    """Both loop condition forms (list literal and command) work."""
    tools = Tools(session=session)
    tools.g_model_run(input=write_model(tmp_path, LOOP_MODEL))
    assert raster_maps(tools) == ["copy_loop_a", "copy_loop_b", "loop_a", "loop_b"]
    assert raster_min_max(tools, "copy_loop_a") == (2, 2)


def test_if_else_not_supported(session, tmp_path):
    """A model with an if-else item fails with the documented error."""
    tools = Tools(session=session)
    with pytest.raises(ToolError, match="not supported"):
        tools.g_model_run(input=write_model(tmp_path, IF_ELSE_MODEL))


def test_parse_zipcodes_sample_model():
    """The parser reads the sample model shipped with the GUI."""
    spec = importlib.util.spec_from_file_location("g_model_run_tool", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    model = module.parse_gxm(SAMPLE_MODEL)
    assert model["properties"]["name"] == "zipcodes_avg_elevation"
    assert not model["properties"]["overwrite"]
    assert set(model["variables"]) == {"raster", "vector"}
    assert model["variables"]["raster"]["type"] == "file"
    assert (
        model["variables"]["raster"]["value"]
        == "/opt/geodata/ncrast/elev_state_500m.tif"
    )
    actions = [item for item in model["items"] if item["kind"] == "action"]
    assert [action["id"] for action in actions] == list(range(1, 14))
    assert actions[0]["module"] == "r.import"
    assert [flag["name"] for flag in actions[1]["flags"]] == ["o", "overwrite"]
    assert all(action["enabled"] for action in actions)
    assert all(not action["loop_ids"] for action in actions)
    r_colors = actions[6]
    assert r_colors["module"] == "r.colors"
    assert [
        param["name"] for param in r_colors["params"] if param["parameterized"]
    ] == ["color"]
    assert len(model["data"]) == 3
    assert not any(data["intermediate"] for data in model["data"])
    assert not model["condition_ids"]
