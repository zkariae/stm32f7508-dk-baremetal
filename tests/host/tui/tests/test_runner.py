"""Host tests of the event plugin, the scenarios, the discovery and the runner (C2, C3, C4, C5).

No board. Each test writes its own fake files in tmp_path: pytest test files
with a pytest.ini, a fake make and a fake uart_rx_check.py, scenario YAML
files. The runs go to tmp_path, never to work/hil-results.

  - plugins/hil_events.py: a real pytest run of fake tests covering every
    outcome; hil_outcome of each phase, the log lines against pytest.log,
    nothing written without --hil-events.
  - core/runner.py: Totals on hand-made reports by the junit.xml rule
    before and from pytest 9.1, then real runs whose totals must equal
    junit.xml of the installed pytest and the pytest summary (C3), each
    teardown error case in its own run; Stop during a test,
    during a fake flash (deferred) and twice during it (forced), with the
    process group checked gone (C2); T1-T8 with fake scripts; scenario runs.
  - core/scenario.py: the step outcomes, the exit codes and the refused files.
  - core/suites.py: the UART RX plan, the collection of tests/host/hil (no
    total written here, C5) and a broken collection kept in its family.

Not tested here: the board, the real flash, make and the real
uart_rx_check.py (checked by hand on the board in E20), and the display
(tests_pane.py).

Version: 1.1
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
  1.1  11/11/2026  Test Totals by the junit.xml rule of pytest before and from 9.1, and each teardown error case.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from adapters.outcomes import UnexpectedReset
from adapters.serial_adapter import Response
from core.catalog import load as load_catalog
from core.runner import PLUGINS_DIR, REPO, Run, Totals, junit_counts_teardown_once
from core.scenario import ScenarioError, load, load_all, run as play_scenario
from core.suites import SuitesError, discover_all, discover_pytest, discover_rx, discover_scenarios, rx_selection

PY = sys.executable
RUN_WAIT = 30.0  # Seconds a test waits for a run to end
EVENT_WAIT = 15.0  # Seconds a test waits for a state of a running run
FLASH = 1.5  # Seconds of a fake flash
REPORT_KEYS = {"t", "event", "nodeid", "when", "outcome", "hil_outcome", "duration", "message", "xfail"}
HIL_LOG = REPO / "work" / "hil-results" / "pytest.log"

CATALOG = load_catalog()

# Fake files

INI = """\
[pytest]
log_file_level = DEBUG
log_file_format = %(name)s|%(levelname)s|%(message)s
"""

CASES = '''\
import logging

import pytest

log = logging.getLogger("hil.serial")


class HilOutcome(Exception):
    outcome = "PROTOCOL_FAILURE"


class UnexpectedReset(HilOutcome):
    outcome = "UNEXPECTED_RESET"


@pytest.fixture
def broken():
    raise RuntimeError("bench down")


@pytest.fixture
def bad_teardown():
    yield
    raise OSError("port lost in teardown")


def test_pass():
    log.info("TX  CMD id=1 command=HELLO")
    log.debug("RX  RESULT id=1 status=OK")


def test_hil_outcome():
    raise UnexpectedReset("READY while idle")


def test_assert():
    assert 1 == 2, "LED should be on"


def test_other():
    {}["missing"]


def test_skip():
    pytest.skip("no LCD on this board")


def test_setup_error(broken):
    pass


def test_teardown_error(bad_teardown):
    pass


def test_call_and_teardown(bad_teardown):
    assert False


@pytest.mark.xfail(reason="known")
def test_xfail():
    assert False


@pytest.mark.xfail(strict=True)
def test_xpass_strict():
    pass
'''

TEARDOWNS = '''\
import pytest


@pytest.fixture
def bad_teardown():
    yield
    raise OSError("port lost in teardown")


@pytest.fixture
def bad_setup():
    raise OSError("bench down")


def test_call_failed(bad_teardown):
    assert False


def test_setup_failed(bad_teardown, bad_setup):
    pass


def test_skipped(bad_teardown):
    pytest.skip("no LCD")


def test_passed(bad_teardown):
    pass
'''

PASSING = '''\
import logging

log = logging.getLogger("hil.serial")


def test_one():
    log.info("TX  CMD id=1 command=HELLO")


def test_two():
    log.info("RX  RESULT id=1 status=OK")
'''

LONG = '''\
import logging
import time

log = logging.getLogger("hil.serial")


def test_long():
    for _ in range(300):
        log.info("RX  tick")
        time.sleep(0.1)
'''

FLASHING = f'''\
import logging
import time

log = logging.getLogger("hil.programmer")


def test_flash():
    log.info("RUN make hil-bench-flash")
    time.sleep({FLASH})
    log.info("RUN make reset")
    time.sleep(30)
'''

FAKE_MAKE = f'''\
"""Fake make: three lines, slow for a -flash target; exit 2 for a target named fail."""
import sys
import time

target = sys.argv[-1]
for n in range(3):
    print(f"{{target}} line {{n}}")
    time.sleep({FLASH / 3} if target.endswith("-flash") else 0.02)
sys.exit(2 if target == "fail" else 0)
'''

FAKE_RX = '''\
"""Prints like uart_rx_check.py --trace for T1 and T3; argv: pass, fail or serial."""
import sys

mode = sys.argv[1]
print("TX  ' !\\"#$%&...'")
print("RX  ' !\\"#$%&...'")
print("PASS T1: 100 lines echoed")
print("BAUD 9600")
print("TX  00")
print("BAUD 115200")
print("RX  '[FE]\\\\r\\\\n'")
if mode == "fail":
    print("FAIL T3: no marker")
    print("FAILED: T3 (1/2 passed)")
    sys.exit(1)
if mode == "serial":
    print("Serial error: device reports readiness to read but returned no data")
    sys.exit(2)
print("PASS T3: [FE] reported")
print("CHECK T7: LD1 keeps blinking at 2 Hz (visual)")
print("ALL PASSED: 2/2")
'''

LCD = """\
name: LCD colour check
steps:
  - {command: LCD_INIT}
  - {command: LCD_FILL, args: {color: "0xF800"}}
  - {command: LCD_PIXEL, args: {x: 0, y: 0}, expect: {color: "0xf800"}}
  - {prompt: "Is the screen red?"}
