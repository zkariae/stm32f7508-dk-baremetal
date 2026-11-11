"""Delay between pytest.log and the monitor display of a run (C3).

A real pytest run started from the Tests tab of a headless HilApp: every
hil record of pytest.log must reach the monitor, in order, with the time of
its record, and soon enough. The delay of a line is the time monitor.add()
received it less its time in pytest.log; it covers the event plugin, the
reads of events.jsonl by the runner (POLL) and the refresh of the app
(RUN_REFRESH). Median, 95th percentile and maximum are recorded as test
properties and printed (-s).

  - No board (ui): the fake firmware of test_ui_commands, then fake tests in
    tmp_path, one at a slow rhythm (10 lines/s) and one burst at the rhythm
    of the full suite (300 lines/s). The panel totals must equal junit.xml.
  - Board (board, run by hand): the same check on cases/test_smoke.py, the
    TUI on the real port. Close miniterm and minicom first.

The delay compares two wall clock times (time.time() of the display, the
record time of the pytest subprocess), so a step of the wall clock during
the run makes it wrong: WSL2 resyncs its clock now and then, by up to a
second. Each run compares time.time() with time.monotonic() at its start and
end; when the gap moved by more than CLOCK_STEP the run is made again once,
and when the clock steps again the test is skipped: the measure is lost, the
TUI is not at fault (issue #45).

Not tested here: the paint of the terminal after monitor.add() (one frame of
Textual, measured by hand in E24) and the T1-T8 lines (no pytest.log).

Version: 1.1
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
  1.1  11/11/2026  Run again once when the wall clock steps during the run; skip if it steps twice.
"""

import asyncio
import datetime
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytest.importorskip("textual")

import test_ui_commands as ui  # noqa: E402
from core.runner import Run  # noqa: E402
from core.session import State, load_bench  # noqa: E402
from ui.app import HilApp  # noqa: E402
from ui import tests_pane  # noqa: E402  (the module: pytest would try to collect the class TestsPane)

SIZE = (140, 44)
STEP = 0.05
CONNECT_WAIT = 20.0  # Seconds for a connection (the board: reset, banner, HELLO, CAPS)
FAKE_WAIT = 60.0  # Seconds for the fake run
BOARD_WAIT = 600.0  # Seconds for the smoke run on the board, its flash included
SLOW_LINES, SLOW_RATE = 20, 10.0  # Lines and lines per second of the slow test
BURST_LINES, BURST_RATE = 1500, 300.0  # The rhythm of the full suite
SLOW_LIMIT = 0.5  # Seconds: POLL + RUN_REFRESH = 0.25 s, the rest is margin for a loaded host
BURST_LIMIT = 1.0
BOARD_LIMIT = 1.0
FAKE_TOLERANCE = 1e-3  # Seconds between the time of a line and its pytest.log time (%(created).6f)
BOARD_TOLERANCE = 2e-3  # pytest.log of tests/host/hil keeps milliseconds, truncated
CLOCK_STEP = 0.05  # Seconds the wall clock may move against the monotonic one in a run: a slew stays far below
SMOKE = "cases/test_smoke.py"

INI = """\
[pytest]
log_file_level = DEBUG
log_file_format = %(created).6f|%(name)s|%(levelname)s|%(message)s
"""

FAKE_TESTS = f'''\
import logging
import time

serial = logging.getLogger("hil.serial")


def paced(count, rate, line):
    start = time.monotonic()
    for index in range(count):
        delay = start + index / rate - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        serial.info(line(index))


def test_slow():
    paced({SLOW_LINES}, {SLOW_RATE}, lambda i: f"TX  CMD id={{i + 1}} command=SLOW")


def test_burst():
    paced({BURST_LINES}, {BURST_RATE}, lambda i: f"RX  BURST {{i}}")
'''

_BOARD_LINE = re.compile(r"(\d\d):(\d\d):(\d\d)\.(\d{3}) (hil\.\S+) (\w+) (.*)")


# pytest.log

def fake_record(line: str):
    """Record of a line of the fake pytest.log, or None for a continuation line."""
    parts = line.split("|", 3)
    if len(parts) == 4 and parts[1].startswith("hil.") and re.fullmatch(r"\d+\.\d+", parts[0]):
        return {"t": float(parts[0]), "logger": parts[1], "level": parts[2], "text": parts[3]}
    return None


