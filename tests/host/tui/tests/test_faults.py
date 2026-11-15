"""Faults seen from the TUI, on the fake firmware: the C6 matrix (E29).

No board. HilApp runs with App.run_test() and its real Session thread on the
fake bench of test_ui_commands, extended with three faults: the cable
unplugged (every read, write and open of the port raises OSError, as pyserial
does), the port held by another program (PortBusy, as the lock of E7 reports
it) and a silent board (no banner after a reset, no answer to a request).
Each fault is played at connection, in a session and during a run; a run
holds the port, so a fault during a run shows when the TUI connects again
after it. A FakeRun stands for the run and is ended by the test.

Checked for each case: the state and its own message with the next step, the
Connection box only for a lost port or session, the application still
running, then the fault cleared and the key of that next step (Connect or
Recover, under the box when there is one) back to CONNECTED in the same
application. Also: the three faults give three different messages, Disconnect
works in each state it is offered, Quit during a real pytest run asks first,
a No keeps the run and a Yes stops its whole process group, and the next
launch checks the board again (reset and banner).

Not tested here: a real USB unplug (by hand on the board), the port lock
between programs (test_session.py), minicom, which takes no lock (a limit
documented in ci/README.md), and the timer gap of the interface (E30).

Version: 1.0
Date: 15/11/2026
Author: Z. BEN-AKKA
History:
  1.0  15/11/2026  Initial version.
"""

import asyncio
import os
import signal
import time
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Button  # noqa: E402

import test_ui_commands as ui  # noqa: E402
from adapters.serial_adapter import PortBusy, SerialAdapter  # noqa: E402
from core.runner import Run  # noqa: E402
from core.session import Session, State  # noqa: E402
from ui import tests_pane  # noqa: E402  (the module: pytest would try to collect the class TestsPane)
from ui.app import ConfirmScreen, HilApp  # noqa: E402
from ui.progress_box import ProgressBox  # noqa: E402

pytestmark = pytest.mark.ui

HOLDER = "python3 -m serial.tools.miniterm (PID 42)"
RUN_WAIT = 60.0  # Seconds for a real pytest run to start its test
GONE_WAIT = 10.0  # Seconds for the process group to be gone after Quit
STEP = 0.05


# Fake bench with faults

class FaultPort(ui.Port):
    """The fake port; unplugged, every read and write raises like pyserial on a lost device."""

    def __init__(self, responder):
        super().__init__(responder)
        self.unplugged = False

    def read_until(self, expected: bytes = b"\n") -> bytes:
        if self.unplugged:
            raise OSError(5, "device disconnected")
        return super().read_until(expected)

    def write(self, data: bytes) -> int:
        if self.unplugged:
            raise OSError(5, "device disconnected")
        return super().write(data)


class FaultProgrammer(ui.Programmer):
    """Reset queues the banner, unless the board is silent; counts the resets."""

    def __init__(self, rig):
        super().__init__(rig.port)
        self.rig = rig

    def reset(self) -> None:
        self.rig.resets += 1
        if not self.rig.no_banner:
            super().reset()


class Rig(ui.Rig):
    """The fake bench of test_ui_commands, with a cable, a port lock and a board that can fail."""

    def __init__(self):
        super().__init__()
        self.port = FaultPort(self.respond)
        self.no_banner = False
        self.resets = 0

    def unplug(self) -> None:
        self.port.unplugged = True

    def plug(self) -> None:
        self.port.unplugged = False

    def mute(self) -> None:
        """No banner after a reset and no answer to a request."""
        self.silent = self.no_banner = True

    def unmute(self) -> None:
        self.silent = self.no_banner = False

    def open(self, serial_config, timeout, name):
        if self.port.unplugged:
            raise OSError(2, f"could not open port {name}: No such file or directory")
        if self.holder is not None:
            raise PortBusy(name, self.holder)
        self.port.closed = False
        return SerialAdapter(self.port, timeout)

    def session(self, bench, on_event, port=None) -> Session:
        return Session(bench, on_event, port=port, open_port=self.open, programmer=FaultProgrammer(self))


class FakeRun:
    """A run that holds the port until the test ends it with finish()."""

    def __init__(self, kind: str, on_event, folder: Path):
        self.kind = kind
        self.on_event = on_event
        self.folder = folder
        self.forced = False
        self.stopped = False

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)

    def stop(self) -> None:
        self.stopped = True

    def finish(self, verdict: str = "PASS") -> None:
        self.on_event({"t": time.time(), "event": "run_end", "verdict": verdict, "forced": False,
                       "folder": str(self.folder)})


def fake_runs(root: Path):
    """run_factory of HilApp: one FakeRun per run, in its own folder."""
    count = []

    def factory(kind, selection, on_event, **kwargs):
        count.append(kind)
        return FakeRun(kind, on_event, root / f"run-{len(count)}")

    return factory