"""

BAD = {
    "unknown_command": ("name: x\nsteps:\n  - {command: NOPE}\n", "step 1: NOPE is not in the catalogue"),
    "out_of_range": ("name: x\nsteps:\n  - {command: LCD_PIXEL, args: {x: 999, y: 0}}\n", "step 1: LCD_PIXEL x:"),
    "both": ('name: x\nsteps:\n  - {command: LCD_INIT, prompt: "hi"}\n', "step 1: needs either command or prompt"),
    "unknown_key": ("name: x\nsteps:\n  - {command: LCD_INIT, wait: 1}\n", "step 1: unknown keys ['wait']"),
    "unquoted_hex": ("name: x\nsteps:\n  - {command: LCD_FILL, args: {color: 0xF800}}\n", "(quote hex values)"),
    "no_steps": ("name: x\nsteps: []\n", "steps must be a non-empty list"),
    "no_name": ('steps:\n  - {prompt: "hi"}\n', "name must be a non-empty string"),
    "prompt_with_expect": ('name: x\nsteps:\n  - {prompt: "hi", expect: {a: 1}}\n',
                           "step 1: a prompt step has no args or expect"),
}


# Helpers

def write(folder: Path, files: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def suite_of(tmp_path: Path, name: str, test_file: str) -> Path:
    """A folder of fake pytest tests with its pytest.ini."""
    return write(tmp_path / name, {"pytest.ini": INI, f"test_{name}.py": test_file})


def wait_until(condition, timeout: float = EVENT_WAIT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def make_run(tmp_path: Path, kind: str, **kwargs) -> Run:
    seen = []
    run = Run(kind, on_event=seen.append, results=tmp_path / "runs", **kwargs)
    run.seen = seen
    return run


def finish(run: Run) -> Run:
    assert run.wait(RUN_WAIT), "the run did not end"
    return run


def read_events(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def junit_counts(folder: Path) -> dict:
    """junit.xml counts, with passed from the pytest summary line (junit.xml has none)."""
    root = ET.parse(folder / "junit.xml").getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    summary = (folder / "pytest.out").read_text(encoding="utf-8").strip().splitlines()[-1]
    passed = re.search(r"(\d+) passed", summary)
    return {"tests": int(suite.get("tests")), "passed": int(passed.group(1)) if passed else 0,
            "failed": int(suite.get("failures")), "errors": int(suite.get("errors")),
            "skipped": int(suite.get("skipped"))}


def group_gone(run: Run) -> bool:
    """True when no process is left in the group of the run."""
    try:
        os.killpg(run._process.pid, 0)
    except ProcessLookupError:
        return True
    return False


def notes(run: Run) -> list:
    return [event["text"] for event in run.seen if event.get("logger") == "tui.runner"]


def plugin_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(PLUGINS_DIR), env.get("PYTHONPATH")]))
    return env


def report(nodeid: str, when: str, outcome: str) -> dict:
    return {"event": "report", "nodeid": nodeid, "when": when, "outcome": outcome}


# plugins/hil_events.py

@pytest.fixture(scope="module")
def plugin_run(tmp_path_factory):
    """One pytest run of CASES with the plugin: (events, pytest.log lines, junit.xml path)."""
    folder = suite_of(tmp_path_factory.mktemp("plugin"), "cases", CASES)
    events, log, junit = folder / "events.jsonl", folder / "pytest.log", folder / "junit.xml"
    done = subprocess.run([PY, "-m", "pytest", str(folder), "-q", "-p", "hil_events", "--hil-events", str(events),
                           "--log-file", str(log), "--junitxml", str(junit)],
                          cwd=folder, env=plugin_env(), capture_output=True, text=True, timeout=RUN_WAIT)
    assert done.returncode == 1, done.stdout
    return read_events(events), log.read_text(encoding="utf-8").splitlines(), junit


def test_plugin_classifies_each_phase(plugin_run):
    events, _, _ = plugin_run
    outcomes = {(event["nodeid"].split("::")[1], event["when"]): (event["hil_outcome"], event["xfail"])
                for event in events if event["event"] == "report"}
    assert outcomes[("test_pass", "call")] == ("PASS", False)
    assert outcomes[("test_hil_outcome", "call")] == ("UNEXPECTED_RESET", False)
    assert outcomes[("test_assert", "call")] == ("FUNCTIONAL_ERROR", False)
    assert outcomes[("test_other", "call")] == ("BENCH_ERROR", False)
    assert outcomes[("test_skip", "call")] == ("SKIPPED", False)
    assert outcomes[("test_setup_error", "setup")] == ("BENCH_ERROR", False)
    assert outcomes[("test_teardown_error", "teardown")] == ("BENCH_ERROR", False)
    assert outcomes[("test_call_and_teardown", "call")] == ("FUNCTIONAL_ERROR", False)
    assert outcomes[("test_call_and_teardown", "teardown")] == ("BENCH_ERROR", False)
    assert outcomes[("test_xfail", "call")] == ("SKIPPED", True)
    assert outcomes[("test_xpass_strict", "call")] == ("BENCH_ERROR", False)


def test_plugin_stream_format(plugin_run):
    events, _, _ = plugin_run
    kinds = [event["event"] for event in events]
    assert kinds[:2] == ["session_start", "collected"]
    assert events[1]["count"] == 10
    assert events[-1] == {**events[-1], "event": "session_end", "exitstatus": 1}
    assert kinds.count("test_start") == kinds.count("test_end") == 10
    assert all(set(event) == REPORT_KEYS for event in events if event["event"] == "report")
    messages = {event["nodeid"].split("::")[1]: event["message"] for event in events
                if event["event"] == "report" and event["outcome"] != "passed"}
    assert messages["test_skip"] == "Skipped: no LCD on this board"  # The reason as pytest gives it
    assert "LED should be on" in messages["test_assert"]


def test_plugin_log_lines_match_pytest_log(plugin_run):
    events, log, _ = plugin_run
    streamed = [(event["logger"], event["level"], event["text"]) for event in events if event["event"] == "log"]
    logged = [tuple(line.split("|", 2)) for line in log if line.startswith("hil.")]
    assert streamed == logged == [("hil.serial", "INFO", "TX  CMD id=1 command=HELLO"),
                                  ("hil.serial", "DEBUG", "RX  RESULT id=1 status=OK")]
    assert all(event["nodeid"].endswith("::test_pass") for event in events if event["event"] == "log")


def test_plugin_counts_match_junit(plugin_run):
    events, _, junit = plugin_run
    totals = Totals()
    for event in events:
        totals.add(event)
    root = ET.parse(junit).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    assert {key: getattr(totals, name) for key, name in (("tests", "tests"), ("failures", "failed"),
                                                         ("errors", "errors"), ("skipped", "skipped"))} \
        == {key: int(suite.get(key)) for key in ("tests", "failures", "errors", "skipped")}


def test_plugin_writes_nothing_without_option(tmp_path):
    folder = suite_of(tmp_path, "passing", PASSING)
    done = subprocess.run([PY, "-m", "pytest", str(folder), "-q", "-p", "hil_events", "-p", "no:cacheprovider"],
                          cwd=folder, env=plugin_env(), capture_output=True, text=True, timeout=RUN_WAIT)
    assert done.returncode == 0, done.stdout
    assert list(tmp_path.rglob("*.jsonl")) == []


# Totals

@pytest.mark.parametrize("teardown_once", [False, True], ids=["pytest-before-9.1", "pytest-9.1-and-later"])
@pytest.mark.parametrize("reports, expected, tests_from_9_1", [
    ([("a", "setup", "passed"), ("a", "call", "passed"), ("a", "teardown", "passed")],
     {"tests": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0}, 1),
    ([("a", "setup", "passed"), ("a", "call", "failed"), ("a", "teardown", "passed")],
     {"tests": 1, "passed": 0, "failed": 1, "errors": 0, "skipped": 0}, 1),
    ([("a", "setup", "failed"), ("a", "teardown", "passed")],
     {"tests": 1, "passed": 0, "failed": 0, "errors": 1, "skipped": 0}, 1),
    ([("a", "setup", "passed"), ("a", "call", "passed"), ("a", "teardown", "failed")],
     {"tests": 2, "passed": 1, "failed": 0, "errors": 1, "skipped": 0}, 1),
    ([("a", "setup", "passed"), ("a", "call", "failed"), ("a", "teardown", "failed")],
     {"tests": 1, "passed": 0, "failed": 1, "errors": 1, "skipped": 0}, 2),
    ([("a", "setup", "failed"), ("a", "teardown", "failed")],
     {"tests": 2, "passed": 0, "failed": 0, "errors": 2, "skipped": 0}, 1),
    ([("a", "setup", "skipped"), ("a", "teardown", "failed")],
     {"tests": 2, "passed": 0, "failed": 0, "errors": 1, "skipped": 1}, 1),
    ([("a", "setup", "skipped"), ("a", "teardown", "passed")],
     {"tests": 1, "passed": 0, "failed": 0, "errors": 0, "skipped": 1}, 1),
    ([("a", "setup", "passed"), ("a", "call", "skipped"), ("a", "teardown", "passed")],
     {"tests": 1, "passed": 0, "failed": 0, "errors": 0, "skipped": 1}, 1),
    ([("a", "setup", "passed")],
     {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}, 0),
], ids=["passed", "call-failed", "setup-error", "teardown-error", "call-and-teardown", "setup-and-teardown",
        "skip-and-teardown", "skip-in-setup", "skip-or-xfail-in-call", "interrupted-before-call"])
def test_totals_count_as_junit(reports, expected, tests_from_9_1, teardown_once):
    """tests by the rule of junit.xml before pytest 9.1, and from 9.1 (pytest issue #3850)."""
    totals = Totals(_teardown_once=teardown_once)
    totals.add({"event": "test_start", "nodeid": "a"})
    for nodeid, when, outcome in reports:
        totals.add(report(nodeid, when, outcome))
    totals.add({"event": "log", "text": "RX  x"})
    assert totals.counts() == {**expected, "tests": tests_from_9_1 if teardown_once else expected["tests"]}


@pytest.mark.parametrize("version, once", [((8, 4), False), ((9, 0), False), ((9, 1), True), ((9, 2), True),
                                           ((10, 0), True)], ids=["8.4", "9.0", "9.1", "9.2", "10.0"])
def test_junit_rule_by_pytest_version(version, once):
    assert junit_counts_teardown_once(version) is once


def test_totals_follow_the_installed_pytest():
    major, minor = (int(part) for part in re.match(r"(\d+)\.(\d+)", pytest.__version__).groups())
    assert Totals()._teardown_once is ((major, minor) >= (9, 1))


# Runner: pytest

def test_runner_pytest_totals_equal_junit(tmp_path):
    run = make_run(tmp_path, "pytest", tests=suite_of(tmp_path, "cases", CASES), everything=True)
    run.start()
    finish(run)
    assert run.totals.counts() == junit_counts(run.folder)
    assert (run.verdict, run.exitstatus) == ("FAIL", 1)
    meta = json.loads((run.folder / "run.json").read_text(encoding="utf-8"))
    assert {"kind", "selection", "commit", "commands", "bench", "started", "verdict", "exitstatus", "totals",
            "forced", "ended"} <= set(meta)
    assert (meta["verdict"], meta["totals"]) == ("FAIL", run.totals.counts())
    assert (run.folder / "bench.yaml").exists() and (run.folder / "pytest.log").exists()
    kinds = [event["event"] for event in run.seen]
    assert kinds[-1] == "run_end" and kinds.count("run_end") == 1
    assert run.seen[-1]["verdict"] == "FAIL" and run.folder.parent == tmp_path / "runs"


def test_runner_pytest_teardown_errors_equal_junit(tmp_path):
    """Each teardown error case alone: CASES has one of each kind, their differences cancel out."""
    run = make_run(tmp_path, "pytest", tests=suite_of(tmp_path, "teardown", TEARDOWNS), everything=True)
    run.start()
    finish(run)
    assert run.totals.counts() == junit_counts(run.folder)
    assert (run.totals.failed, run.totals.errors, run.totals.skipped, run.totals.passed) == (1, 5, 1, 1)


def test_runner_pytest_all_passed(tmp_path):
    run = make_run(tmp_path, "pytest", selection=["test_passing.py"], tests=suite_of(tmp_path, "passing", PASSING))
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("PASS", 0)
    assert run.totals.counts() == junit_counts(run.folder) == {"tests": 2, "passed": 2, "failed": 0, "errors": 0,
                                                                "skipped": 0}
    assert run.folder.name.endswith("-pytest")


def test_runner_pytest_nothing_collected(tmp_path):
    run = make_run(tmp_path, "pytest", tests=write(tmp_path / "empty", {"pytest.ini": INI}), everything=True)
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus, run.totals.tests) == ("BENCH ERROR", 5, 0)


