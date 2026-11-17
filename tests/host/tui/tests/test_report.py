"""Host tests of the run report, core/report.py (C4).

No board. Each test writes its runs in tmp_path: real runs of fake pytest
tests through core/runner.py, a pytest killed with SIGKILL in the middle of
a test, and hand-made run folders for the cases a run cannot be asked for.

  - Real run: the totals equal junit.xml and run.json, the verdict FAIL, one
    line per test with its outcome, the last request of a failure with its
    records, the teardown error named, the banner of the session line.
  - Stop: INTERRUPTED, only the tests that ran, the note says so.
  - Kill: run.json without verdict, the report is rebuilt from events.jsonl,
    INTERRUPTED, the test in progress not finished and not counted; a cut
    last line, a missing or unreadable run.json.
  - The timeouts of section 8.1, the escaping of the Markdown and the HTML
    page (well formed, no script, no external resource), export() and the
    command line.

Not tested here: the Export button of the TUI (E28) and the look of the
page in a browser (checked by hand in E26).

Version: 1.1
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
  1.1  11/11/2026  Fix the expected totals for the junit.xml rule of pytest 9.1 and later.
"""

import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

from core import report
from core.runner import BENCH, PLUGINS_DIR, Run, junit_counts_teardown_once

PY = sys.executable
REPORT_PY = Path(report.__file__)
RUN_WAIT = 30.0  # Seconds a test waits for a run to end
EVENT_WAIT = 15.0  # Seconds a test waits for a line of events.jsonl
# junit.xml of pytest 9.1 and later counts a failed call then a failed teardown twice (hil_tui.md)
CALL_AND_TEARDOWN = int(junit_counts_teardown_once())
SESSION = "READY name=hil-bench fw=1.3.0 proto=1.3 build=abc1234 reset=PIN reset_flags=0x04000000"

INI = """\
[pytest]
log_file_level = DEBUG
"""

CASES = f'''\
import logging

import pytest

serial = logging.getLogger("hil.serial")
board = logging.getLogger("hil.board")


@pytest.fixture
def bad_teardown():
    yield
    raise OSError("port lost in teardown")


def test_pass():
    serial.info("RX  {SESSION}")
    board.info("session started: {SESSION}")
    serial.info("TX  CMD id=1 command=HELLO")
    serial.info("RX  RESULT id=1 status=OK")
    serial.info("RX  END id=1")


def test_led_reads_back(bad_teardown):
    serial.info("TX  CMD id=2 command=LED_SET state=on")
    serial.info("RX  RESULT id=2 status=OK")
    serial.info("RX  END id=2")
    serial.info("TX  CMD id=3 command=LED_GET")
    serial.info("RX  RESULT id=3 status=OK state=off")
    serial.info("RX  END id=3")
    assert False, "LED | should be <on> & lit"


def test_skip():
    pytest.skip("no LCD on this board")


def test_fake_firmware_banner():
    serial.info("RX  READY name=hil-bench fw=1.0.0 proto=1.0 build=abc1234 reset=PIN reset_flags=0x04000000")
'''

LONG = '''\
import logging
import time

log = logging.getLogger("hil.serial")


def test_first():
    log.info("TX  CMD id=1 command=HELLO")


def test_long():
    for _ in range(300):
        log.info("RX  tick")
        time.sleep(0.1)


def test_never_reached():
    pass
'''

LED = "cases/test_led.py::test_on"
STEP = "scenario:lcd_colors.yaml::step5"


# Helpers

