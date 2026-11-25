"""Headless tests of the Options window and of the operator instructions, on the fake firmware.

No board. The fake bench and the fake runs are those of test_ui_commands and
test_faults; the run factory keeps the environment it gets. The options come
from a file of tmp_path, so the real run_options.yaml can change freely.

Checked: the Options button opens the window with the current values, OK
keeps them, shows them on the Options line and gives them to the next pytest
run, they stay for the run after, Cancel and Escape change nothing, a refused
value keeps the window open with its rule, T1-T8 gets no option, the values
start from the environment, a bad file shows its error; an instruction of the
logger hil.operator shows on the progress line until its test ends, and the
TX and RX lines never hide it.

Not tested here: the options file and its rules (test_run_options.py), the
pytest process (test_runner.py), and the operator tests themselves, played by
hand on the board.

Version: 1.0
Date: 23/11/2026
Author: Z. BEN-AKKA
History:
  1.0  23/11/2026  Initial version.
"""

import asyncio
import time

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Checkbox, Input, Select, Static  # noqa: E402

import test_faults as faults  # noqa: E402
import test_ui_commands as ui  # noqa: E402
from core.session import State  # noqa: E402
from test_run_options import GOOD, write  # noqa: E402
from ui import tests_pane  # noqa: E402  (the module: pytest would try to collect the class TestsPane)
from ui.app import HilApp  # noqa: E402
from ui.options_screen import OptionsScreen  # noqa: E402

pytestmark = pytest.mark.ui

NODEID = "cases/test_touch.py::test_touch_draw"
INSTRUCTION = "Draw on the screen with one finger"


class Runs:
    """Run factory that keeps the environment of each run."""

    def __init__(self, root):
        self.root = root
        self.envs = []

    def __call__(self, kind, selection, on_event, env=None, **kwargs):
        self.envs.append(env)
        return faults.FakeRun(kind, on_event, self.root / f"run-{len(self.envs)}")


def drive(tmp_path, scenario, text: str = GOOD, environ: dict | None = None) -> None:
    rig = ui.Rig()
    runs = Runs(tmp_path / "runs")
    path = write(tmp_path, text)

    async def main():
        app = HilApp(rig.bench, ui.CATALOG, rig.session, run_factory=runs, options_file=path,
                     discover=lambda *args, **kwargs: [], environ=environ or {})
        try:
            async with app.run_test(size=ui.SIZE) as pilot:
                await ui.until(pilot, app, State.CONNECTED)
                await pilot.press("ctrl+o")  # Tests tab
                await ui.settle(pilot, app)
                await scenario(pilot, app, runs)
        finally:
            if app.session is not None:
                app.session.shutdown()

    asyncio.run(main())


async def open_window(pilot, app) -> None:
    await pilot.click("#options")
    await ui.wait_for(pilot, lambda: isinstance(app.screen, OptionsScreen), "the Options window")
    await pilot.pause()


async def close(pilot, app, button: str = "#ok") -> None:
    await pilot.click(button)
    await ui.wait_for(pilot, lambda: not isinstance(app.screen, OptionsScreen), "the window to close")
    await pilot.pause()


def fill(app, operator: bool | None = None, colour: str | None = None, other: str | None = None,
         seed: str | None = None) -> None:
    screen = app.screen
    if operator is not None:
        screen.query_one("#opt-FAKE_OPERATOR", Checkbox).value = operator
    if colour is not None:
        screen.query_one("#opt-FAKE_COLOUR", Select).value = colour
    if other is not None:
        screen.query_one("#other-FAKE_COLOUR", Input).value = other
    if seed is not None:
        screen.query_one("#opt-FAKE_SEED", Input).value = seed


def line(app) -> str:
    return ui.text(app, "#options-text")