def test_runner_pytest_stop(tmp_path):
    run = make_run(tmp_path, "pytest", tests=suite_of(tmp_path, "long", LONG), everything=True)
    run.start()
    assert wait_until(lambda: any(event.get("text") == "RX  tick" for event in run.seen))
    run.stop()
    finish(run)
    assert run.verdict == "INTERRUPTED" and not run.forced
    assert group_gone(run)
    assert json.loads((run.folder / "run.json").read_text(encoding="utf-8"))["verdict"] == "INTERRUPTED"


def test_runner_pytest_stop_deferred_during_flash(tmp_path):
    run = make_run(tmp_path, "pytest", tests=suite_of(tmp_path, "flash", FLASHING), everything=True)
    run.start()
    assert wait_until(lambda: run.flashing)
    run.stop()
    assert run.deferred and not run.finished.is_set()
    finish(run)
    assert run.verdict == "INTERRUPTED" and not run.forced and not run.deferred
    assert [text.split(":")[0] for text in notes(run)] == ["Stop deferred", "Flash over"]
    texts = [event.get("text") for event in run.seen]
    assert "RUN make reset" in texts  # The flash ended before the SIGINT
    assert group_gone(run)


def test_runner_pytest_second_stop_forces(tmp_path):
    run = make_run(tmp_path, "pytest", tests=suite_of(tmp_path, "flash", FLASHING), everything=True)
    run.start()
    assert wait_until(lambda: run.flashing)
    started = time.monotonic()
    run.stop()
    run.stop()
    finish(run)
    assert time.monotonic() - started < 1.0
    assert run.verdict == "INTERRUPTED" and run.forced
    assert "RUN make reset" not in [event.get("text") for event in run.seen]
    assert any(text.startswith("Stop forced") for text in notes(run))
    assert run.seen[-1]["forced"] is True
    assert group_gone(run)


