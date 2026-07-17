"""Tests of g.model.export with the pywps, actinia, and if-else extensions."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

TOOL_PATH = Path(__file__).parents[1] / "g.model.export.py"
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

# A parameterized option and flag, a disabled action, and the model
# overwrite property.
MIXED_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>mixed</name>
        <flag name="overwrite" />
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>first = 1</value>
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
    <action id="3" name="r.colors" pos="10,130" size="100,50">
        <task name="r.colors">
            <flag name="n" value="0" parameterized="1" />
            <parameter name="map">
                <value>first</value>
            </parameter>
            <parameter name="color">
                <parameterized />
                <value>grey</value>
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

# An if-else condition with a constant condition and only an if branch.
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

# An if-else condition selecting a branch based on a model variable.
IF_ELSE_VARIABLE_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>conditional</name>
    </properties>
    <variables>
        <variable name="threshold" type="integer">
            <value>3</value>
            <description>Branch selector</description>
        </variable>
    </variables>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>yes_map = 1</value>
            </parameter>
        </task>
    </action>
    <if-else id="2" pos="10,70" size="100,50">
        <condition>%{threshold} &gt; 5</condition>
        <if>
            <item>1</item>
        </if>
        <else>
            <item>3</item>
        </else>
    </if-else>
    <action id="3" name="r.mapcalc" pos="10,130" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>no_map = 1</value>
            </parameter>
        </task>
    </action>
</gxm>
"""

# An if-else condition whose only action is disabled (the generated
# branch needs a pass statement to stay valid Python).
IF_ELSE_DISABLED_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>conditional_disabled</name>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <disabled />
            <parameter name="expression">
                <value>skipped = 1</value>
            </parameter>
        </task>
    </action>
    <if-else id="2" pos="10,70" size="100,50">
        <condition>2 &gt; 1</condition>
        <if>
            <item>1</item>
        </if>
    </if-else>
</gxm>
"""

# An action creating an input for a second action with a parameterized
# output option (r.slope.aspect has interface-declared outputs, which
# the pywps and actinia exports classify by the option age).
SLOPE_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>slope</name>
        <description>Compute slope from generated elevation.</description>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>elev = row()</value>
            </parameter>
        </task>
    </action>
    <action id="2" name="r.slope.aspect" pos="10,70" size="100,50">
        <task name="r.slope.aspect">
            <parameter name="elevation">
                <value>elev</value>
            </parameter>
            <parameter name="slope">
                <parameterized />
                <value>slope</value>
            </parameter>
        </task>
    </action>
</gxm>
"""

# One plain action without variables or parameterization.
SIMPLE_MODEL = """\
<?xml version="1.0" encoding="UTF-8"?>
<gxm>
    <properties>
        <name>simple</name>
    </properties>
    <action id="1" name="r.mapcalc" pos="10,10" size="100,50">
        <task name="r.mapcalc">
            <parameter name="expression">
                <value>plain = 1</value>
            </parameter>
        </task>
    </action>
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


def export_model(tools, tmp_path, model_text, name="model", format="python"):
    """Export model text in the given format and return the output path"""
    model = tmp_path / f"{name}.gxm"
    model.write_text(model_text)
    extension = "json" if format == "actinia" else "py"
    output = tmp_path / f"{name}_{format}.{extension}"
    tools.g_model_export(input=model, output=output, format=format)
    return output


def run_script(script, session, *args):
    """Run a generated script in the session and check that it succeeds"""
    result = subprocess.run(
        [sys.executable, str(script), *args],
        env=session.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


def raster_maps(tools):
    """Get names of raster maps in the current mapset"""
    # Without maps there is no output and the Tools call returns None.
    result = tools.g_list(type="raster")
    return result.text.splitlines() if result is not None else []


def raster_min_max(tools, name):
    """Get (min, max) of a raster map"""
    info = tools.r_univar(map=name, flags="g").keyval
    return float(info["min"]), float(info["max"])


def test_export_is_valid_python(session, tmp_path):
    """The exported script exists and compiles as Python."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, CHAIN_MODEL)
    assert script.exists()
    compile(script.read_text(), str(script), "exec")


def test_existing_output_needs_overwrite(session, tmp_path):
    """An existing output file is only replaced with --overwrite."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, CHAIN_MODEL)
    model = tmp_path / "model.gxm"
    with pytest.raises(ToolError, match="exists"):
        tools.g_model_export(input=model, output=script, format="python")
    tools.g_model_export(input=model, output=script, format="python", overwrite=True)


def test_exported_chain_runs(session, tmp_path):
    """The exported script runs the chain and cleans up the intermediate."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, CHAIN_MODEL)
    run_script(script, session)
    assert raster_min_max(tools, "result") == (7, 7)
    assert raster_maps(tools) == ["result"]