async def run(pilot, app, kind: str = "pytest") -> None:
    """Start a run of that kind, end it, and wait until the TUI is connected again."""
    app.tests.post_message(tests_pane.TestsPane.Run(kind, ["T1"] if kind == "rx_check" else [], kind == "pytest"))
    await ui.wait_for(pilot, lambda: app.active_run is not None, "the run start")
    app.active_run.finish()
    await ui.wait_for(pilot, lambda: app.active_run is None, "the run end")


# Options window

def test_chosen_options_reach_the_runs(tmp_path):
    async def scenario(pilot, app, runs):
        assert "none" in line(app)
        await open_window(pilot, app)
        fill(app, operator=True, colour="red", seed="42")
        await close(pilot, app)
        assert "FAKE_OPERATOR=1 FAKE_COLOUR=red FAKE_SEED=42" in line(app)
        sent = {"FAKE_OPERATOR": "1", "FAKE_COLOUR": "red", "FAKE_SEED": "42"}
        await run(pilot, app)
        await ui.until(pilot, app, State.CONNECTED)
        await run(pilot, app)  # Kept from one run to the next
        assert runs.envs == [sent, sent]

    drive(tmp_path, scenario)


def test_default_options_are_removed_from_the_run(tmp_path):
    async def scenario(pilot, app, runs):
        await run(pilot, app)
        assert runs.envs == [{"FAKE_OPERATOR": None, "FAKE_COLOUR": None, "FAKE_SEED": None}]

    drive(tmp_path, scenario)


def test_rx_check_gets_no_option(tmp_path):
    async def scenario(pilot, app, runs):
        await open_window(pilot, app)
        fill(app, operator=True)
        await close(pilot, app)
        await run(pilot, app, "rx_check")
        assert runs.envs == [{}]

    drive(tmp_path, scenario)


def test_typed_value_wins_and_comes_back(tmp_path):
    async def scenario(pilot, app, runs):
        await open_window(pilot, app)
        fill(app, colour="red", other="0x07E0")
        await close(pilot, app)
        assert "FAKE_COLOUR=0x07E0" in line(app)
        await open_window(pilot, app)
        assert app.screen.query_one("#other-FAKE_COLOUR", Input).value == "0x07E0"
        fill(app, other="Rouge")  # An alias
        await close(pilot, app)
        assert "FAKE_COLOUR=red" in line(app)
        await open_window(pilot, app)
        assert app.screen.query_one("#other-FAKE_COLOUR", Input).value == ""
        assert app.screen.query_one("#opt-FAKE_COLOUR", Select).value == "red"

    drive(tmp_path, scenario)


@pytest.mark.parametrize("cancel", ["button", "escape"])
def test_cancel_changes_nothing(tmp_path, cancel):
    async def scenario(pilot, app, runs):
        await open_window(pilot, app)
        fill(app, operator=True, colour="red", seed="1")
        if cancel == "button":
            await close(pilot, app, "#cancel")
        else:
            await pilot.press("escape")
            await ui.wait_for(pilot, lambda: not isinstance(app.screen, OptionsScreen), "the window to close")
        assert "none" in line(app)

    drive(tmp_path, scenario)


def test_refused_value_keeps_the_window(tmp_path):
    async def scenario(pilot, app, runs):
        await open_window(pilot, app)
        fill(app, other="pink", seed="100")
        await pilot.click("#ok")
        await pilot.pause()
        assert isinstance(app.screen, OptionsScreen)
        errors = {name: str(app.screen.query_one(f"#err-{name}", Static).render())
                  for name in ("FAKE_OPERATOR", "FAKE_COLOUR", "FAKE_SEED")}
        assert errors["FAKE_OPERATOR"] == ""
        assert "one of black, red, cyan, or 0x and 4 digits" in errors["FAKE_COLOUR"]
        assert "from 0 to 99" in errors["FAKE_SEED"]
        fill(app, other="", seed="99")
        app.screen.query_one("#opt-FAKE_SEED", Input).focus()
        await pilot.press("enter")  # Enter in a field is OK
        await ui.wait_for(pilot, lambda: not isinstance(app.screen, OptionsScreen), "the window to close")
        assert "FAKE_SEED=99" in line(app)

    drive(tmp_path, scenario)