# Runner: T1-T8

@pytest.fixture
def fakes(tmp_path):
    return write(tmp_path / "fakes", {"fake_make.py": FAKE_MAKE, "fake_rx.py": FAKE_RX})


def rx_run(tmp_path, fakes, mode="pass", reset="reset"):
    commands = [[PY, str(fakes / "fake_make.py"), "uart-diag-flash"], [PY, str(fakes / "fake_make.py"), reset],
                [PY, str(fakes / "fake_rx.py"), mode]]
    return make_run(tmp_path, "rx_check", selection=["T1", "T3"], rx_commands=commands)


def rx_reports(run: Run) -> list:
    return [(event["nodeid"], event["hil_outcome"], event["message"])
            for event in read_events(run.events_path) if event["event"] == "report"]


def test_runner_rx_pass(tmp_path, fakes):
    run = rx_run(tmp_path, fakes)
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("PASS", 0)
    assert rx_reports(run) == [("rx:T1", "PASS", ""), ("rx:T3", "PASS", "")]
    assert run.totals.counts() == {"tests": 2, "passed": 2, "failed": 0, "errors": 0, "skipped": 0}
    assert run.folder.name.endswith("-uart-rx")


def test_runner_rx_stream_format(tmp_path, fakes):
    run = rx_run(tmp_path, fakes)
    run.start()
    finish(run)
    events = read_events(run.events_path)
    kinds = [event["event"] for event in events]
    assert kinds[:2] == ["session_start", "collected"] and kinds[-1] == "session_end"
    assert events[1]["nodeids"] == ["rx:T1", "rx:T3"]
    assert all(set(event) == REPORT_KEYS for event in events if event["event"] == "report")
    logs = [(event["logger"], event["text"]) for event in events if event["event"] == "log"]
    assert sum(logger == "hil.serial" for logger, _ in logs) == 6
    assert ("hil.programmer", "RUN make uart-diag-flash") in logs and ("hil.programmer", "RUN make reset") in logs
    assert ("rx_check", "CHECK T7: LD1 keeps blinking at 2 Hz (visual)") in logs
    assert [event for event in run.seen if event["event"] != "run_end"
            and event.get("logger") != "tui.runner"] == events  # on_event got the same stream