def drive(rig: Rig, scenario, connected: bool = True, run_factory=None) -> HilApp:
    """test_ui_commands.drive with a run factory."""

    async def main():
        kwargs = {"run_factory": run_factory} if run_factory is not None else {}
        app = HilApp(rig.bench, ui.CATALOG, rig.session, **kwargs)
        try:
            async with app.run_test(size=ui.SIZE) as pilot:
                if connected:
                    await ui.until(pilot, app, State.CONNECTED)
                await scenario(pilot, app)
        finally:
            if app.session is not None:
                app.session.shutdown()
        return app

    return asyncio.run(main())


async def wait_for(pilot, condition, what: str, timeout: float = ui.WAIT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause(STEP)
    pytest.fail(f"timed out waiting for {what}")


def boxes(app: HilApp) -> list:
    return [screen for screen in app.screen_stack if isinstance(screen, ProgressBox)]


def message(app: HilApp) -> str:
    return ui.text(app, "#message")


async def start_run(pilot, app: HilApp) -> None:
    """Run the whole pytest family from the Tests tab; the session releases the port first."""
    app.tests.post_message(tests_pane.TestsPane.Run("pytest", [], True))
    await wait_for(pilot, lambda: app.active_run is not None, "the run start")


# The C6 matrix: fault x moment

CASES = [
    # id, fault, moment, state, message, next step, Connection box, key of the next step
    ("cable-at-connection", "cable", "connection", State.DISCONNECTED, "Port lost (", "Check the cable", True,
     "ctrl+n"),
    ("cable-in-session", "cable", "session", State.DISCONNECTED, "Port lost (", "Check the cable", True, "ctrl+n"),
    ("cable-during-a-run", "cable", "run", State.DISCONNECTED, "Port lost (", "Check the cable", True, "ctrl+n"),
    ("busy-at-connection", "busy", "connection", State.DISCONNECTED, f"held by {HOLDER}", "Close it, then Connect",
     False, "ctrl+n"),
    ("busy-during-a-run", "busy", "run", State.DISCONNECTED, f"held by {HOLDER}", "Close it, then Connect", False,
     "ctrl+n"),
    ("silent-at-connection", "silent", "connection", State.UNKNOWN_IMAGE, "", "Flash hil-bench", False, "ctrl+r"),
    ("silent-in-session", "silent", "session", State.SESSION_LOST, "LED_GET", "Press Recover", True, "ctrl+r"),
    ("silent-during-a-run", "silent", "run", State.UNKNOWN_IMAGE, "", "Flash hil-bench", False, "ctrl+r"),
]


def apply(rig: Rig, fault: str) -> None:
    {"cable": rig.unplug, "busy": lambda: setattr(rig, "holder", HOLDER), "silent": rig.mute}[fault]()


def clear(rig: Rig, fault: str) -> None:
    {"cable": rig.plug, "busy": lambda: setattr(rig, "holder", None), "silent": rig.unmute}[fault]()


@pytest.mark.parametrize("fault, moment, state, text, hint, box, key",
                         [case[1:] for case in CASES], ids=[case[0] for case in CASES])
def test_fault(tmp_path, fault, moment, state, text, hint, box, key):
    rig = Rig()
    if moment == "connection":
        apply(rig, fault)

    async def scenario(pilot, app):
        if moment == "session":
            await ui.until(pilot, app, State.CONNECTED)
            apply(rig, fault)
            if fault == "silent":  # Seen at the next request: the board is idle otherwise
                await ui.select(pilot, app, "LED_GET")
                await ui.send(pilot)
        elif moment == "run":
            await ui.until(pilot, app, State.CONNECTED)
            await start_run(pilot, app)
            apply(rig, fault)  # While the run holds the port
            app.active_run.finish()
        resets = rig.resets
        await wait_for(pilot, lambda: hint in message(app) and app.session.state is state, f"the {fault} message")
        await ui.settle(pilot, app)
        assert text in message(app)
        assert app.is_running  # No crash
        assert bool(boxes(app)) == box
        assert len(boxes(app)) <= 1
        if fault == "busy":
            assert rig.resets == resets  # The board is not reset when the port cannot be opened
        clear(rig, fault)
        await pilot.press(key)  # Under the box when there is one
        await ui.until(pilot, app, State.CONNECTED)
        assert not app.query_one("#send", Button).disabled  # Work resumes in the same application

    drive(rig, scenario, connected=False, run_factory=fake_runs(tmp_path))


def test_faults_have_distinct_messages():
    """The three faults one after the other in one application: three messages, three next steps."""
    rig = Rig()
    rig.holder = HOLDER
    seen = {}

    async def scenario(pilot, app):
        await wait_for(pilot, lambda: "held by" in message(app), "the busy port")
        seen["busy"] = message(app)
        rig.holder = None
        rig.unplug()
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: "Port lost" in message(app), "the lost port")
        seen["cable"] = message(app)
        rig.plug()
        rig.mute()
        await pilot.press("ctrl+n")  # Under the Connection box
        await ui.until(pilot, app, State.UNKNOWN_IMAGE)
        seen["silent"] = message(app)
        rig.unmute()
        await pilot.press("ctrl+r")
        await ui.until(pilot, app, State.CONNECTED)

    drive(rig, scenario, connected=False)
    assert len(set(seen.values())) == 3, seen
    hints = ["Close it, then Connect", "Check the cable", "Flash hil-bench"]
    assert [hint in seen[name] for name, hint in zip(["busy", "cable", "silent"], hints)] == [True] * 3