def test_variable_becomes_script_option(session, tmp_path):
    """A model variable is a script option and its value is used."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, CHAIN_MODEL)
    source = script.read_text()
    assert "# % key: offset" in source
    assert "# % answer: 2" in source
    run_script(script, session, "offset=10")
    assert raster_min_max(tools, "result") == (15, 15)


def test_parameterized_option_becomes_script_option(session, tmp_path):
    """A parameterized option and flag surface as script options."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, MIXED_MODEL)
    source = script.read_text()
    assert "# % key: rcolors3_color" in source
    assert "# % key: rcolors3_n" in source
    run_script(script, session)
    assert "1 127:127:127" in tools.r_colors_out(map="first").text
    run_script(script, session, "rcolors3_color=bgyr")
    # For the single-value map, bgyr assigns its middle color.
    assert "1 255:127:0" in tools.r_colors_out(map="first").text


def test_disabled_action_commented_out(session, tmp_path):
    """A disabled action is present only as a comment and does not run."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, MIXED_MODEL)
    source = script.read_text()
    assert "# Action (2) r.mapcalc is disabled in the model:" in source
    assert '# run_command("r.mapcalc",' in source
    run_script(script, session)
    assert "skipped" not in raster_maps(tools)


def test_exported_loops_run(session, tmp_path):
    """Loops are exported for both condition forms and run correctly."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, LOOP_MODEL)
    run_script(script, session)
    assert raster_maps(tools) == ["copy_loop_a", "copy_loop_b", "loop_a", "loop_b"]
    assert raster_min_max(tools, "copy_loop_b") == (2, 2)


def test_if_else_exports_and_runs(session, tmp_path):
    """An if branch with a constant condition is exported and runs."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, IF_ELSE_MODEL)
    source = script.read_text()
    assert "    if 1 == 1:" in source
    run_script(script, session)
    assert "first" in raster_maps(tools)


def test_if_else_variable_selects_branch(session, tmp_path):
    """A variable in the condition selects the branch at run time."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, IF_ELSE_VARIABLE_MODEL)
    source = script.read_text()
    assert '    if int(options["threshold"]) > 5:' in source
    assert "    else:" in source
    run_script(script, session)
    assert raster_maps(tools) == ["no_map"]
    run_script(script, session, "threshold=9")
    assert raster_maps(tools) == ["no_map", "yes_map"]


def test_if_else_disabled_action_gets_pass(session, tmp_path):
    """A branch with only a disabled action stays valid and runs."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, IF_ELSE_DISABLED_MODEL)
    source = script.read_text()
    assert "# Action (1) r.mapcalc is disabled in the model:" in source
    assert "        pass" in source
    run_script(script, session)
    assert "skipped" not in raster_maps(tools)


def test_pywps_export_compiles_with_inputs_and_outputs(session, tmp_path):
    """The PyWPS export compiles and exposes inputs, outputs, and exports."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, SLOPE_MODEL, format="pywps")
    source = script.read_text()
    compile(source, str(script), "exec")
    assert "class Model(Process):" in source
    assert 'identifier="slope",' in source
    assert 'identifier="rslopeaspect2_slope",' in source
    assert "outputs.append(ComplexOutput(" in source
    assert 'supported_formats=[Format("image/tif")]))' in source
    assert 'slope=request.inputs["rslopeaspect2_slope"][0].data)' in source
    assert 'run_command("r.out.gdal",' in source
    assert (
        'response.outputs["rslopeaspect2_slope"].file = os.path.join('
        "tempfile.gettempdir(), "
        'request.inputs["rslopeaspect2_slope"][0].data + ".tif")'
    ) in source


def test_pywps_variable_and_mixed_value(session, tmp_path):
    """A model variable becomes a LiteralInput used through an f-string."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, CHAIN_MODEL, format="pywps")
    source = script.read_text()
    compile(source, str(script), "exec")
    assert 'identifier="offset",' in source
    assert 'data_type="integer",' in source
    assert "default=2))" in source
    assert (
        "expression=f\"result = step1 + {request.inputs['offset'][0].data}\"" in source
    )


def test_pywps_parameterized_flag_and_disabled_action(session, tmp_path):
    """Parameterized flags become inputs; disabled actions are comments."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, MIXED_MODEL, format="pywps")
    source = script.read_text()
    compile(source, str(script), "exec")
    assert 'identifier="rcolors3_n",' in source
    assert 'flags=get_parameterized_flags(request.inputs, ["rcolors3_n"])' in source
    assert "def get_parameterized_flags(inputs, keys):" in source
    assert '# run_command("r.mapcalc",' in source


