"""Serial session of the TUI: one thread owns the port and the session state.

SerialAdapter only listens during a transaction and is not thread-safe
(README.md section 3), so a single thread opens the port, runs every request
and, while connected and idle, keeps reading: a READY there is an unexpected
reset, a lost port is seen at once. The public methods only queue a job and
return; the thread reports everything through on_event(Event), called from
the thread itself (the TUI hands it over with call_from_thread).

States and rules follow README.md section 4.1 and tests/protocol.md:
  - connect: reset, READY, HELLO and CAPS (sections 4.1, 6.2, 6.3); no valid
    READY or another protocol major leaves UNKNOWN_IMAGE, port kept open;
  - a build other than the local hil_build.h is reported, never blocking;
  - a timeout, a READY or an invalid reply loses the session: the request is
    never sent again and sending waits for recover() (sections 4.3, 8.3);
  - disconnect closes the port without a reset; release closes it before a
    run, and only connect is useful after it;
  - a busy port names its holder; a lost port (cable) closes the session.

The TX and RX lines are not events: the hil.serial logger already traces
them for the monitor. No Textual import.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import enum
import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_HIL_DIR = Path(__file__).resolve().parents[2] / "hil"
if str(_HIL_DIR) not in sys.path:
    sys.path.insert(0, str(_HIL_DIR))  # adapters/ and fixtures/ of the HIL tests, without pytest

import pytest  # noqa: E402  load_bench_config raises pytest.UsageError

from adapters.board import Board, parse_banner  # noqa: E402
from adapters.outcomes import HilOutcome, IncompatibleProtocol, ProgrammingFailure, StartupFailure  # noqa: E402
from adapters.programmer import Programmer  # noqa: E402
from adapters.serial_adapter import PortBusy, SerialAdapter, SessionExhausted  # noqa: E402
from fixtures.board_fixtures import DEFAULT_CONFIG, REPO_ROOT, load_bench_config  # noqa: E402

IDLE_POLL = 0.1  # Seconds of listening between two looks at the job queue
SHUTDOWN_WAIT = 5.0  # Seconds shutdown() waits for the thread

log = logging.getLogger("tui.session")


class SessionError(Exception):
    """Unusable bench configuration."""


class State(enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RUNNING = "RUNNING"
    UNKNOWN_IMAGE = "UNKNOWN_IMAGE"
    SESSION_LOST = "SESSION_LOST"


@dataclass(frozen=True)
class Event:
    """What the session reports: kind is state, response, error, unsolicited or build_mismatch."""

    kind: str
    state: State
    text: str = ""
    data: object = None


def load_bench(path: Path | None = None) -> dict:
    """bench.yaml checked as the HIL fixtures check it; SessionError if unusable."""
    try:
        return load_bench_config(path or DEFAULT_CONFIG)
    except pytest.UsageError as error:
        raise SessionError(str(error)) from None


def bench_programmer(bench: dict) -> Programmer:
    """The make targets of bench.yaml, as the board fixture builds them."""
    hardware = bench["hardware"]
    return Programmer(REPO_ROOT, hardware["board"], hardware["firmware_target"], hardware["reset_target"],
                      bench["timeouts"]["make"], hardware["reset_sw_target"])


def show_response(response) -> str:
    """One-line form of a response: status, code and result fields."""
    parts = [f"status={response.status}"]
    if response.code is not None:
        parts.append(f"code={response.code}")
    parts += [f"{key}={value}" for key, value in response.fields.items()]
    return " ".join(parts)


class Session:
    """The board session of the TUI, run by its own thread."""

    def __init__(self, bench: dict, on_event, port: str | None = None, open_port=SerialAdapter.open,
                 programmer=None):
        self.bench = bench
        self.port = port  # None: serial.port of bench.yaml
        self.on_event = on_event
        self._open_port = open_port
        self.programmer = programmer or bench_programmer(bench)
        self.state = State.DISCONNECTED
        self.banner = None  # Banner of the connected session
        self.names = []  # CAPS list of the connected session
        self._adapter = None
        self._board = None
        self._jobs = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="hil-session", daemon=True)
        self._thread.start()

    # Public methods: queue a job and return at once

    def connect(self) -> None:
        self._jobs.put(("connect", ()))

    def send(self, command: str, args: dict | None = None) -> None:
        """Send one request; args are the checked values of Catalog.check, or a free form."""
        self._jobs.put(("send", (command, dict(args or {}))))

    def recover(self) -> None:
        self._jobs.put(("recover", ()))

    def disconnect(self) -> None:
        self._jobs.put(("disconnect", ()))

    def release(self) -> None:
        """Free the port before a run (pytest or uart_rx_check.py open it themselves)."""
        self._jobs.put(("release", ()))

    def shutdown(self) -> None:
        """Close the port and stop the thread."""
        self._jobs.put(None)
        self._thread.join(SHUTDOWN_WAIT)

    # Thread

    def _run(self) -> None:
        while True:
            if self.state is State.CONNECTED:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    self._guarded(self._listen)
                    continue
            else:
                job = self._jobs.get()
            if job is None:
                self._close()
                return
            name, args = job
            self._guarded(getattr(self, f"_{name}"), *args)

    def _guarded(self, job, *args) -> None:
        """Run a job; a port or bench failure closes the session, nothing stops the thread."""
        try:
            job(*args)
        except PortBusy as error:
            self._close()
            self._set(State.DISCONNECTED, str(error), kind="error")  # "<port> is busy: held by ..."
        except OSError as error:  # serial.SerialException is an OSError: cable unplugged, no such port
            self._close()
            self._set(State.DISCONNECTED, f"port lost: {error}", kind="error")
        except ProgrammingFailure as error:
            self._close()
            self._set(State.DISCONNECTED, f"reset failed: {error}", kind="error")
        except Exception as error:  # A bug must not take the TUI down (C6)
            log.exception("session job failed")
            self._close()
            self._set(State.DISCONNECTED, f"internal error: {error!r}", kind="error")

    def _connect(self) -> None:
        if self.state in (State.CONNECTED, State.CONNECTING):
            self._emit("error", "already connected")
            return
        self._close()
        self._set(State.CONNECTING)
        self._adapter = self._open_port(self.bench["serial"], self.bench["timeouts"]["response"], self.port)
        settle = self.bench["delays"]["port_open_settle"]
        time.sleep(settle)  # Let the serial adapter settle after opening
        # Build checked here, not by Board: a mismatch is shown, never blocking
        self._board = Board(self._adapter, self.programmer, self.bench["timeouts"]["startup"], settle)
        self._start()

    def _recover(self) -> None:
        if self.state not in (State.SESSION_LOST, State.UNKNOWN_IMAGE) or self._board is None:
            self._emit("error", f"nothing to recover in state {self.state.value}")
            return
        self._set(State.CONNECTING)
        self._start()

    def _start(self) -> None:
        """Reset, READY, HELLO and CAPS on the open port (section 3.4)."""
        self.banner, self.names = None, []
        try:
            banner = self._board.start_session()
        except (StartupFailure, IncompatibleProtocol) as error:
            self._set(State.UNKNOWN_IMAGE, str(error))
            return
        try:
            self._board.identify()
            names = self._board.capabilities()
        except HilOutcome as error:  # str() starts with the outcome of section 7.3
            self._set(State.SESSION_LOST, str(error))
            return
        expected = self.programmer.build_id()
        if expected is not None and banner.build != expected:
            self._emit("build_mismatch", f"firmware build={banner.build}, local build {expected}",
                       {"firmware": banner.build, "local": expected})
        self.banner, self.names = banner, names
        self._set(State.CONNECTED, banner.text, {"banner": banner, "names": names})

    def _send(self, command: str, args: dict) -> None:
        if self.state is not State.CONNECTED:
            self._emit("error", f"{command} not sent: session is {self.state.value}")
            return
        try:
            response = self._board.request(command, **args)
        except (HilOutcome, SessionExhausted) as error:
            # Never sent again (section 8.3): the operator decides with recover()
            self._set(State.SESSION_LOST, f"{command}: {error}")
            return
        self._emit("response", f"{command} {show_response(response)}",
                   {"command": command, "args": args, "response": response})

    def _listen(self) -> None:
        """Idle read: a READY loses the session (section 4.3), any other line is reported."""
        line = self._adapter.read_line(time.monotonic() + IDLE_POLL)
        if line is None or not line.strip(" "):
            return
        if parse_banner(line) is not None:
            self._set(State.SESSION_LOST, f"UNEXPECTED_RESET: READY while idle: {line}")
            return
        self._emit("unsolicited", line)

    def _disconnect(self) -> None:
        self._close()
        self._set(State.DISCONNECTED)

    def _release(self) -> None:
        self._close()
        self._set(State.RUNNING)

    def _close(self) -> None:
        self.banner, self.names = None, []
        self._board = None
        adapter, self._adapter = self._adapter, None
        if adapter is not None:
            try:
                adapter.close()
            except OSError as error:  # Already gone with the cable
                log.info("close: %s", error)

    # Events

    def _set(self, state: State, text: str = "", data=None, kind: str = "state") -> None:
        self.state = state
        self._emit(kind, text, data)

    def _emit(self, kind: str, text: str = "", data=None) -> None:
        log.info("%s %s %s", kind, self.state.value, text)
        try:
            self.on_event(Event(kind, self.state, text, data))
        except Exception:  # A broken listener must not stop the session
            log.exception("on_event failed")
