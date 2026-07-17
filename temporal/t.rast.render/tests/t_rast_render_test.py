"""Tests of t.rast.render"""

import os
import shutil

import pytest

import grass.script as gs
from grass.tools import Tools

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def strds_session(tmp_path):
    """Active session with an STRDS of three daily raster maps"""
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with (
        gs.setup.init(project, env=os.environ.copy()) as session,
        Tools(session=session) as tools,
    ):
        tools.g_region(s=0, n=10, w=0, e=10, res=1)
        for i in range(1, 4):
            tools.r_mapcalc(expression=f"map{i} = row() * {i}")
        tools.t_create(
            output="series",
            type="strds",
            temporaltype="absolute",
            title="Test series",
            description="Series for rendering tests",
        )
        tools.t_register(
            input="series",
            type="raster",
            maps="map1,map2,map3",
            start="2020-01-01",
            increment="1 day",
            flags="i",
        )
        yield session


def test_frames(strds_session, tmp_path):
    """Frames format creates one PNG file per registered map"""
    tools = Tools(session=strds_session)
    base = tmp_path / "sequence" / "frame"
    tools.t_rast_render(input="series", output=base, format="frames", size="120,90")
    frames = sorted(base.parent.iterdir())
    assert [path.name for path in frames] == [
        "frame_001.png",
        "frame_002.png",
        "frame_003.png",
    ]
    for frame in frames:
        assert frame.read_bytes().startswith(PNG_MAGIC)


def test_gif(strds_session, tmp_path):
    """GIF format creates a file with the GIF magic number"""
    tools = Tools(session=strds_session)
    output = tmp_path / "animation.gif"
    tools.t_rast_render(input="series", output=output, format="gif", size="120,90")
    assert output.read_bytes().startswith(b"GIF8")


def test_gif_with_time_labels(strds_session, tmp_path):
    """The -t flag draws time stamp labels without error"""
    tools = Tools(session=strds_session)
    output = tmp_path / "labeled.gif"
    tools.t_rast_render(
        input="series", output=output, format="gif", size="200,150", flags="t"
    )
    assert output.read_bytes().startswith(b"GIF8")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
def test_avi(strds_session, tmp_path):
    """AVI format creates a RIFF AVI file"""
    tools = Tools(session=strds_session)
    output = tmp_path / "animation.avi"
    tools.t_rast_render(
        input="series", output=output, format="avi", size="120,90", fps=5
    )
    content = output.read_bytes()
    assert content.startswith(b"RIFF")
    assert content[8:12] == b"AVI "


def test_where(strds_session, tmp_path):
    """The where option limits the rendered maps"""
    tools = Tools(session=strds_session)
    base = tmp_path / "subset"
    tools.t_rast_render(
        input="series",
        output=base,
        format="frames",
        size="120,90",
        where="start_time >= '2020-01-02'",
    )
    frames = sorted(tmp_path.glob("subset_*.png"))
    assert len(frames) == 2