def test_pywps_loops_and_if_else(session, tmp_path):
    """Loops and if-else conditions are exported into the handler."""
    tools = Tools(session=session)
    script = export_model(tools, tmp_path, LOOP_MODEL, name="looping", format="pywps")
    source = script.read_text()
    compile(source, str(script), "exec")
    assert "from grass.script import read_command, run_command" in source
    assert '        for name in ["loop_a", "loop_b"]:' in source
    script = export_model(
        tools, tmp_path, IF_ELSE_VARIABLE_MODEL, name="conditional", format="pywps"
    )
    source = script.read_text()
    compile(source, str(script), "exec")
    assert '        if int(request.inputs["threshold"][0].data) > 5:' in source


def test_actinia_json_structure(session, tmp_path):
    """The actinia export is valid JSON with the GUI export's structure."""
    tools = Tools(session=session)
    output = export_model(tools, tmp_path, SLOPE_MODEL, format="actinia")
    chain = json.loads(output.read_text())
    assert chain["id"] == "model"
    assert chain["description"] == "Compute slope from generated elevation."
    assert chain["version"] == "1"
    # Parameterized options make the process list a template.
    entries = chain["template"]["list"]
    assert [entry["module"] for entry in entries] == ["r.mapcalc", "r.slope.aspect"]
    assert entries[0]["id"] == "rmapcalc1"
    assert entries[0]["inputs"] == [{"param": "expression", "value": "elev = row()"}]
    assert entries[1]["inputs"] == [{"param": "elevation", "value": "elev"}]
    assert entries[1]["outputs"] == [
        {"param": "slope", "value": '{{ rslopeaspect2_slope|default("slope") }}'}
    ]


def test_actinia_variable_placeholder(session, tmp_path):
    """A model variable reference becomes an inline Jinja placeholder."""
    tools = Tools(session=session)
    output = export_model(tools, tmp_path, CHAIN_MODEL, format="actinia")
    chain = json.loads(output.read_text())
    entries = chain["template"]["list"]
    assert entries[1]["inputs"] == [
        {"param": "expression", "value": "result = step1 + {{ offset|default(2) }}"}
    ]


def test_actinia_without_placeholders_is_not_templated(session, tmp_path):
    """A model without parameterization exports a plain process chain."""
    tools = Tools(session=session)
    output = export_model(tools, tmp_path, SIMPLE_MODEL, format="actinia")
    chain = json.loads(output.read_text())
    assert "template" not in chain
    assert [entry["module"] for entry in chain["list"]] == ["r.mapcalc"]


def test_actinia_skips_disabled_action(session, tmp_path):
    """A disabled action is left out of the actinia process chain."""
    tools = Tools(session=session)
    output = export_model(tools, tmp_path, MIXED_MODEL, format="actinia")
    chain = json.loads(output.read_text())
    entries = chain["template"]["list"]
    assert [entry["id"] for entry in entries] == ["rmapcalc1", "rcolors3"]
    assert entries[1]["inputs"] == [
        {"param": "map", "value": "first"},
        {"param": "color", "value": '{{ rcolors3_color|default("grey") }}'},
    ]


def test_actinia_rejects_loops_and_if_else(session, tmp_path):
    """Loops and if-else conditions cannot be expressed in actinia."""
    tools = Tools(session=session)
    for model_text in (LOOP_MODEL, IF_ELSE_MODEL):
        model = tmp_path / "model.gxm"
        model.write_text(model_text)
        with pytest.raises(ToolError, match="actinia"):
            tools.g_model_export(
                input=model, output=tmp_path / "chain.json", format="actinia"
            )


def test_sample_model_exports_to_all_formats(session, tmp_path):
    """The sample model exports to pywps and actinia as well."""
    tools = Tools(session=session)
    script = tmp_path / "zipcodes_pywps.py"
    tools.g_model_export(input=SAMPLE_MODEL, output=script, format="pywps")
    compile(script.read_text(), str(script), "exec")
    output = tmp_path / "zipcodes_actinia.json"
    tools.g_model_export(input=SAMPLE_MODEL, output=output, format="actinia")
    chain = json.loads(output.read_text())
    assert len(chain["template"]["list"]) == 13


def test_zipcodes_sample_model_exports(session, tmp_path):
    """The sample model shipped with the GUI exports to valid Python."""
    tools = Tools(session=session)
    script = tmp_path / "zipcodes.py"
    tools.g_model_export(input=SAMPLE_MODEL, output=script)
    source = script.read_text()
    compile(source, str(script), "exec")
    assert "# % key: rcolors7_color" in source
    assert "# % key: raster" in source
    assert "# % key: vector" in source


def test_parse_zipcodes_sample_model():
    """The parser reads the sample model shipped with the GUI."""
    spec = importlib.util.spec_from_file_location("g_model_export_tool", TOOL_PATH)
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
    assert not [item for item in model["items"] if item["kind"] == "condition"]