def test_runner_rx_fail(tmp_path, fakes):
    run = rx_run(tmp_path, fakes, mode="fail")
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("FAIL", 1)
    assert rx_reports(run) == [("rx:T1", "PASS", ""), ("rx:T3", "FUNCTIONAL_ERROR", "no marker")]


def test_runner_rx_serial_error(tmp_path, fakes):
    run = rx_run(tmp_path, fakes, mode="serial")
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("BENCH ERROR", 2)
    nodeid, outcome, message = rx_reports(run)[-1]
    assert (nodeid, outcome) == ("rx:T3", "BENCH_ERROR") and message.startswith("Serial error")


def test_runner_rx_stop_deferred_during_flash(tmp_path, fakes):
    run = rx_run(tmp_path, fakes)
    run.start()
    assert wait_until(lambda: run.flashing)
    run.stop()
    assert run.deferred
    finish(run)
    assert run.verdict == "INTERRUPTED" and not run.forced
    texts = [event.get("text", "") for event in run.seen]
    assert "RUN make reset" not in texts and not any(text.startswith("TX ") for text in texts)
    assert rx_reports(run) == []


def test_runner_rx_make_failure(tmp_path, fakes):
    run = rx_run(tmp_path, fakes, reset="fail")
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("BENCH ERROR", 2)
    assert any("failed with exit status 2" in text for text in notes(run))
    assert rx_reports(run) == []
    assert not any(event.get("text", "").startswith("TX ") for event in run.seen)