# Disconnect

@pytest.mark.parametrize("state", [State.CONNECTED, State.SESSION_LOST, State.UNKNOWN_IMAGE],
                         ids=["connected", "session-lost", "unknown-image"])
def test_disconnect_available(state):
    rig = Rig()

    async def scenario(pilot, app):
        if state is State.SESSION_LOST:
            await ui.select(pilot, app, "LED_GET")
            rig.silent = True
            await ui.send(pilot)
        elif state is State.UNKNOWN_IMAGE:
            rig.mute()
            await pilot.press("ctrl+b")
            await ui.until(pilot, app, State.DISCONNECTED)
            await pilot.press("ctrl+n")
        await ui.until(pilot, app, state)
        assert not app.query_one("#disconnect", Button).disabled
        resets = rig.resets
        if boxes(app):
            await pilot.press("escape")  # The Connection box passes only Recover and Connect
            await wait_for(pilot, lambda: not boxes(app), "the box to close")
        await pilot.press("ctrl+b")
        await ui.until(pilot, app, State.DISCONNECTED)
        assert rig.port.closed
        assert rig.resets == resets  # Disconnect does not reset the board

    drive(rig, scenario)


# Quit during a run

LONG_TEST = '''\
import subprocess
import time
from pathlib import Path


def test_long():
    child = subprocess.Popen(["sleep", "60"])  # In the process group of pytest
    Path({pid_file!r}).write_text(str(child.pid))
    time.sleep(60)
'''


def alive(pid: int) -> bool:
    """The process exists and is not a zombie."""
    try:
        status = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return status.rsplit(")", 1)[1].split()[0] != "Z"


def test_quit_during_a_run(tmp_path):
    """Quit asks first; No keeps the run, Yes stops its process group (a child of the test included)."""
    tests = tmp_path / "tests"
    tests.mkdir()
    pid_file = tmp_path / "child.pid"
    (tests / "test_long.py").write_text(LONG_TEST.format(pid_file=str(pid_file)))
    rig = Rig()

    def factory(kind, selection, on_event, **kwargs):
        return Run(kind, selection, on_event, results=tmp_path / "runs", tests=tests, **kwargs)

    async def scenario(pilot, app):
        await start_run(pilot, app)
        await wait_for(pilot, pid_file.exists, "the test child", RUN_WAIT)
        await pilot.press("ctrl+l")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen), "the question")
        await pilot.click("#no")
        await pilot.pause(0.5)
        assert app.active_run is not None and app.is_running  # No: the run goes on
        assert alive(int(pid_file.read_text()))
        await pilot.press("ctrl+l")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen), "the question again")
        await pilot.click("#yes")
        await wait_for(pilot, lambda: app.return_code is not None, "the exit", RUN_WAIT)

    child = None
    try:
        app = drive(rig, scenario, run_factory=factory)
        child = int(pid_file.read_text())
        deadline = time.monotonic() + GONE_WAIT
        while alive(child) and time.monotonic() < deadline:
            time.sleep(STEP)
        assert not alive(child), "the child of the test outlived Quit: the process group was not stopped"
        assert app.return_code == 0
        assert rig.port.closed
    finally:
        if child is not None and alive(child):
            os.kill(child, signal.SIGKILL)


# Next launch

def test_next_launch_checks_the_board():
    """A TUI left in UNKNOWN_IMAGE, then a new launch on the same bench: reset and banner again."""
    rig = Rig()
    rig.mute()

    async def first(pilot, app):
        await ui.until(pilot, app, State.UNKNOWN_IMAGE)
        await pilot.press("ctrl+l")

    async def second(pilot, app):
        await ui.until(pilot, app, State.CONNECTED)

    app = drive(rig, first, connected=False)
    assert app.return_code == 0
    resets = rig.resets
    rig.unmute()
    drive(rig, second, connected=False)
    assert rig.resets == resets + 1  # The launch resets the board and reads its banner
