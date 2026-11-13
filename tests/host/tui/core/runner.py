"""Runs of the TUI: pytest, T1-T8 and scenarios, with live events, Stop and verdict (C2, C3, C6).

Each run gets its own folder, work/hil-results/<YYYYMMDD-HHMMSS>-<suite>/
(README.md section 4.3): events.jsonl, run.json (kind, selection, commands,
Git commit, copy of bench.yaml, then verdict, totals and exit status), and
for pytest junit.xml and pytest.log.

  - pytest: tests/host/hil runs in its own process group with the
    hil_events plugin (plugins/hil_events.py); the runner follows
    events.jsonl as it grows. The whole suite is passed as the folder.
  - rx_check: the steps of ci/scripts/rx_check.sh, make uart-diag-flash,
    make reset, then uart_rx_check.py --trace --only <ids>. The runner turns
    their output into events of the same format: RUN make and make lines,
    TX, RX and BAUD lines as log, PASS and FAIL Tn as report (PASS,
    FUNCTIONAL_ERROR), CHECK Tn as log; a test left without verdict when
    the script ends is BENCH_ERROR with the last error line. The exit
    status is the script's (C3).
  - scenario: core/scenario.py in a thread of this process; the caller
    gives request and ask (the session and the operator).

A flash starts at a RUN make ...-flash line and ends at the next RUN make,
RX line or report, or when its process ends (README.md section 3). Stop
sends SIGINT to the process group, and SIGKILL if it is still alive after
STOP_GRACE. During a flash Stop is deferred until the flash ends; a second
Stop during the flash kills the group at once and sets forced: the image on
the board is then unknown. A scenario stops before its next step.

Totals count the reports as pytest and junit.xml do (C3): a passed call is
passed, a failed call a failure, a failed setup or teardown an error, a skip
or an xfail skipped; tests is the tests attribute of junit.xml, whose rule
for a teardown error changed in pytest 9.1 (Totals follows the installed
pytest, junit_counts_teardown_once). A test interrupted before its first
report is not counted. The verdict is PASS
only with exit status 0 and at least one test, INTERRUPTED after Stop, FAIL
with exit status 1, BENCH ERROR otherwise.

on_event(event) gets every event, plus log events of the logger tui.runner
(Stop deferred, forced) and a final run_end event. It is always called from
one dispatcher thread, in order, never with a lock held and never from the
thread that called stop(), so the TUI may block in it (call_from_thread);
finished is set once run_end has been handed over.

The runner does not free the serial port (the TUI releases its session
first), writes no report (report.py) and shows nothing. No Textual import.

Version: 1.1
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
  1.1  11/11/2026  Fix Totals against the junit.xml of pytest 9.1 and later: the teardown error rule follows the installed pytest.
"""

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path

from core import scenario as scenarios

TUI_DIR = Path(__file__).resolve().parents[1]
REPO = TUI_DIR.parents[2]
HIL_DIR = REPO / "tests" / "host" / "hil"
PLUGINS_DIR = TUI_DIR / "plugins"
RX_SCRIPT = REPO / "tests" / "host" / "rx_check" / "uart_rx_check.py"
RX_IMAGE = "uart-diag"  # Image of the T1-T8 checks, flashed as rx_check.sh does
BENCH = REPO / "tests" / "host" / "config" / "bench.yaml"
RESULTS = REPO / "work" / "hil-results"
POLL = 0.05  # Seconds between two reads of a growing events.jsonl
STOP_GRACE = 5.0  # Seconds after SIGINT before SIGKILL
LOGGER = "tui.runner"

PASS, FAIL, BENCH_ERROR, INTERRUPTED = "PASS", "FAIL", "BENCH ERROR", "INTERRUPTED"
KINDS = ("pytest", "rx_check", "scenario")
_RX_VERDICT = re.compile(r"(PASS|FAIL) (T\d+): ?(.*)")
_RX_TRACE = ("TX  ", "RX  ", "BAUD ")
_RX_ERRORS = ("Serial error", "Configuration error", "Plan error")


def _pytest_version() -> tuple:
    """(major, minor) of the pytest of this interpreter, the one that runs the runs; None without pytest."""
    try:
        match = re.match(r"(\d+)\.(\d+)", metadata.version("pytest"))
    except metadata.PackageNotFoundError:
        return None
    return (int(match[1]), int(match[2])) if match else None


def junit_counts_teardown_once(version: tuple | None = None) -> bool:
    """True when junit.xml counts a teardown error once with the earlier phases of its test (pytest >= 9.1).

    pytest 9.1 changed the tests attribute (pytest issue #3850). A teardown
    error after a failed call opens a second test case in both versions.
      - pytest < 9.1: the teardown error is counted, less one only after a
        failed call (two test cases, counted once).
      - pytest >= 9.1: the teardown error is counted once with its test case,
        except after a failed call (two test cases, counted twice).
    """
    version = version or _pytest_version()
    return version is None or version >= (9, 1)


