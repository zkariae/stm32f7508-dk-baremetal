"""Timer gap of the interface over a full suite (C6, E30).

A timer of TICK seconds runs on the event loop of a headless HilApp from just
before a pytest run, started from the Tests tab, until the session is
connected again after it. The gap is the longest time between two ticks: a
loop blocked by the display of the run makes the next tick late. C6 asks for
a gap of GAP_LIMIT (500 ms) at most. The maximum, the 99th percentile and the
number of ticks are recorded as test properties and printed (-s).

  - No board (ui): the fake firmware of test_ui_commands and a fake suite in
    tmp_path of the size and rhythm of the full one: FAKE_TESTS tests of
    LINES_PER_TEST hil lines each, LINE_RATE lines per second, one failed
    and one skipped test so the panel shows every outcome.
  - The measure itself (ui): a callback that blocks the loop for BLOCK
    seconds must give a gap above GAP_LIMIT.
  - Board (board, run by hand): the full suite of tests/host/hil (216 tests,
    its flash included) from the TUI on the real port. Close miniterm,
    minicom and any other TUI first.

Not tested here: the T1-T8 runs (uart_rx_check.py, no hil log stream at the
full suite rhythm) and the paint of a real terminal (headless here; seen by
eye in the VS Code terminal).

Version: 1.0
Date: 16/11/2026
Author: Z. BEN-AKKA
History:
  1.0  16/11/2026  Initial version.
"""

import asyncio
import time

import pytest

pytest.importorskip("textual")

import test_display_latency as latency  # noqa: E402
import test_ui_commands as ui  # noqa: E402
from core.runner import Run  # noqa: E402
from core.session import State, load_bench  # noqa: E402
from ui import tests_pane  # noqa: E402  (the module: pytest would try to collect the class TestsPane)
from ui.app import HilApp  # noqa: E402

TICK = 0.05  # Seconds between two ticks of the measuring timer
GAP_LIMIT = 0.5  # C6: the longest gap between two ticks over a full suite
BLOCK = 0.7  # Seconds the loop is blocked on purpose in the check of the measure
FAKE_TESTS, LINES_PER_TEST, LINE_RATE = 216, 10, 300.0  # The size and the rhythm of the full suite
FAKE_FAILED, FAKE_SKIPPED = 100, 150  # Indexes of the failed and the skipped fake test
CONNECT_WAIT = 20.0  # Seconds for a connection (the board: reset, banner, HELLO, CAPS)
FAKE_WAIT = 120.0  # Seconds for the fake suite
BOARD_WAIT = 1800.0  # Seconds for the full suite on the board, its flash included

FAKE_SUITE = f'''\
import logging
import time

import pytest

serial = logging.getLogger("hil.serial")
START = time.monotonic()  # The lines keep LINE_RATE over the whole suite, not test by test


@pytest.mark.parametrize("index", range({FAKE_TESTS}))
def test_case(index):
    if index == {FAKE_SKIPPED}:
        pytest.skip("skipped on purpose")
    for line in range({LINES_PER_TEST}):
        number = index * {LINES_PER_TEST} + line
        delay = START + number / {LINE_RATE} - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        serial.info(f"RX  RESULT id={{number + 1}} status=OK test={{index}}")
    assert index != {FAKE_FAILED}, "failed on purpose"
'''


# Measure

def gaps(ticks: list) -> list:
    return [later - earlier for earlier, later in zip(ticks, ticks[1:])]


def stats(values: list) -> dict:
    ordered = sorted(values)
    return {"ticks": len(ordered) + 1, "p99": ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))],
            "max": ordered[-1]}


def report(record_property, name: str, values: dict) -> None:
    for key, value in values.items():
        record_property(f"{name}_{key}", round(value, 4) if isinstance(value, float) else value)
    print(f"\n{name}: {values['ticks']} ticks of {TICK * 1000:.0f} ms, p99 {values['p99'] * 1000:.0f} ms, "
          f"max {values['max'] * 1000:.0f} ms (limit {GAP_LIMIT * 1000:.0f} ms)")


def measure(app: HilApp, selection: list, everything: bool, connect_wait: float, run_wait: float) -> dict:
    """Tick from just before the run until connected again after it; the ticks and the verdict."""
    ticks = []

    async def main():
        try:
            async with app.run_test(size=latency.SIZE) as pilot:
                await latency.wait_for(pilot, lambda: app.session.state is State.CONNECTED, "the connection",
                                       connect_wait)
                timer = app.set_interval(TICK, lambda: ticks.append(time.monotonic()))
                app.tests.post_message(tests_pane.TestsPane.Run("pytest", selection, everything))
                await latency.wait_for(pilot, lambda: app.active_run is not None, "the run start", connect_wait)
                pane = app.tests
                await latency.wait_for(pilot, lambda: pane.verdict is not None and not pane.running, "the run end",
                                       run_wait)
                await latency.wait_for(pilot, lambda: app.session.state is State.CONNECTED, "connected again",
                                       connect_wait)
                timer.stop()
                return {"ticks": ticks, "verdict": pane.verdict, "totals": pane.totals.counts()}
        finally:
            if app.session is not None:
                app.session.shutdown()

    return asyncio.run(main())


# No board

@pytest.mark.ui
def test_gap_over_a_fake_full_suite(tmp_path, record_property):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pytest.ini").write_text(latency.INI)
    (tests / "test_full_suite_fake.py").write_text(FAKE_SUITE)
    rig = ui.Rig()
    app = HilApp(rig.bench, ui.CATALOG, rig.session,
                 run_factory=lambda kind, selection, on_event, **kwargs: Run(
                     kind, selection, on_event, results=tmp_path / "runs", tests=tests, **kwargs))
    result = measure(app, [], True, ui.WAIT, FAKE_WAIT)
    totals = result["totals"]
    assert (totals["tests"], totals["failed"], totals["skipped"]) == (FAKE_TESTS, 1, 1)  # The whole suite ran
    summary = stats(gaps(result["ticks"]))
    report(record_property, "fake", summary)
    assert summary["max"] <= GAP_LIMIT, f"the interface stopped {summary['max']:.3f} s, limit {GAP_LIMIT} s"


@pytest.mark.ui
def test_measure_sees_a_block():
    """A callback that blocks the event loop shows as a gap above the limit."""
    rig = ui.Rig()
    ticks = []

    async def scenario(pilot, app):
        blocked = []

        def block():
            blocked.append(True)
            time.sleep(BLOCK)  # On the event loop, as a slow display would be

        timer = app.set_interval(TICK, lambda: ticks.append(time.monotonic()))
        await pilot.pause(0.3)
        app.call_later(block)
        await latency.wait_for(pilot, lambda: blocked, "the blocked loop", ui.WAIT)
        await pilot.pause(0.3)
        timer.stop()

    ui.drive(rig, scenario)
    assert max(gaps(ticks)) > GAP_LIMIT


# Board

@pytest.mark.board
def test_board_gap_over_the_full_suite(tmp_path, record_property):
    app = HilApp(load_bench(), ui.CATALOG,
                 run_factory=lambda kind, selection, on_event, **kwargs: Run(
                     kind, selection, on_event, results=tmp_path, **kwargs))
    result = measure(app, [], True, CONNECT_WAIT, BOARD_WAIT)
    summary = stats(gaps(result["ticks"]))
    report(record_property, "board", summary)
    assert result["verdict"] == "PASS"
    assert summary["max"] <= GAP_LIMIT, f"the interface stopped {summary['max']:.3f} s, limit {GAP_LIMIT} s"
