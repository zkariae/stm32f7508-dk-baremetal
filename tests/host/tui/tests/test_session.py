"""Host tests of core/session.py and of the serial port lock (C6).

No board. The session runs its real thread on the fake port and fake
firmware of tests/host/hil/unit/hil_fake.py, with a fake programmer whose
reset queues a banner; the timeouts are cut so the file runs in seconds. The
tests check the states of README.md section 4.1, that a refused or lost
request is never written again, and that port and bench faults end in a
state, never in a dead thread.

The lock tests use a real pty held by this process or by a child process:
SerialAdapter.open (E7) and uart_rx_check.py (E8) must refuse it and name
the holder. port_holder is also checked on fake /proc/locks and /proc trees.
They read /proc, so they run on Linux only.

Not tested here: the real board, the make targets and a real USB unplug
(checked by hand on the board in E9), and the TUI display.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import copy
import os
import queue
import subprocess
import sys
import time
from pathlib import Path

import pytest

from adapters.outcomes import ProgrammingFailure
from adapters.serial_adapter import HOLDER_MAX_LEN, PortBusy, SerialAdapter, port_holder
from core.session import Session, SessionError, State, load_bench
from unit.hil_fake import FakePort, firmware

BANNER = b"READY name=hil-bench fw=1.0.0 proto=1.0 build=abc1234 reset=PIN reset_flags=0x04000000\r\n"
OTHER_MAJOR = BANNER.replace(b"proto=1.0", b"proto=2.0")
EVENT_WAIT = 3.0  # Seconds a test waits for one event
LINUX = sys.platform.startswith("linux")
RX_CHECK = Path(__file__).resolve().parents[2] / "rx_check" / "uart_rx_check.py"

BENCH = load_bench()


# Fake bench

class Port(FakePort):
    """FakePort that remembers whether it was closed."""

    def __init__(self, responder=None):
        super().__init__(responder)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class Programmer:
    """Fake programmer: reset() queues the banner the board would send."""

    def __init__(self, port: Port, banner: bytes = BANNER, build: str | None = "abc1234"):
        self.port = port
        self.banner = banner
        self.build = build
        self.resets = 0
        self.failure = None  # ProgrammingFailure raised by the next reset

    def reset(self) -> None:
        self.resets += 1
        if self.failure is not None:
            raise self.failure
        self.port.incoming += self.banner

    def build_id(self) -> str | None:
        return self.build


class Rig:
    """A Session on the fake bench, with its events in a queue."""

    def __init__(self, responder=None, banner: bytes = BANNER, build: str | None = "abc1234"):
        bench = copy.deepcopy(BENCH)
        bench["delays"]["port_open_settle"] = 0.0
        bench["timeouts"]["startup"] = 0.5
        bench["timeouts"]["response"] = 0.3
        self.port = Port(responder or firmware())
        self.programmer = Programmer(self.port, banner, build)
        self.opens = 0
        self.open_error = None  # Exception raised by the next open
        self.events = queue.Queue()
        self.seen = []
        self.session = Session(bench, self.events.put, open_port=self._open, programmer=self.programmer)

    def _open(self, serial_config, timeout, name):
        if self.open_error is not None:
            raise self.open_error
        self.opens += 1
        self.port.closed = False
        return SerialAdapter(self.port, timeout)

    def wait(self, state: State, kind: str = "state"):
        """Next event of that kind in that state; earlier events are kept in seen."""
        deadline = time.monotonic() + EVENT_WAIT
        while True:
            try:
                event = self.events.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                pytest.fail(f"no {kind} event in {state.value}; seen: {[(e.kind, e.state.value) for e in self.seen]}")
            self.seen.append(event)
            if event.kind == kind and event.state is state:
                return event

    def connected(self):
        self.session.connect()
        return self.wait(State.CONNECTED)

    def kinds(self) -> list:
        return [event.kind for event in self.seen]

    def close(self) -> None:
        self.session.shutdown()


@pytest.fixture
def rig():
    bench = Rig()
    yield bench
    bench.close()


def make_rig(request, **kwargs) -> Rig:
    bench = Rig(**kwargs)
    request.addfinalizer(bench.close)
    return bench


# Connection

def test_connect(rig):
    event = rig.connected()
    assert event.data["names"] == ["HELLO", "CAPS"]
    assert event.data["banner"].build == "abc1234"
    assert rig.session.state is State.CONNECTED
    assert rig.session.names == ["HELLO", "CAPS"]
    assert rig.programmer.resets == 1
    assert rig.port.written == ["CMD id=1 command=HELLO", "CMD id=2 command=CAPS start=0"]
    assert "build_mismatch" not in rig.kinds()


def test_build_mismatch_does_not_block(request):
    bench = make_rig(request, build="def5678")
    bench.session.connect()
    event = bench.wait(State.CONNECTING, "build_mismatch")
    assert event.data == {"firmware": "abc1234", "local": "def5678"}
    bench.wait(State.CONNECTED)


def test_no_local_build_is_not_a_mismatch(request):
    bench = make_rig(request, build=None)
    bench.connected()
    assert "build_mismatch" not in bench.kinds()


@pytest.mark.parametrize("banner", [b"", OTHER_MAJOR], ids=["no_banner", "other_major"])
def test_unknown_image(request, banner):
    bench = make_rig(request, banner=banner)
    bench.session.connect()
    event = bench.wait(State.UNKNOWN_IMAGE)
    assert event.text.startswith("STARTUP_FAILURE" if not banner else "INCOMPATIBLE_PROTOCOL")
    assert not bench.port.closed  # Kept open: recover or a flash comes next


def test_recover_from_unknown_image(request):
    bench = make_rig(request, banner=b"")
    bench.session.connect()
    bench.wait(State.UNKNOWN_IMAGE)
    bench.programmer.banner = BANNER  # hil-bench flashed meanwhile
    bench.session.recover()
    bench.wait(State.CONNECTED)
    assert bench.opens == 1


def test_connect_twice_is_refused(rig):
    rig.connected()
    rig.session.connect()
    event = rig.wait(State.CONNECTED, "error")
    assert "already connected" in event.text
    assert rig.opens == 1 and rig.programmer.resets == 1


# Requests

def test_send_ok(rig):
    rig.connected()
    rig.session.send("HELLO")
    event = rig.wait(State.CONNECTED, "response")
    assert event.data["response"].ok
    assert event.text == "HELLO status=OK name=hil-bench proto=1.0 fw=1.0.0 build=abc1234"


def test_send_err_keeps_the_session(rig):
    rig.connected()
    rig.session.send("NO_SUCH", {"x": "1"})
    event = rig.wait(State.CONNECTED, "response")
    assert event.data["response"].code == "UNKNOWN_COMMAND"
    assert rig.port.written[-1] == "CMD id=3 command=NO_SUCH x=1"
    rig.session.send("HELLO")
    assert rig.wait(State.CONNECTED, "response").data["response"].ok


def _disconnected(bench: Rig) -> None:
    pass


def _running(bench: Rig) -> None:
    bench.connected()
    bench.session.release()
    bench.wait(State.RUNNING)


def _lost(bench: Rig) -> None:
    bench.connected()
    bench.port.incoming += BANNER
    bench.wait(State.SESSION_LOST)


@pytest.mark.parametrize("setup, state", [(_disconnected, State.DISCONNECTED), (_running, State.RUNNING),
                                          (_lost, State.SESSION_LOST)], ids=["disconnected", "running", "lost"])
def test_send_refused(rig, setup, state):
    setup(rig)
    written = len(rig.port.written)
    rig.session.send("HELLO")
    event = rig.wait(state, "error")
    assert event.text == f"HELLO not sent: session is {state.value}"
    assert len(rig.port.written) == written


# Lost session

def test_ready_while_idle(rig):
    rig.connected()
    rig.port.incoming += BANNER
    event = rig.wait(State.SESSION_LOST)
    assert event.text.startswith("UNEXPECTED_RESET: READY while idle")
    rig.session.recover()
    rig.wait(State.CONNECTED)
    assert rig.programmer.resets == 2


def test_unsolicited_line_while_idle(rig):
    rig.connected()
    rig.port.incoming += b"ERROR code=BAD_FRAME\r\n"
    event = rig.wait(State.CONNECTED, "unsolicited")
    assert event.text == "ERROR code=BAD_FRAME"


def test_ready_during_a_request(request):
    serve = firmware()
    bench = make_rig(request, responder=lambda line: BANNER if "LED_SET" in line else serve(line))
    bench.connected()
    bench.session.send("LED_SET", {"state": "toggle"})
    event = bench.wait(State.SESSION_LOST)
    assert event.text.startswith("LED_SET: UNEXPECTED_RESET")


def test_timeout_is_never_sent_again(rig):
    rig.connected()
    rig.port.responder = lambda line: b""
    rig.session.send("LED_SET", {"state": "toggle"})
    event = rig.wait(State.SESSION_LOST)
    assert "no END for id=3" in event.text
    rig.session.send("LED_SET", {"state": "toggle"})
    rig.wait(State.SESSION_LOST, "error")
    assert sum("LED_SET" in line for line in rig.port.written) == 1
    rig.port.responder = firmware()
    rig.session.recover()
    rig.wait(State.CONNECTED)
    assert sum("LED_SET" in line for line in rig.port.written) == 1


def test_recover_needs_a_lost_session(rig):
    rig.connected()
    rig.session.recover()
    event = rig.wait(State.CONNECTED, "error")
    assert event.text == "nothing to recover in state CONNECTED"
    assert rig.programmer.resets == 1


# Port and bench faults

def test_port_busy(rig):
    rig.open_error = PortBusy("/dev/ttyACM0", "miniterm (PID 42)")
    rig.session.connect()
    event = rig.wait(State.DISCONNECTED, "error")
    assert event.text == "/dev/ttyACM0 is busy: held by miniterm (PID 42)"
    assert rig.programmer.resets == 0


def test_no_port_at_open(rig):
    rig.open_error = OSError(2, "could not open port /dev/ttyACM0")
    rig.session.connect()
    event = rig.wait(State.DISCONNECTED, "error")
    assert event.text.startswith("port lost: ")
    rig.open_error = None
    rig.connected()


def test_port_lost_while_idle(rig):
    rig.connected()

    def unplugged(expected=b"\n"):
        raise OSError(5, "device disconnected")

    rig.port.read_until = unplugged
    event = rig.wait(State.DISCONNECTED, "error")
    assert event.text == "port lost: [Errno 5] device disconnected"
    assert rig.port.closed
    del rig.port.read_until  # Cable back
    rig.connected()
    assert rig.opens == 2


def test_reset_failure(rig):
    rig.programmer.failure = ProgrammingFailure("make reset failed (exit 2)")
    rig.session.connect()
    event = rig.wait(State.DISCONNECTED, "error")
    assert event.text == "reset failed: PROGRAMMING_FAILURE: make reset failed (exit 2)"
    assert rig.port.closed


def test_internal_error_keeps_the_thread(rig):
    rig.open_error = ValueError("bug")
    rig.session.connect()
    event = rig.wait(State.DISCONNECTED, "error")
    assert event.text == "internal error: ValueError('bug')"
    rig.open_error = None
    rig.connected()


def test_broken_listener_keeps_the_thread(request):
    bench = make_rig(request)
    received = bench.session.on_event

    def broken(event):
        received(event)
        raise RuntimeError("listener bug")

    bench.session.on_event = broken
    bench.connected()
    bench.session.send("HELLO")
    bench.wait(State.CONNECTED, "response")


# Port release

def test_disconnect_closes_without_reset(rig):
    rig.connected()
    rig.session.disconnect()
    rig.wait(State.DISCONNECTED)
    assert rig.port.closed
    assert rig.programmer.resets == 1
    assert rig.session.banner is None and rig.session.names == []


def test_release_then_connect(rig):
    rig.connected()
    rig.session.release()
    rig.wait(State.RUNNING)
    assert rig.port.closed
    rig.connected()
    assert rig.opens == 2


def test_shutdown_closes_the_port(rig):
    rig.connected()
    rig.session.shutdown()
    assert rig.port.closed
    assert not rig.session._thread.is_alive()


def test_bad_bench_config(tmp_path):
    path = tmp_path / "bench.yaml"
    path.write_text("schema_version: 2\n")
    with pytest.raises(SessionError, match="schema_version must be 1"):
        load_bench(path)


# Port lock on a real pty (E7, E8)

@pytest.fixture
def pty_path():
    master, slave = os.openpty()
    yield os.ttyname(slave)
    os.close(slave)
    os.close(master)


@pytest.fixture
def held_pty(pty_path):
    """A pty locked by a child process, as miniterm would hold the port."""
    child = subprocess.Popen(
        [sys.executable, "-c",
         "import serial, sys, time; s = serial.Serial(sys.argv[1], exclusive=True); print('held', flush=True); "
         "time.sleep(30)", pty_path],
        stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        yield pty_path, child.pid
    finally:
        child.kill()
        child.wait()


def _open(path):
    return SerialAdapter.open(BENCH["serial"], 0.5, path)


@pytest.mark.skipif(not LINUX, reason="pty and /proc/locks")
def test_second_open_in_this_process(pty_path):
    with _open(pty_path):
        with pytest.raises(PortBusy) as error:
            _open(pty_path)
    assert error.value.port == pty_path
    assert error.value.holder.endswith(f"(PID {os.getpid()})")
    with _open(pty_path):  # The lock went with the close
        pass


@pytest.mark.skipif(not LINUX, reason="pty and /proc/locks")
def test_port_held_by_another_process(held_pty):
    path, pid = held_pty
    with pytest.raises(PortBusy) as error:
        _open(path)
    assert error.value.holder.startswith(sys.executable)
    assert error.value.holder.endswith(f"(PID {pid})")
    assert str(error.value) == f"{path} is busy: held by {error.value.holder}"


@pytest.mark.skipif(not LINUX, reason="pty and /proc/locks")
def test_unlocked_port_has_no_holder(pty_path):
    assert port_holder(pty_path) is None


@pytest.mark.skipif(not LINUX, reason="pty and /proc/locks")
def test_rx_check_refuses_a_held_port(held_pty):
    path, pid = held_pty
    done = subprocess.run([sys.executable, str(RX_CHECK), path, "--only", "T1"],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 2
    assert f"Serial error: {path} is busy: held by " in done.stderr
    assert f"(PID {pid})" in done.stderr
    assert "PASS" not in done.stdout


# port_holder on fake /proc trees

@pytest.fixture
def proc_tree(tmp_path):
    """A locked file, its /proc/locks node, and an empty /proc."""
    target = tmp_path / "ttyFAKE"
    target.write_text("")
    info = os.stat(target)
    node = f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}"
    proc = tmp_path / "proc"
    proc.mkdir()
    return target, node, proc


def _holder(tree, lines, cmdlines=None):
    target, node, proc = tree
    locks = proc / "locks"
    locks.write_text("\n".join(line.format(node=node) for line in lines) + "\n")
    for pid, cmdline in (cmdlines or {}).items():
        (proc / pid).mkdir()
        (proc / pid / "cmdline").write_bytes(cmdline)
    return port_holder(str(target), str(locks), str(proc))


@pytest.mark.skipif(not LINUX, reason="os.major on st_dev")
def test_holder_found(proc_tree):
    lines = ["1: FLOCK  ADVISORY  WRITE 111 00:00:1 0 EOF",  # Another file
             "2: POSIX  ADVISORY  WRITE 222 {node} 0 EOF",  # Not a flock
             "3: -> FLOCK  ADVISORY  WRITE 444 {node} 0 EOF",  # A waiter
             "3: FLOCK  ADVISORY  WRITE 333 {node} 0 EOF"]
    holder = _holder(proc_tree, lines, {"333": b"python3\0-m\0serial.tools.miniterm\0"})
    assert holder == "python3 -m serial.tools.miniterm (PID 333)"


@pytest.mark.skipif(not LINUX, reason="os.major on st_dev")
def test_holder_long_command_is_cut(proc_tree):
    holder = _holder(proc_tree, ["1: FLOCK  ADVISORY  WRITE 333 {node} 0 EOF"], {"333": b"x" * 300})
    command = holder.removesuffix(" (PID 333)")
    assert len(command) == HOLDER_MAX_LEN and command.endswith("...")


@pytest.mark.skipif(not LINUX, reason="os.major on st_dev")
def test_holder_without_cmdline(proc_tree):
    assert _holder(proc_tree, ["1: FLOCK  ADVISORY  WRITE 333 {node} 0 EOF"]) == "PID 333"


@pytest.mark.skipif(not LINUX, reason="os.major on st_dev")
def test_holder_not_found(proc_tree):
    assert _holder(proc_tree, ["1: FLOCK  ADVISORY  WRITE 111 00:00:1 0 EOF"]) is None


def test_holder_without_locks_file(tmp_path):
    assert port_holder(str(tmp_path / "ttyFAKE"), str(tmp_path / "locks")) is None