@dataclass
class Totals:
    """Counts of the reports received so far, as pytest and its junit.xml count them.

    passed is a passed call, failed a failed call, errors a failed setup or
    teardown, skipped a skip or an xfail in any phase. tests is the tests
    attribute of junit.xml: the sum, less one for some teardown errors,
    by the rule of the pytest that runs (junit_counts_teardown_once).
    """

    tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    _failed_call: set = field(default_factory=set, repr=False)
    _teardown_once: bool = field(default_factory=junit_counts_teardown_once, repr=False)

    def add(self, event: dict) -> None:
        if event.get("event") != "report":
            return
        nodeid, when, outcome = event.get("nodeid"), event.get("when"), event.get("outcome")
        if outcome == "passed":
            if when != "call":
                return
            self.passed += 1
        elif outcome == "skipped":
            self.skipped += 1
        elif outcome == "failed":
            if when == "call":
                self.failed += 1
                self._failed_call.add(nodeid)
            else:
                self.errors += 1
                if when == "teardown" and (nodeid in self._failed_call) != self._teardown_once:
                    self.tests -= 1  # junit.xml counts this teardown error with an earlier phase
        else:
            return
        self.tests += 1

    def counts(self) -> dict:
        return {key: value for key, value in asdict(self).items() if not key.startswith("_")}


