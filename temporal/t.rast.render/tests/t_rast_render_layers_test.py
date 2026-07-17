"""Tests of t.rast.render multi-layer rendering and legend support"""

import os
from io import StringIO

import pytest

import grass.script as gs
from grass.tools import ToolError, Tools

# Colors of the test maps as RGB tuples (GRASS standard color names).
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
ORANGE = (255, 128, 0)
WHITE = (255, 255, 255)

# Pixel positions in a 100x100 frame rendered from the 10x10 region:
# each cell is 10x10 pixels and row 1 is at the top.
NULL_AREA = (5, 5)  # Row 1: null in the series maps.
SERIES_AREA = (5, 55)  # Row 6: valid series values.
OVERLAY_AREA = (5, 95)  # Row 10: non-null cells of the overlay map.
LEGEND_AREA = (90, 75)  # Inside the color bar of d.legend at=10,40,85,95.


@pytest.fixture
def strds_session(tmp_path):
    """Active session with a two-map STRDS plus background and overlay maps.

    The series maps are null in the top three rows and single-valued
    elsewhere, each with a distinct color, so layer stacking and per-frame
    legends can be verified from frame pixel colors.
    """
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with (
        gs.setup.init(project, env=os.environ.copy()) as session,
        Tools(session=session) as tools,
    ):
        tools.g_region(s=0, n=10, w=0, e=10, res=1)
        for i, color in enumerate(["red", "yellow"], start=1):
            tools.r_mapcalc(expression=f"map{i} = if(row() <= 3, null(), {i})")
            tools.r_colors(map=f"map{i}", rules=StringIO(f"{i} {color}"))
        tools.r_mapcalc(expression="back = 5")
        tools.r_colors(map="back", rules=StringIO("5 blue"))
        tools.r_mapcalc(expression="over = if(row() >= 9, 7, null())")
        tools.r_colors(map="over", rules=StringIO("7 green"))
        tools.r_mapcalc(expression="over2 = if(row() <= 1, 8, null())")
        tools.r_colors(map="over2", rules=StringIO("8 orange"))
        tools.t_create(
            output="series",
            type="strds",
            temporaltype="absolute",
            title="Test series",
            description="Series for layer rendering tests",
        )
        tools.t_register(
            input="series",
            type="raster",
            maps="map1,map2",
            start="2020-01-01",
            increment="1 day",
            flags="i",
        )
        yield session


def render_frames(tools, tmp_path, **kwargs):
    """Render the series to two 100x100 frames and return them as PIL images"""
    from PIL import Image

    base = tmp_path / "frames" / "frame"
    tools.t_rast_render(
        input="series", output=base, format="frames", size="100,100", **kwargs
    )
    return [Image.open(f"{base}_{i:03d}.png").convert("RGB") for i in (1, 2)]


def test_background_visible_through_nulls(strds_session, tmp_path):
    """A background layer shows through null cells of the series map"""
    tools = Tools(session=strds_session)
    frames = render_frames(tools, tmp_path, background="d.rast map=back")
    for frame in frames:
        assert frame.getpixel(NULL_AREA) == BLUE
    assert frames[0].getpixel(SERIES_AREA) == RED
    assert frames[1].getpixel(SERIES_AREA) == YELLOW


def test_overlay_drawn_above_series(strds_session, tmp_path):
    """An overlay layer covers the series map where it has data"""
    tools = Tools(session=strds_session)
    frames = render_frames(tools, tmp_path, overlay="d.rast map=over")
    for frame in frames:
        assert frame.getpixel(OVERLAY_AREA) == GREEN
    assert frames[0].getpixel(SERIES_AREA) == RED
    # Without a background layer, null cells stay on the white background.
    assert frames[0].getpixel(NULL_AREA) == WHITE


def test_multiple_commands_per_option(strds_session, tmp_path):
    """Semicolon-separated commands in one option are all rendered"""
    tools = Tools(session=strds_session)
    frames = render_frames(tools, tmp_path, overlay="d.rast map=over; d.rast map=over2")
    assert frames[0].getpixel(OVERLAY_AREA) == GREEN
    assert frames[0].getpixel(NULL_AREA) == ORANGE


def test_legend_uses_map_of_each_frame(strds_session, tmp_path):
    """The legend is drawn from the series map of the current frame"""
    tools = Tools(session=strds_session)
    frames = render_frames(tools, tmp_path, legend="d.legend at=10,40,85,95")
    assert frames[0].getpixel(LEGEND_AREA) == RED
    assert frames[1].getpixel(LEGEND_AREA) == YELLOW


def test_legend_with_explicit_raster(strds_session, tmp_path):
    """An explicit raster= in the legend command is kept for all frames"""
    tools = Tools(session=strds_session)
    frames = render_frames(
        tools, tmp_path, legend="d.legend raster=back at=10,40,85,95"
    )
    for frame in frames:
        assert frame.getpixel(LEGEND_AREA) == BLUE


def test_gif_with_layers_legend_and_labels(strds_session, tmp_path):
    """All layer options combine with the gif format and time labels"""
    tools = Tools(session=strds_session)
    output = tmp_path / "layered.gif"
    tools.t_rast_render(
        input="series",
        output=output,
        format="gif",
        size="200,150",
        background="d.rast map=back",
        overlay="d.rast map=over",
        legend="d.legend at=10,40,85,95",
        flags="t",
    )
    assert output.read_bytes().startswith(b"GIF8")


def test_background_rejects_non_display_command(strds_session, tmp_path):
    """Non-display commands in the background option are rejected"""
    tools = Tools(session=strds_session)
    with pytest.raises(ToolError):
        tools.t_rast_render(
            input="series",
            output=tmp_path / "rejected.gif",
            background="g.region -p",
        )


def test_legend_rejects_other_command(strds_session, tmp_path):
    """The legend option accepts only a d.legend command"""
    tools = Tools(session=strds_session)
    with pytest.raises(ToolError):
        tools.t_rast_render(
            input="series",
            output=tmp_path / "rejected.gif",
            legend="d.barscale at=1,5",
        )
