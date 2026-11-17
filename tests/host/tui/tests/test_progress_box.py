"""Headless tests of the progress box (ui/progress_box.py), no board.

A small host application with the dialog theme shows the box with
App.run_test(); the tests are synchronous and drive the pilot with
asyncio.run, as test_ui_commands does.

Checked: the gauge at 0, 30 and 100% and out of range (filled cells, label
centred, colours of the filled and empty parts), the moving block (size,
to and fro, never out of the gauge, moving only without a percentage),
update() in place (one box, new title, message and gauge, "Esc: close" only
without auto close), the auto close and its restart on update, a box covered
by a question that closes only once on top again, Escape and Enter, the
application keys passed with keys, and the contrast of the texts of the box.

Not tested here: the uses in the application (Export, connection lost) and
the rendering in a real terminal (checked by hand).

Version: 1.0
Date: 13/11/2026
Author: Z. BEN-AKKA
History:
  1.0  13/11/2026  Initial version.
"""

import asyncio
import time

import pytest

pytest.importorskip("textual")

from textual.app import App  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Vertical  # noqa: E402
from textual.widgets import Static  # noqa: E402

from ui import theme  # noqa: E402
from ui.app import ConfirmScreen  # noqa: E402
from ui.progress_box import BLOCK_SHARE, Gauge, ProgressBox  # noqa: E402

pytestmark = pytest.mark.ui

SIZE = (100, 24)
WAIT = 3.0  # Seconds a test waits for a state
STEP = 0.05
RECOVER = Binding("f7,ctrl+r", "app.recover", "Recover", key_display="F7/^R")


class Host(App):
    """The background of the box: the dialog theme and one application key."""

    BINDINGS = [("ctrl+r", "recover", "Recover")]

    def __init__(self):
        super().__init__()
        self.recovered = 0

    def compose(self):
        yield Static("Background")

    def on_mount(self) -> None:
        self.register_theme(theme.HIL_DIALOG)
        self.ansi_theme_light = theme.ANSI
        self.theme = theme.NAME

    def action_recover(self) -> None:
        self.recovered += 1


def drive(scenario):
    """Run scenario(pilot, app) on a new Host."""

    async def main():
        app = Host()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            return await scenario(pilot, app)

    return asyncio.run(main())


