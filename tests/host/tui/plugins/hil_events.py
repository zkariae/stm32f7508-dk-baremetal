"""pytest plugin that streams a run as events.jsonl, for the TUI (C2, C3, C4).

Loaded only on request, the pytest configuration is unchanged (README.md
section 4.3):

    PYTHONPATH=tests/host/tui/plugins python3 -m pytest tests/host/hil \\
        -p hil_events --hil-events work/hil-results/<run>/events.jsonl

Without --hil-events the plugin does nothing. Each event is one JSON object
on its own line, written and flushed at once, so a reader follows the run
live and a run killed with SIGKILL leaves every line written so far intact.
Each line has t (epoch seconds) and event:

    session_start  pid, args, rootdir
    collected      count, nodeids
    test_start     nodeid
    log            nodeid (null outside a test), logger, level, text
    report         nodeid, when, outcome, hil_outcome, duration, message, xfail
    test_end       nodeid
    session_end    exitstatus

log carries every record of the hil loggers (TX, RX, RUN make, banner) at
DEBUG, the level of pytest.log, so both show the same lines; no logger level
is changed. report is sent for each phase (setup, call, teardown); the
plugin does not count, the reader counts as JUnit does (a failed call is a
failure, a failed setup or teardown an error, a skip or an xfail skipped).

hil_outcome classifies a phase (README.md section 3): PASS, SKIPPED, the
outcome of a HilOutcome exception (tests/protocol.md section 7.3),
FUNCTIONAL_ERROR for a plain assert, BENCH_ERROR for anything else. The
exception class is recognised by name, so the plugin needs no import of
the HIL adapters. A write error never fails the tests: the plugin prints one
line on stderr and stops writing.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import json
import logging
import os
import sys
import threading
import time

import pytest

LOGGER = "hil"  # Parent of hil.serial, hil.board, hil.programmer and hil.fixtures
MESSAGE_MAX = 300  # Characters kept of a failure or skip message


def pytest_addoption(parser):
    group = parser.getgroup("hil events", "event stream for the HIL bench TUI")
    group.addoption("--hil-events", metavar="PATH", default=None,
                    help="write the run as JSON lines to PATH (one event per line, flushed at once)")


def pytest_configure(config):
    path = config.getoption("hil_events")
    if path:
        config.pluginmanager.register(EventStream(config, path), "hil_events_stream")


def classify(report, excinfo) -> str:
    """hil_outcome of one phase."""
    if report.skipped:
        return "SKIPPED"
    if report.passed:
        return "PASS"
    if excinfo is None:
        return "BENCH_ERROR"  # A failure without exception, such as a strict XPASS
    error = excinfo.value
    if any(cls.__name__ == "HilOutcome" for cls in type(error).__mro__):
        return str(getattr(error, "outcome", "PROTOCOL_FAILURE"))
    if isinstance(error, AssertionError):
        return "FUNCTIONAL_ERROR"
    return "BENCH_ERROR"


def message_of(report, excinfo) -> str:
    """First line of the failure or the skip reason, shortened."""
    if report.passed:
        return ""
    if report.skipped and isinstance(report.longrepr, tuple):
        text = str(report.longrepr[2])  # (file, line, reason)
    elif excinfo is not None:
        text = excinfo.exconly()
    else:
        text = str(report.longrepr or "")
    text = text.strip().splitlines()[0] if text.strip() else ""
    return text if len(text) <= MESSAGE_MAX else text[:MESSAGE_MAX - 3] + "..."


class _Handler(logging.Handler):
    """Hands each hil record to the stream."""

    def __init__(self, stream):
        super().__init__(logging.DEBUG)
        self.stream = stream

    def emit(self, record):
        try:
            self.stream.log_record(record)
        except Exception:  # A record must never break the code that logs it
            self.handleError(record)


class EventStream:
    """Writes the events of one pytest session."""

    def __init__(self, config, path):
        self.config = config
        self.path = path
        self.lock = threading.Lock()  # Records may come from other threads
        self.nodeid = None  # Test running now
        self.failed = False
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        self.file = open(path, "w", encoding="utf-8")
        self.handler = _Handler(self)
        logging.getLogger(LOGGER).addHandler(self.handler)

    def write(self, event: str, **fields) -> None:
        if self.failed:
            return
        line = json.dumps({"t": fields.pop("t", time.time()), "event": event, **fields}, ensure_ascii=False)
        with self.lock:
            try:
                self.file.write(line + "\n")
                self.file.flush()
            except (OSError, ValueError) as error:  # Disk full, file closed: warn once, keep testing
                self.failed = True
                print(f"hil_events: writing {self.path} stopped: {error}", file=sys.stderr)

    def log_record(self, record) -> None:
        self.write("log", t=record.created, nodeid=self.nodeid, logger=record.name,
                   level=record.levelname, text=record.getMessage())

    # Hooks

    def pytest_sessionstart(self, session):
        self.write("session_start", pid=os.getpid(), args=list(self.config.invocation_params.args),
                   rootdir=str(self.config.rootpath))

    def pytest_collection_finish(self, session):
        self.write("collected", count=len(session.items), nodeids=[item.nodeid for item in session.items])

    def pytest_runtest_logstart(self, nodeid, location):
        self.nodeid = nodeid
        self.write("test_start", nodeid=nodeid)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        excinfo = call.excinfo
        self.write("report", nodeid=report.nodeid, when=report.when, outcome=report.outcome,
                   hil_outcome=classify(report, excinfo), duration=round(report.duration, 6),
                   message=message_of(report, excinfo), xfail=hasattr(report, "wasxfail"))

    def pytest_runtest_logfinish(self, nodeid, location):
        self.write("test_end", nodeid=nodeid)
        self.nodeid = None

    def pytest_sessionfinish(self, session, exitstatus):
        self.write("session_end", exitstatus=int(exitstatus))

    def pytest_unconfigure(self, config):
        logging.getLogger(LOGGER).removeHandler(self.handler)
        with self.lock:
            try:
                self.file.close()
            except OSError:  # The unwritten buffer of a failed write is flushed again here
                pass