def board_record(day: datetime.date):
    """Parser of the pytest.log lines of tests/host/hil: local time with milliseconds."""

    def parse(line: str):
        match = _BOARD_LINE.fullmatch(line)
        if match is None:
            return None
        hours, minutes, seconds, millis = (int(value) for value in match.groups()[:4])
        moment = datetime.datetime.combine(day, datetime.time(hours, minutes, seconds, millis * 1000))
        return {"t": moment.timestamp(), "logger": match[5], "level": match[6], "text": match[7]}

    return parse


def read_log(path: Path, parse, start: float) -> list:
    """The hil records of pytest.log; a line that is not a record continues the previous one."""
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = parse(line)
        if record is not None:
            if record["t"] < start - 60.0:  # The run went past midnight
                record["t"] += 86400.0
            records.append(record)
        elif records:
            records[-1]["text"] += "\n" + line
    return records


# Run from the Tests tab

def measure(app: HilApp, selection: list, everything: bool, connect_wait: float, run_wait: float) -> dict:
    """Start the run from the Tests tab; the lines shown while it runs and when, the panel totals."""
    shown = []

    async def main():
        try:
            async with app.run_test(size=SIZE) as pilot:
                await wait_for(pilot, lambda: app.session.state is State.CONNECTED, "the connection", connect_wait)
                add = app.monitor.add

                def timed(line):
                    if app.active_run is not None:  # Lines of the run, not of the session
                        shown.append((time.time(), line))
                    add(line)

                app.monitor.add = timed
                offset = clock_offset()
                start = time.time()
                app.tests.post_message(tests_pane.TestsPane.Run("pytest", selection, everything))
                await wait_for(pilot, lambda: app.active_run is not None, "the run start", connect_wait)
                folder = app.active_run.folder
                pane = app.tests
                await wait_for(pilot, lambda: pane.verdict is not None and not pane.running, "the run end", run_wait)
                step = clock_offset() - offset  # The last line is shown by now
                await wait_for(pilot, lambda: app.session.state is State.CONNECTED, "connected again",
                               connect_wait)
                return {"start": start, "folder": folder, "shown": shown, "verdict": pane.verdict,
                        "totals": pane.totals.counts(), "clock_step": step}
        finally:
            if app.session is not None:
                app.session.shutdown()

    return asyncio.run(main())


def clock_offset() -> float:
    """Wall clock less monotonic clock: constant while the wall clock does not step.

    A thread switch between the two reads would pass for a step on a loaded
    host: time.time() is read between two monotonic reads, and the tightest
    of a few tries is kept.
    """
    tries = []
    for _ in range(5):
        before = time.monotonic()
        wall = time.time()
        after = time.monotonic()
        tries.append((after - before, wall - (before + after) / 2))
    return min(tries)[1]


def measure_steady(make_app, selection: list, everything: bool, connect_wait: float, run_wait: float) -> dict:
    """measure() on a new app from make_app(); once more if the wall clock stepped, skip if it stepped again."""
    steps = []
    for _ in range(2):
        result = measure(make_app(), selection, everything, connect_wait, run_wait)
        steps.append(result["clock_step"])
        if abs(result["clock_step"]) <= CLOCK_STEP:
            result["clock_retries"] = len(steps) - 1
            return result
    pytest.skip(f"the wall clock stepped in both runs ({steps[0]:+.3f} s, {steps[1]:+.3f} s): no delay to measure")