# Runner: scenarios

@pytest.fixture
def lcd(tmp_path):
    return load(write(tmp_path / "scenarios", {"lcd.yaml": LCD}) / "lcd.yaml", CATALOG)


def pixel_ok(name, args):
    return Response(1, "OK", None, {"color": "0xF800"} if name == "LCD_PIXEL" else {})


def test_runner_scenario_pass(tmp_path, lcd):
    run = make_run(tmp_path, "scenario", scenario=lcd, request=pixel_ok, ask=lambda text: True)
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("PASS", 0)
    assert run.totals.counts() == {"tests": 4, "passed": 4, "failed": 0, "errors": 0, "skipped": 0}
    assert run.folder.name.endswith("-lcd")
    assert [event["event"] for event in read_events(run.events_path)][-1] == "session_end"


def test_runner_scenario_stop_between_steps(tmp_path, lcd):
    calls = []
    holder = {}

    def request(name, args):
        calls.append(name)
        holder["run"].stop()  # The operator presses Stop during step 1
        return pixel_ok(name, args)

    run = holder["run"] = make_run(tmp_path, "scenario", scenario=lcd, request=request, ask=lambda text: True)
    run.start()
    finish(run)
    assert (run.verdict, run.exitstatus) == ("INTERRUPTED", 2)
    assert calls == ["LCD_INIT"] and run.totals.passed == 1