def test_options_start_from_the_environment(tmp_path):
    async def scenario(pilot, app, runs):
        assert "FAKE_OPERATOR=1 FAKE_COLOUR=red" in line(app)
        await open_window(pilot, app)
        assert app.screen.query_one("#opt-FAKE_OPERATOR", Checkbox).value is True
        fill(app, operator=False)
        await close(pilot, app)
        await run(pilot, app)
        assert runs.envs == [{"FAKE_OPERATOR": None, "FAKE_COLOUR": "red", "FAKE_SEED": None}]

    drive(tmp_path, scenario, environ={"FAKE_OPERATOR": "1", "FAKE_COLOUR": "rouge"})


def test_bad_options_file_is_shown(tmp_path):
    async def scenario(pilot, app, runs):
        assert "FAKE_SEED.type" in line(app)
        assert app.query_one("#options", Button).disabled
        await run(pilot, app)  # A run is still possible, with the environment unchanged
        assert runs.envs == [{}]

    drive(tmp_path, scenario, text=GOOD.replace("type: int", "type: float"))


def test_window_fits_a_small_terminal(tmp_path):
    """OK and Cancel stay on the screen with the help and errors of every option (80 x 24)."""
    async def scenario(pilot, app, runs):
        await pilot.resize_terminal(80, 24)
        await pilot.press("f2")  # The monitor covers the buttons of the Tests tab at this height
        await ui.settle(pilot, app)
        for button in ("#run", "#stop", "#options", "#refresh"):
            assert app.screen.region.contains_region(app.query_one(button, Button).region)
        await open_window(pilot, app)
        fill(app, other="pink", seed="100")
        await pilot.click("#ok")
        await pilot.pause()
        for button in ("#ok", "#cancel"):
            region = app.screen.query_one(button, Button).region
            assert region.height and app.screen.region.contains_region(region)

    drive(tmp_path, scenario)


# Operator instructions

def test_instruction_on_the_progress_line(tmp_path):
    async def scenario(pilot, app, runs):
        app.tests.post_message(tests_pane.TestsPane.Run("pytest", [], True))
        await ui.wait_for(pilot, lambda: app.active_run is not None, "the run start")
        assert app.query_one("#options", Button).disabled

        def send(event, **fields):
            app.active_run.on_event({"t": time.time(), "event": event, "nodeid": NODEID, **fields})

        send("collected", count=1, nodeids=[NODEID])
        send("test_start")
        send("log", logger="hil.operator", level="INFO", text=INSTRUCTION)
        for _ in range(200):  # TOUCH_READ polls while the operator reads
            send("log", logger="hil.serial", level="INFO", text="TX  CMD id=1 command=TOUCH_READ")
            send("log", logger="hil.serial", level="INFO", text="RX  RESULT id=1 status=OK points=0")
        await ui.wait_for(pilot, lambda: not app.run_events, "the events")
        assert f">>> {INSTRUCTION}" in ui.text(app, "#progress")
        send("report", when="call", outcome="passed", hil_outcome="PASS", duration=1.0, message="", xfail=False)
        send("test_end")
        await ui.wait_for(pilot, lambda: app.tests.done == 1, "the test end")
        assert INSTRUCTION not in ui.text(app, "#progress")  # Nothing left to do for the operator
        app.active_run.finish()
        await ui.wait_for(pilot, lambda: app.active_run is None, "the run end")
        assert "PASS" in ui.text(app, "#progress")
        results = "\n".join(strip.text for strip in app.query_one("#results").lines)
        assert f"operator  {INSTRUCTION}" in results  # Kept for the reader
        assert not app.query_one("#options", Button).disabled

    drive(tmp_path, scenario)