def write(folder: Path, files: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def wait_until(condition, timeout: float = EVENT_WAIT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def junit_counts(path: Path) -> dict:
    """tests, failed, errors and skipped of junit.xml (it has no passed count)."""
    root = ET.parse(path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    return {"tests": int(suite.get("tests")), "failed": int(suite.get("failures")),
            "errors": int(suite.get("errors")), "skipped": int(suite.get("skipped"))}


def events_file(folder: Path, events: list, meta: dict | None = None) -> Path:
    """A hand-made run folder: events.jsonl and, if given, run.json."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    if meta is not None:
        (folder / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def phase(nodeid: str, when: str, outcome: str, hil_outcome: str, message: str = "", duration: float = 0.1) -> dict:
    return {"t": 1.0, "event": "report", "nodeid": nodeid, "when": when, "outcome": outcome,
            "hil_outcome": hil_outcome, "duration": duration, "message": message, "xfail": False}


def log(nodeid: str | None, text: str, logger: str = "hil.serial") -> dict:
    return {"t": 1.0, "event": "log", "nodeid": nodeid, "logger": logger, "level": "INFO", "text": text}


class Page(HTMLParser):
    """Tags of the page: every one closed in order, none that loads or runs something."""

    VOID = {"meta", "br"}
    FORBIDDEN = {"script", "link", "img", "iframe", "object", "embed"}

    def __init__(self, text: str):
        super().__init__()
        self.open, self.errors = [], []
        self.feed(text)
        self.close()
        self.errors += [f"<{tag}> not closed" for tag in self.open]

    def handle_starttag(self, tag, attrs):
        if tag in self.FORBIDDEN:
            self.errors.append(f"<{tag}>")
        if any(name.startswith("on") or (value or "").startswith(("http:", "https:")) for name, value in attrs):
            self.errors.append(f"<{tag}> {attrs}")
        if tag not in self.VOID:
            self.open.append(tag)

    def handle_endtag(self, tag):
        if self.open and self.open[-1] == tag:
            self.open.pop()
        else:
            self.errors.append(f"</{tag}> out of order")


# Real runs

@pytest.fixture(scope="module")
def failed_run(tmp_path_factory):
    """One run of CASES through the runner: (run, report)."""
    root = tmp_path_factory.mktemp("report")
    run = Run("pytest", on_event=lambda event: None, everything=True, results=root / "runs",
              tests=write(root / "cases", {"pytest.ini": INI, "test_cases.py": CASES}))
    run.start()
    assert run.wait(RUN_WAIT), "the run did not end"
    return run, report.build(run.folder)


def test_real_run_totals_equal_junit_and_run_json(failed_run):
    run, rep = failed_run
    meta = json.loads((run.folder / "run.json").read_text(encoding="utf-8"))
    assert rep.totals == meta["totals"] == run.totals.counts()
    assert {key: rep.totals[key] for key in ("tests", "failed", "errors", "skipped")} == \
        junit_counts(run.folder / "junit.xml")
    assert rep.totals == {"tests": 4 + CALL_AND_TEARDOWN, "passed": 2, "failed": 1, "errors": 1, "skipped": 1}
    assert (rep.verdict, rep.exitstatus, rep.rebuilt, rep.bad_lines) == ("FAIL", 1, False, [])


def test_real_run_one_line_per_test(failed_run):
    _, rep = failed_run
    outcomes = {test.nodeid.split("::")[1]: test.outcome for test in rep.tests}
    assert outcomes == {"test_pass": "PASS", "test_led_reads_back": "FUNCTIONAL_ERROR", "test_skip": "SKIPPED",
                        "test_fake_firmware_banner": "PASS"}
    assert all(test.finished and test.duration >= 0.0 for test in rep.tests)
    assert "no LCD on this board" in next(test.message for test in rep.tests if test.outcome == "SKIPPED")


def test_real_run_failure_has_its_last_request(failed_run):
    _, rep = failed_run
    [failure] = rep.failures
    assert failure.nodeid.endswith("::test_led_reads_back") and failure.outcome == "FUNCTIONAL_ERROR"
    assert failure.request == "CMD id=3 command=LED_GET"
    assert failure.records == ["RESULT id=3 status=OK state=off", "END id=3"]
    assert failure.message.startswith("AssertionError: LED | should be <on> & lit")
    assert failure.message.endswith("; teardown: BENCH_ERROR OSError: port lost in teardown")


def test_real_run_banner_of_the_session_line(failed_run):
    _, rep = failed_run
    assert rep.banner == SESSION  # Not the fake firmware banner received later
    assert rep.overrides == []  # bench.yaml of the repository: the values of section 8.1
    assert rep.commit and rep.bench == str(BENCH)


def test_stop_gives_an_interrupted_report(tmp_path):
    seen = []
    run = Run("pytest", on_event=seen.append, everything=True, results=tmp_path / "runs",
              tests=write(tmp_path / "long", {"pytest.ini": INI, "test_long.py": LONG}))
    run.start()
    assert wait_until(lambda: any(event.get("text") == "RX  tick" for event in seen))
    run.stop()
    assert run.wait(RUN_WAIT), "the run did not end"
    rep = report.build(run.folder)
    assert rep.verdict == "INTERRUPTED" and not rep.rebuilt
    assert rep.totals == run.totals.counts()
    assert [test.nodeid.split("::")[1] for test in rep.tests if test.finished][0] == "test_first"
    assert not any(test.nodeid.endswith("::test_never_reached") for test in rep.tests)
    assert rep.totals["passed"] >= 1 and rep.totals["tests"] <= 2
    text = report.to_markdown(rep)
    assert "| Verdict | INTERRUPTED |" in text and "only the tests that ran are counted" in text


def test_kill_rebuilds_from_events(tmp_path):
    """A pytest killed with SIGKILL in the middle of a test, run.json left as the runner wrote it at start."""
    tests = write(tmp_path / "long", {"pytest.ini": INI, "test_long.py": LONG})
    folder = tmp_path / "run"
    folder.mkdir()
    events = folder / "events.jsonl"
    (folder / "run.json").write_text(json.dumps({"kind": "pytest", "selection": [], "everything": True,
                                                 "commit": "abc1234", "started": time.time()}), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(PLUGINS_DIR), os.environ.get("PYTHONPATH")])))
    process = subprocess.Popen([PY, "-m", "pytest", str(tests), "-q", "-p", "hil_events", "--hil-events",
                                str(events), "--junitxml", str(folder / "junit.xml")],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_until(lambda: events.is_file() and "RX  tick" in events.read_text(encoding="utf-8"))
    finally:
        process.send_signal(signal.SIGKILL)
        process.wait(RUN_WAIT)
    assert not (folder / "junit.xml").exists()  # pytest never reached its end
    rep = report.build(folder)
    unfinished = [test.nodeid for test in rep.tests if not test.finished]
    assert (rep.verdict, rep.rebuilt, rep.exitstatus) == ("INTERRUPTED", True, None)
    assert rep.totals == {"tests": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0}
    assert len(unfinished) == 1 and unfinished[0].endswith("::test_long")
    text = report.to_markdown(rep)
    assert "Rebuilt from events.jsonl" in text and "Not finished, not counted" in text

    # The kill cut the last line while it was written
    count = len(events.read_text(encoding="utf-8").splitlines())
    with open(events, "a", encoding="utf-8") as stream:
        stream.write('{"t": 1.0, "event": "rep')
    rep = report.build(folder)
    assert rep.bad_lines == [count + 1] and rep.verdict == "INTERRUPTED"
    assert f"lines skipped (not JSON): {count + 1}" in report.to_markdown(rep)


@pytest.mark.parametrize("meta", [None, "{", "[]"], ids=["missing", "cut", "not-an-object"])
def test_unreadable_run_json(tmp_path, meta):
    folder = events_file(tmp_path / "run", [{"t": 10.0, "event": "session_start"}, phase("t::a", "call", "passed",
                                                                                         "PASS")])
    if meta is not None:
        (folder / "run.json").write_text(meta, encoding="utf-8")
    rep = report.build(folder)
    assert (rep.verdict, rep.rebuilt, rep.kind, rep.started) == ("INTERRUPTED", True, "pytest", 10.0)
    assert rep.totals["passed"] == 1


def test_not_a_run_folder(tmp_path):
    with pytest.raises(report.ReportError, match="no events.jsonl"):
        report.build(tmp_path)


# Content

def hand_made(tmp_path: Path, bench: str | None = None) -> Path:
    """A failed pytest call then teardown, a skip, a scenario step and a test that never ended."""
    events = [
        {"t": 1.0, "event": "session_start"},
        {"t": 1.1, "event": "test_start", "nodeid": LED},
        log(LED, "TX  CMD id=4 command=LED_GET"),
        log(LED, "RX  RESULT id=4 status=OK state=off"),
        log(LED, "RX  END id=4"),
        phase(LED, "setup", "passed", "PASS"),
        phase(LED, "call", "failed", "FUNCTIONAL_ERROR", "AssertionError: LED | should be <on>"),
        phase(LED, "teardown", "failed", "BENCH_ERROR", "OSError: port lost"),
        phase("cases/test_lcd.py::test_x", "setup", "skipped", "SKIPPED", "Skipped: no LCD"),
        {"t": 2.0, "event": "test_start", "nodeid": STEP, "label": "PROMPT Is the whole screen red?"},
        log(STEP, "PROMPT Is the whole screen red? -> no", logger="tui.scenario"),
        phase(STEP, "call", "failed", "FUNCTIONAL_ERROR", "operator answered no: Is the whole screen red?"),
        {"t": 2.5, "event": "test_start", "nodeid": "cases/test_qspi.py::test_erase"},
    ]
    folder = events_file(tmp_path / "hand", events, {"kind": "pytest", "selection": [], "verdict": "FAIL",
                                                    "exitstatus": 1, "started": 1.0, "ended": 3.0})
    if bench is not None:
        (folder / "bench.yaml").write_text(bench, encoding="utf-8")
    return folder


def test_hand_made_failures(tmp_path):
    rep = report.build(hand_made(tmp_path))
    assert rep.totals == {"tests": 3 + CALL_AND_TEARDOWN, "passed": 0, "failed": 2, "errors": 1, "skipped": 1}
    led, step = rep.failures
    assert (led.request, led.records) == ("CMD id=4 command=LED_GET", ["RESULT id=4 status=OK state=off", "END id=4"])
    assert led.message == "AssertionError: LED | should be <on>; teardown: BENCH_ERROR OSError: port lost"
    assert (step.request, step.records) == ("PROMPT Is the whole screen red?", [])  # No TX: the step label
    by_id = {test.nodeid: test for test in rep.tests}
    assert by_id[LED].duration == pytest.approx(0.3)
    assert by_id["cases/test_qspi.py::test_erase"].outcome == "NOT_FINISHED"
    assert rep.banner == ""  # No session line
    assert "| Banner | not recorded |" in report.to_markdown(rep)


@pytest.mark.parametrize("change, expected", [
    ("startup: 5.0", []),
    ("startup: 1.0", [("startup", 1.0, 5.0)]),
    ("response: 2.0", []),
    ("response: 4.5", [("response", 4.5, 2.0)]),
    ("startup: fast", [("startup", "fast", 5.0)]),
], ids=["startup-protocol", "startup-changed", "response-protocol", "response-changed", "unreadable"])
def test_timeouts_against_section_8_1(tmp_path, change, expected):
    name = change.split(":")[0]
    bench = BENCH.read_text(encoding="utf-8")
    line = next(line for line in bench.splitlines() if line.strip().startswith(f"{name}:"))
    bench = bench.replace(line, f"  {change}", 1)
    rep = report.build(hand_made(tmp_path, bench))
    assert rep.overrides == expected
    text = report.to_markdown(rep)
    assert ("None: startup 5 s and response 2 s" in text) == (not expected)


def test_markdown_escapes_the_table(tmp_path):
    text = report.to_markdown(report.build(hand_made(tmp_path)))
    row = next(line for line in text.splitlines() if line.startswith("| 1 |"))
    assert "LED \\| should be <on>" in row and row.count(" | ") == 4  # Five cells, the pipe of the message escaped


def test_html_is_escaped_and_self_contained(tmp_path):
    page = report.to_html(report.build(hand_made(tmp_path)))
    assert Page(page).errors == []
    assert "&lt;on&gt;" in page and "<on>" not in page
    assert page.startswith("<!doctype html>") and '<meta charset="utf-8">' in page


def test_export_writes_both_files(tmp_path):
    folder = hand_made(tmp_path)
    markdown, page = report.export(folder)
    assert (markdown, page) == (folder / "report.md", folder / "report.html")
    assert markdown.read_text(encoding="utf-8").startswith("# Test report: pytest: whole suite")
    assert Page(page.read_text(encoding="utf-8")).errors == []


def test_command_line(tmp_path):
    folder = hand_made(tmp_path)
    done = subprocess.run([PY, str(REPORT_PY), str(folder)], cwd=tmp_path, capture_output=True, text=True,
                          timeout=RUN_WAIT)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == [str(folder / "report.md"), str(folder / "report.html")]
    done = subprocess.run([PY, str(REPORT_PY), str(tmp_path / "nowhere")], cwd=tmp_path, capture_output=True,
                          text=True, timeout=RUN_WAIT)
    assert done.returncode == 2 and done.stdout == ""
    assert done.stderr.startswith("report: ") and len(done.stderr.splitlines()) == 1