def test_runner_survives_a_failing_on_event(tmp_path, lcd):
    def on_event(event):
        raise RuntimeError("display broken")

    run = Run("scenario", on_event=on_event, scenario=lcd, request=pixel_ok, ask=lambda text: True,
              results=tmp_path / "runs")
    run.start()
    finish(run)
    assert run.verdict == "PASS"
    assert json.loads((run.folder / "run.json").read_text(encoding="utf-8"))["verdict"] == "PASS"


def test_runner_refuses_bad_arguments(tmp_path):
    with pytest.raises(ValueError):
        Run("other", results=tmp_path)
    with pytest.raises(ValueError):
        Run("scenario", results=tmp_path)


# core/scenario.py

def requester(color="0xF800", lose_at=None, stop=None):
    calls = []

    def request(name, args):
        calls.append(name)
        if stop is not None:
            stop.set()
        if name == lose_at:
            raise UnexpectedReset("READY while idle: READY name=hil-bench reset=SW")
        return Response(len(calls), "OK", None, {"color": color} if name == "LCD_PIXEL" else {})

    request.calls = calls
    return request


@pytest.mark.parametrize("case, status, outcomes, calls", [
    ("all-pass", 0, ["PASS"] * 4, 3),
    ("other-value", 1, ["PASS", "PASS", "FUNCTIONAL_ERROR", "PASS"], 3),
    ("answer-no", 1, ["PASS", "PASS", "PASS", "FUNCTIONAL_ERROR"], 3),
    ("session-lost", 1, ["PASS", "UNEXPECTED_RESET"], 2),
    ("stop", 2, ["PASS"], 1),
], ids=["all-pass", "other-value", "answer-no", "session-lost", "stop"])
def test_scenario_run(lcd, case, status, outcomes, calls):
    stop = threading.Event()
    request = requester(color="0x0000" if case == "other-value" else "0xF800",
                        lose_at="LCD_FILL" if case == "session-lost" else None,
                        stop=stop if case == "stop" else None)
    events = []
    result = play_scenario(lcd, request, lambda text: case != "answer-no", events.append, stop)
    reports = [event for event in events if event["event"] == "report"]
    assert result == status
    assert [event["hil_outcome"] for event in reports] == outcomes
    assert len(request.calls) == calls
    assert events[-1] == {**events[-1], "event": "session_end", "exitstatus": status}
    if case == "other-value":
        assert reports[2]["message"] == "color: expected 0xf800, got 0x0000"
    if case == "answer-no":
        prompts = [event["text"] for event in events if event["event"] == "log"]
        assert prompts == ["PROMPT Is the screen red? -> no"]