async def wait_for(pilot, condition, what: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause(STEP)
    pytest.fail(f"timed out waiting for {what}")


def delays(result: dict, records: list, tolerance: float) -> list:
    """Delay of each shown line; fails if the lines are not those of pytest.log, in order."""
    expected = [HilApp._run_line(record) for record in records]
    lines = [line for _, line in result["shown"]]
    assert [(line.kind, line.text) for line in lines] == [(line.kind, line.text) for line in expected]
    late = [(line.text, line.created - want.created) for line, want in zip(lines, expected)
            if abs(line.created - want.created) > tolerance]
    assert not late, f"{len(late)} lines shown with another time than pytest.log, first {late[0]}"
    return [at - want.created for (at, _), want in zip(result["shown"], expected)]


def stats(values: list) -> dict:
    ordered = sorted(values)
    return {"lines": len(ordered), "median": ordered[len(ordered) // 2],
            "p95": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], "max": ordered[-1]}


def report(record_property, name: str, values: dict) -> None:
    for key, value in values.items():
        record_property(f"{name}_{key}", round(value, 4) if isinstance(value, float) else value)
    retried = ", run again after a clock step" if values.get("clock_retries") else ""
    print(f"\n{name}: {values['lines']} lines, median {values['median'] * 1000:.0f} ms, "
          f"p95 {values['p95'] * 1000:.0f} ms, max {values['max'] * 1000:.0f} ms{retried}")


def junit_totals(path: Path) -> dict:
    suite = ET.parse(path).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    tests, failed, errors, skipped = (int(suite.get(key, 0)) for key in ("tests", "failures", "errors", "skipped"))
    return {"tests": tests, "passed": tests - failed - errors - skipped, "failed": failed, "errors": errors,
            "skipped": skipped}


# No board

@pytest.fixture(scope="module")
def fake_run(tmp_path_factory):
    """One run of the fake tests from the Tests tab, on the fake firmware (two if the wall clock stepped)."""
    root = tmp_path_factory.mktemp("latency")
    tests = root / "tests"
    tests.mkdir()
    (tests / "pytest.ini").write_text(INI)
    (tests / "test_latency_fake.py").write_text(FAKE_TESTS)

    def make_app():
        rig = ui.Rig()
        return HilApp(rig.bench, ui.CATALOG, rig.session,
                      run_factory=lambda kind, selection, on_event, **kwargs: Run(
                          kind, selection, on_event, results=root / "runs", tests=tests, **kwargs))

    result = measure_steady(make_app, [], True, ui.WAIT, FAKE_WAIT)
    result["records"] = read_log(result["folder"] / "pytest.log", fake_record, result["start"])
    return result


@pytest.mark.ui
def test_lines_and_times_follow_pytest_log(fake_run):
    assert len(fake_run["records"]) == SLOW_LINES + BURST_LINES
    delays(fake_run, fake_run["records"], FAKE_TOLERANCE)


@pytest.mark.ui
@pytest.mark.parametrize("name, prefix, count, limit", [
    ("slow", "CMD ", SLOW_LINES, SLOW_LIMIT),
    ("burst", "BURST ", BURST_LINES, BURST_LIMIT),
], ids=["slow-10-lines-per-s", "burst-300-lines-per-s"])
def test_delay_below_limit(fake_run, record_property, name, prefix, count, limit):
    pairs = zip(fake_run["shown"], delays(fake_run, fake_run["records"], FAKE_TOLERANCE))
    values = [delay for (_, line), delay in pairs if line.text.startswith(prefix)]
    assert len(values) == count
    result = stats(values)
    result["clock_retries"] = fake_run["clock_retries"]
    report(record_property, name, result)
    assert min(values) >= 0.0, "a line shown before pytest.log has it: the times are not those of the records"
    assert result["max"] < limit, f"{name}: a line took {result['max']:.3f} s to show, limit {limit} s"


@pytest.mark.ui
def test_totals_match_junit(fake_run):
    assert fake_run["verdict"] == "PASS"
    assert fake_run["totals"] == junit_totals(fake_run["folder"] / "junit.xml")


# Board

@pytest.mark.board
def test_board_smoke_delay(tmp_path, record_property):
    """Smoke suite on the board, from the TUI: lines of pytest.log, delay and totals."""
    def make_app():
        return HilApp(load_bench(), ui.CATALOG,
                      run_factory=lambda kind, selection, on_event, **kwargs: Run(
                          kind, selection, on_event, results=tmp_path, **kwargs))

    result = measure_steady(make_app, [SMOKE], False, CONNECT_WAIT, BOARD_WAIT)
    day = datetime.date.fromtimestamp(result["start"])
    records = read_log(result["folder"] / "pytest.log", board_record(day), result["start"])
    assert records, "pytest.log has no hil record"
    values = delays(result, records, BOARD_TOLERANCE)
    summary = stats(values)
    summary["clock_retries"] = result["clock_retries"]
    report(record_property, "board", summary)
    assert result["verdict"] == "PASS"
    assert result["totals"] == junit_totals(result["folder"] / "junit.xml")
    assert summary["max"] < BOARD_LIMIT, f"a line took {summary['max']:.3f} s to show, limit {BOARD_LIMIT} s"