class Run:
    """One run: start(), stop(), wait(); totals, flashing and verdict are read at any time."""

    def __init__(self, kind: str, selection=None, on_event=None, *, everything: bool = False,
                 scenario=None, request=None, ask=None, results: Path | str = RESULTS,
                 tests: Path | str = HIL_DIR, rx_commands: list | None = None, bench: Path | str = BENCH):
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        if kind == "scenario" and (scenario is None or request is None or ask is None):
            raise ValueError("a scenario run needs scenario, request and ask")
        self.kind = kind
        self.selection = list(selection or [])
        self.on_event = on_event or (lambda event: None)
        self.everything = everything
        self.scenario = scenario
        self.request, self.ask = request, ask
        self.tests = Path(tests)
        self.bench = Path(bench)
        self.rx_commands = rx_commands
        self.folder = self._folder(Path(results))
        self.events_path = self.folder / "events.jsonl"
        self.totals = Totals()
        self.flashing = False
        self.verdict = None
        self.exitstatus = None
        self.forced = False
        self.stop_requested = False
        self.deferred = False  # Stop asked during a flash, not sent yet
        self.finished = threading.Event()
        self._lock = threading.RLock()
        self._process = None
        self._stop = threading.Event()  # Scenario: checked between steps
        self._file = None  # events.jsonl written by the runner (rx_check, scenario)
        self._thread = None
        self._out = queue.Queue()  # Events for on_event, handed over by the dispatcher thread
        self._dispatcher = None
        self._meta = {}

    # Public

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=False)
        self._meta = {"kind": self.kind, "selection": self._selection_text(), "everything": self.everything,
                      "folder": str(self.folder), "commit": _commit(), "bench": str(self.bench),
                      "started": time.time(), "commands": self._commands()}
        try:
            shutil.copyfile(self.bench, self.folder / "bench.yaml")
        except OSError:
            pass  # The report then names the path only
        self._write_meta()
        self._dispatcher = threading.Thread(target=self._dispatch, name=f"run-{self.kind}-events", daemon=True)
        self._dispatcher.start()
        self._thread = threading.Thread(target=self._main, name=f"run-{self.kind}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the run; deferred during a flash, forced by a second Stop during it."""
        with self._lock:
            if self.finished.is_set():
                return
            self.stop_requested = True
            if self.kind == "scenario":
                self._stop.set()
                self._note("Stop: the scenario ends before its next step")
                return
            if self.flashing:
                if self.deferred:
                    self.forced = True
                    self._note("Stop forced during the flash: the board image is unknown")
                    self._signal(signal.SIGKILL)
                else:
                    self.deferred = True
                    self._note("Stop deferred: flashing; press Stop again to force it")
                return
            self._interrupt()

    def wait(self, timeout: float | None = None) -> bool:
        return self.finished.wait(timeout)

    # Main thread of the run

    def _main(self) -> None:
        try:
            if self.kind == "pytest":
                self.exitstatus = self._run_pytest()
            elif self.kind == "rx_check":
                self.exitstatus = self._run_rx()
            else:
                self.exitstatus = self._run_scenario()
        except Exception as error:  # Never leave the TUI waiting for a run that died
            self._note(f"run failed: {error}", level="ERROR")
            self.exitstatus = self.exitstatus if self.exitstatus is not None else -1
            self.verdict = BENCH_ERROR
        finally:
            if self._file is not None:
                self._file.close()
            if self.verdict is None:
                self.verdict = self._verdict()
            self._meta.update(verdict=self.verdict, exitstatus=self.exitstatus, totals=self.totals.counts(),
                              forced=self.forced, ended=time.time())
            self._write_meta()
            self._forward({"t": time.time(), "event": "run_end", "verdict": self.verdict,
                           "exitstatus": self.exitstatus, "totals": self.totals.counts(), "forced": self.forced,
                           "folder": str(self.folder)})
            self._out.put(None)
            self._dispatcher.join()
            self.finished.set()

    def _dispatch(self) -> None:
        while True:
            event = self._out.get()
            if event is None:
                return
            try:
                self.on_event(event)
            except Exception:  # The display must never stop the run
                pass

    def _verdict(self) -> str:
        if self.stop_requested:
            return INTERRUPTED
        if self.exitstatus == 0 and self.totals.tests > 0:
            return PASS
        if self.exitstatus == 1:
            return FAIL
        return BENCH_ERROR

    # pytest

    def _run_pytest(self) -> int:
        command = self._commands()[0]
        output = open(self.folder / "pytest.out", "w", encoding="utf-8")
        try:
            with self._lock:
                if self.stop_requested:
                    return 2
                self._process = subprocess.Popen(command, cwd=REPO, env=_env(), stdout=output,
                                                 stderr=subprocess.STDOUT, start_new_session=True)
            position, partial = 0, ""
            while True:
                done = self._process.poll() is not None
                position, partial = self._follow(position, partial)
                if done:
                    break
                time.sleep(POLL)
            position, partial = self._follow(position, partial)  # Lines written just before the end
            self._flash_over()
            return self._process.returncode
        finally:
            output.close()

    def _follow(self, position: int, partial: str) -> tuple:
        """Hand over the complete lines added to events.jsonl since position."""
        try:
            with open(self.events_path, encoding="utf-8") as stream:
                stream.seek(position)
                data = stream.read()
                position = stream.tell()
        except FileNotFoundError:
            return position, partial
        lines = (partial + data).split("\n")
        for line in lines[:-1]:
            if line.strip():
                try:
                    self._handle(json.loads(line), write=False)
                except ValueError:
                    pass  # A line cut by a kill: the report rebuild skips it too
        return position, lines[-1]

    # T1-T8

    def _run_rx(self) -> int:
        self._open_events()
        ids = list(self.selection)
        nodeids = [f"rx:{test_id}" for test_id in ids]
        self._handle(_event("session_start", pid=os.getpid(), args=self._selection_text(), rootdir=str(REPO)))
        self._handle(_event("collected", count=len(ids), nodeids=nodeids))
        commands = self._commands()
        status = 2
        for index, command in enumerate(commands):
            with self._lock:
                if self.stop_requested:
                    break
            last = index == len(commands) - 1
            if not last:
                status = self._make_step(command)
                if status != 0:
                    if not self.stop_requested:
                        self._note(f"{' '.join(command)} failed with exit status {status}", level="ERROR")
                    break
            else:
                status = self._script_step(command, ids)
        self._handle(_event("session_end", exitstatus=status))
        return status

    def _make_step(self, command: list) -> int:
        target = command[-1]
        self._handle(_event("log", nodeid=None, logger="hil.programmer", level="INFO", text=f"RUN make {target}"))
        process = self._spawn(command)
        for line in process.stdout:
            self._handle(_event("log", nodeid=None, logger="hil.programmer", level="DEBUG",
                                text=f"make {target}: {line.rstrip()}"))
        status = process.wait()
        self._flash_over()
        return status

    def _script_step(self, command: list, ids: list) -> int:
        pending = list(ids)
        current = None
        last_error = ""

        def begin():
            nonlocal current
            current = pending.pop(0) if pending else None
            if current is not None:
                self._handle(_event("test_start", nodeid=f"rx:{current}"))

        process = self._spawn(command)
        begin()
        for raw in process.stdout:
            line = raw.rstrip("\r\n")
            match = _RX_VERDICT.match(line)
            nodeid = f"rx:{current}" if current else None
            if match and match.group(2) == current:
                passed = match.group(1) == "PASS"
                self._handle(_event("report", nodeid=nodeid, when="call", outcome="passed" if passed else "failed",
                                    hil_outcome="PASS" if passed else "FUNCTIONAL_ERROR", duration=0.0,
                                    message="" if passed else match.group(3), xfail=False))
                self._handle(_event("test_end", nodeid=nodeid))
                begin()
            elif line.startswith(_RX_TRACE):
                self._handle(_event("log", nodeid=nodeid, logger="hil.serial", level="INFO", text=line))
            elif line.strip():
                if line.startswith(_RX_ERRORS):
                    last_error = line
                self._handle(_event("log", nodeid=nodeid, logger="rx_check",
                                    level="ERROR" if line.startswith(_RX_ERRORS) else "INFO", text=line))
        status = process.wait()
        if current is not None and not self.stop_requested:  # Ended without a verdict for this test
            nodeid = f"rx:{current}"
            self._handle(_event("report", nodeid=nodeid, when="call", outcome="failed", hil_outcome="BENCH_ERROR",
                                duration=0.0, message=last_error or f"no verdict, exit status {status}",
                                xfail=False))
            self._handle(_event("test_end", nodeid=nodeid))
        return status

    def _spawn(self, command: list):
        with self._lock:
            self._process = subprocess.Popen(command, cwd=REPO, env=_env(), stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, bufsize=1,
                                             start_new_session=True)
            return self._process

    # Scenario

    def _run_scenario(self) -> int:
        self._open_events()
        return scenarios.run(self.scenario, self.request, self.ask, lambda event: self._handle(event), self._stop)

    # Events

    def _handle(self, event: dict, write: bool = True) -> None:
        """One event: written (rx_check, scenario), counted, flash state, handed to on_event."""
        if write and self._file is not None:
            self._file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._file.flush()
        with self._lock:
            self.totals.add(event)
            kind = event.get("event")
            text = str(event.get("text", ""))
            if kind == "log" and text.startswith("RUN "):
                if any(token.endswith("-flash") for token in text.split()):
                    self.flashing = True
                else:
                    self._flash_over()
            elif (kind == "log" and text.startswith("RX ")) or kind == "report":
                self._flash_over()
        self._forward(event)

    def _flash_over(self) -> None:
        with self._lock:
            if not self.flashing:
                return
            self.flashing = False
            if self.deferred and not self.forced:
                self.deferred = False
                self._note("Flash over: stopping now")
                self._interrupt()

    def _forward(self, event: dict) -> None:
        self._out.put(event)

    def _note(self, text: str, level: str = "WARNING") -> None:
        self._forward(_event("log", nodeid=None, logger=LOGGER, level=level, text=text))

    # Signals

    def _interrupt(self) -> None:
        self._signal(signal.SIGINT)
        timer = threading.Timer(STOP_GRACE, self._signal, (signal.SIGKILL,))
        timer.daemon = True
        timer.start()

    def _signal(self, number: int) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, number)  # The group: make, OpenOCD and pytest with it
        except (ProcessLookupError, PermissionError):
            pass

    # Files

    def _folder(self, results: Path) -> Path:
        if self.kind == "scenario":
            suite = Path(getattr(self.scenario, "path", "scenario")).stem
        else:
            suite = {"pytest": "pytest", "rx_check": "uart-rx"}[self.kind]
        stamp = time.strftime("%Y%m%d-%H%M%S")
        folder, number = results / f"{stamp}-{suite}", 2
        while folder.exists():
            folder, number = results / f"{stamp}-{suite}-{number}", number + 1
        return folder

    def _open_events(self) -> None:
        self._file = open(self.events_path, "w", encoding="utf-8")

    def _write_meta(self) -> None:
        temporary = self.folder / "run.json.tmp"
        temporary.write_text(json.dumps(self._meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.folder / "run.json")  # Never half written, even after a kill

    def _selection_text(self) -> list:
        if self.kind == "scenario":
            return [str(getattr(self.scenario, "path", ""))]
        return list(self.selection)

    def _commands(self) -> list:
        if self.kind == "pytest":
            targets = [str(self.tests)] if self.everything or not self.selection else \
                [str(self.tests / nodeid) for nodeid in self.selection]
            return [[sys.executable, "-m", "pytest", *targets, "-p", "hil_events",
                     "--hil-events", str(self.events_path), "--junitxml", str(self.folder / "junit.xml"),
                     "--log-file", str(self.folder / "pytest.log")]]
        if self.kind == "rx_check":
            if self.rx_commands is not None:
                return self.rx_commands
            return [["make", f"{RX_IMAGE}-flash"], ["make", "reset"],
                    [sys.executable, str(RX_SCRIPT), "--trace", "--only", *self.selection]]
        return []


def _event(event: str, **fields) -> dict:
    return {"t": time.time(), "event": event, **fields}


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(PLUGINS_DIR), env.get("PYTHONPATH")]))
    env["PYTHONUNBUFFERED"] = "1"  # Lines in order and at once through the pipe
    return env


def _commit() -> str | None:
    """Short commit of the repository, with -dirty for local changes; None without Git."""
    try:
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short=7", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return f"{commit}-dirty" if commit and dirty else commit or None