def test_scenario_nodeids(lcd):
    events = []
    play_scenario(lcd, requester(), lambda text: True, events.append)
    assert events[1]["nodeids"] == [f"scenario:lcd.yaml::step{n}" for n in range(1, 5)]
    kinds = Counter(event["event"] for event in events)
    assert kinds["test_start"] == kinds["report"] == kinds["test_end"] == 4


@pytest.mark.parametrize("name", sorted(BAD))
def test_scenario_refused(tmp_path, name):
    text, fragment = BAD[name]
    path = write(tmp_path, {f"{name}.yaml": text}) / f"{name}.yaml"
    with pytest.raises(ScenarioError) as error:
        load(path, CATALOG)
    assert str(error.value).startswith(f"{path}: ")
    assert fragment in str(error.value)
    if name == "out_of_range":
        assert "quote" not in str(error.value)  # The hint is for hex values only


def test_scenario_load_all(tmp_path):
    folder = write(tmp_path / "mixed", {"a_good.yaml": LCD, "b_bad.yaml": BAD["unknown_command"][0],
                                        "notes.txt": "not a scenario"})
    found, errors = load_all(folder, CATALOG)
    assert [item.name for item in found] == ["LCD colour check"]
    assert len(errors) == 1 and "b_bad.yaml" in errors[0]


# core/suites.py

def test_suites_rx_plan():
    rx = discover_rx()
    assert [item.id for item in rx.items] == [f"T{n}" for n in range(1, 9)]
    assert rx.items[6].after == ("T3", "T4", "T5", "T6")
    assert rx_selection(["T7"], rx) == ["T3", "T4", "T5", "T6", "T7"]
    assert rx_selection(["T7", "T1"], rx) == ["T1", "T3", "T4", "T5", "T6", "T7"]
    with pytest.raises(SuitesError, match="T9"):
        rx_selection(["T9"], rx)


def test_suites_rx_bad_plan(tmp_path):
    plan = write(tmp_path, {"plan.yaml": "tests: []\n"}) / "plan.yaml"
    with pytest.raises(SuitesError, match="non-empty list"):
        discover_rx(plan)


def test_suites_collect_hil(tmp_path):
    before = HIL_LOG.stat().st_mtime if HIL_LOG.exists() else None
    suite = discover_pytest(tmp_path / "work")
    assert suite.items and suite.errors == []
    assert "cases/test_smoke.py" in {item.group for item in suite.items}
    assert all(item.id.startswith(f"{item.group}::") for item in suite.items)
    assert (tmp_path / "work" / "collect.log").exists()
    assert (HIL_LOG.stat().st_mtime if HIL_LOG.exists() else None) == before


def test_suites_broken_collection(tmp_path):
    broken = write(tmp_path / "broken", {"pytest.ini": INI, "test_broken.py": "def test_x(:\n    pass\n"})
    with pytest.raises(SuitesError) as error:
        discover_pytest(tmp_path / "work", broken)
    assert str(error.value).startswith("pytest collection failed")
    assert "Traceback" not in str(error.value)


def test_suites_scenarios(tmp_path):
    assert (lambda suite: (suite.items, suite.errors))(discover_scenarios(CATALOG, tmp_path / "absent")) == ([], [])
    folder = write(tmp_path / "mixed", {"a_good.yaml": LCD, "b_bad.yaml": BAD["unknown_command"][0]})
    found = discover_scenarios(CATALOG, folder)
    assert [(item.id, item.title) for item in found.items] == [("a_good.yaml", "LCD colour check")]
    assert len(found.errors) == 1


def test_suites_failure_stays_in_its_family(tmp_path):
    broken = write(tmp_path / "broken", {"pytest.ini": INI, "test_broken.py": "def test_x(:\n    pass\n"})
    folder = write(tmp_path / "mixed", {"a_good.yaml": LCD, "b_bad.yaml": BAD["unknown_command"][0]})
    suites = discover_all(CATALOG, tmp_path / "work", tests=broken, folder=folder)
    assert {suite.kind: (len(suite.items), len(suite.errors)) for suite in suites} == {
        "pytest": (0, 1), "rx_check": (8, 0), "scenario": (1, 1)}