async def wait_for(pilot, condition, what: str, timeout: float = WAIT) -> float:
    """Poll until condition() holds; the seconds it took."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if condition():
            return time.monotonic() - start
        await pilot.pause(STEP)
    pytest.fail(f"timed out waiting for {what}")


async def show(pilot, app, box: ProgressBox) -> ProgressBox:
    app.push_screen(box)
    await wait_for(pilot, lambda: app.screen is box and box.query(Gauge), "the box")
    await pilot.pause()
    return box


def cells(gauge: Gauge) -> list:
    """(character, background is the primary colour) of each cell of the gauge."""
    filled = gauge.get_component_rich_style("gauge--filled")
    return [(segment.text, segment.style == filled) for segment in gauge.render().render(gauge.app.console)
            for _ in segment.text]


def box_count(app) -> int:
    return sum(isinstance(screen, ProgressBox) for screen in app.screen_stack)


# Gauge

@pytest.mark.parametrize("value, label", [(0, "0%"), (30, "30%"), (100, "100%"), (-5, "0%"), (140, "100%")],
                         ids=["0", "30", "100", "below-0", "above-100"])
def test_gauge_fill_and_label(value, label):
    async def scenario(pilot, app):
        box = await show(pilot, app, ProgressBox("Export", "Export in progress...", value))
        gauge = box.query_one(Gauge)
        line = cells(gauge)
        width = len(line)
        text = "".join(char for char, _ in line)
        filled = [index for index, (_, on) in enumerate(line) if on]
        percent = int(label[:-1])
        assert width == gauge.content_size.width > 0
        assert text.strip() == label
        assert text.index(label) == (width - len(label)) // 2  # Centred
        assert filled == list(range(round(width * percent / 100)))  # From the left, clamped to 0..100

    drive(scenario)


def test_gauge_colours():
    async def scenario(pilot, app):
        box = await show(pilot, app, ProgressBox("Export", "Export in progress...", 50))
        gauge = box.query_one(Gauge)
        filled = gauge.get_component_rich_style("gauge--filled")
        empty = gauge.get_component_rich_style("gauge--empty")
        assert filled.bgcolor.triplet.hex.upper() == theme.BLUE  # The fill is the primary colour
        assert filled.color.triplet.hex.upper() == theme.WHITE  # The label on the fill
        assert empty.color.triplet.hex.upper() == theme.BLUE  # The label on the grey

    drive(scenario)


@pytest.mark.parametrize("width", [58, 20, 7, 3, 1])
def test_moving_block_goes_to_and_fro(width):
    gauge = Gauge()
    size = max(1, width // BLOCK_SHARE)
    starts = []
    for step in range(4 * width + 3):
        gauge.step = step
        start, end = gauge.block(width)
        assert end - start == min(size, width)
        assert 0 <= start and end <= width
        starts.append(start)
    if width > size:
        assert starts[0] == 0 and max(starts) == width - size  # Both ends of the gauge
        moves = [b - a for a, b in zip(starts, starts[1:])]
        assert set(moves) == {1, -1}  # One cell per step, both ways


def test_moving_block_moves_only_without_percentage():
    async def scenario(pilot, app):
        box = await show(pilot, app, ProgressBox("Connection", "Connection lost", None))
        gauge = box.query_one(Gauge)
        first = gauge.step
        await wait_for(pilot, lambda: gauge.step >= first + 3, "the block to move")
        assert "%" not in "".join(char for char, _ in cells(gauge))
        box.update("Connection", "Connection back", 100)
        await pilot.pause(0.2)
        stopped = gauge.step
        await pilot.pause(0.4)
        assert gauge.step == stopped  # A percentage stops the block

    drive(scenario)


# Content and closing

def test_update_replaces_the_content_in_place():
    async def scenario(pilot, app):
        box = await show(pilot, app, ProgressBox("Connection", "Connection lost", None))
        frame = box.query_one("#box", Vertical)
        assert frame.border_title.strip() == "Connection"
        assert frame.border_subtitle.strip() == "Esc: close"
        box.update("Export", "Export in progress...", 25, auto_close=None)
        await pilot.pause()
        assert box_count(app) == 1 and app.screen is box
        assert frame.border_title.strip() == "Export"
        assert str(box.query_one("#box-message", Static).render()) == "Export in progress..."
        assert box.query_one(Gauge).value == 25
        box.update("Export", "Export done", 100, auto_close=WAIT)
        await pilot.pause()
        assert frame.border_subtitle == ""  # It closes by itself: no hint

    drive(scenario)


@pytest.mark.parametrize("delay", [0.5, 2.0])
def test_auto_close_after_the_delay(delay):
    async def scenario(pilot, app):
        start = time.monotonic()
        box = await show(pilot, app, ProgressBox("Export", "Export done", 100, auto_close=delay))
        await wait_for(pilot, lambda: box_count(app) == 0, "the auto close", delay + WAIT)
        took = time.monotonic() - start
        assert delay <= took <= delay + 2.0  # Never early; late only by the load of the host

    drive(scenario)


def test_update_restarts_the_auto_close():
    async def scenario(pilot, app):
        start = time.monotonic()
        box = await show(pilot, app, ProgressBox("Connection", "Connection back", 100, auto_close=2.0))
        await pilot.pause(1.2)
        box.update("Connection", "Connection back", 100, auto_close=2.0)
        await pilot.pause(1.2)
        assert box_count(app) == 1  # 2.4 s from the start, past the first delay; 1.2 s from the update
        await wait_for(pilot, lambda: box_count(app) == 0, "the auto close")
        assert time.monotonic() - start >= 3.2

    drive(scenario)


def test_auto_close_waits_until_on_top():
    async def scenario(pilot, app):
        box = await show(pilot, app, ProgressBox("Export", "Export done", 100, auto_close=0.3))
        question = ConfirmScreen("Flash hil-bench now?")
        app.push_screen(question)
        await pilot.pause(1.0)
        assert app.screen is question and box_count(app) == 1  # Not closed: the question would have gone
        question.dismiss(False)
        await wait_for(pilot, lambda: box_count(app) == 0, "the box to close once on top")
        assert not isinstance(app.screen, (ProgressBox, ConfirmScreen))

    drive(scenario)


@pytest.mark.parametrize("key", ["escape", "enter"])
def test_key_closes_a_box_without_auto_close(key):
    async def scenario(pilot, app):
        await show(pilot, app, ProgressBox("Export", "Export failed: no events.jsonl", 75))
        await pilot.pause(0.5)
        assert box_count(app) == 1  # Stays open
        await pilot.press(key)
        await wait_for(pilot, lambda: box_count(app) == 0, f"{key} to close the box")

    drive(scenario)


@pytest.mark.parametrize("keys, expected", [([RECOVER], 2), ([], 0)], ids=["passed", "not-passed"])
def test_application_keys_under_the_box(keys, expected):
    async def scenario(pilot, app):
        await show(pilot, app, ProgressBox("Connection", "Connection lost", None, keys=keys))
        await pilot.press("ctrl+r")
        await pilot.press("f7")
        await pilot.pause()
        assert app.recovered == expected
        assert box_count(app) == 1  # The key does not close the box

    drive(scenario)


def test_texts_readable():
    async def scenario(pilot, app):
        box = await show(pilot, app, ProgressBox("Export", "Export failed: no events.jsonl", 40))
        frame = box.query_one("#box", Vertical)
        surface = frame.styles.background.hex.upper()
        gauge = box.query_one(Gauge)
        filled = gauge.get_component_rich_style("gauge--filled")
        empty = gauge.get_component_rich_style("gauge--empty")
        pairs = {
            "title": (frame.styles.border_title_color.hex.upper(), surface),
            "hint": (frame.styles.border_subtitle_color.hex.upper(), surface),
            "message": (box.query_one("#box-message", Static).rich_style.color.triplet.hex.upper(), surface),
            "label on the fill": (filled.color.triplet.hex.upper(), filled.bgcolor.triplet.hex.upper()),
            "label on the grey": (empty.color.triplet.hex.upper(), surface),
        }
        low = {name: round(theme.contrast(*pair), 2) for name, pair in pairs.items()
               if theme.contrast(*pair) < theme.MIN_CONTRAST}
        assert not low, f"below {theme.MIN_CONTRAST}:1: {low}"

    drive(scenario)
