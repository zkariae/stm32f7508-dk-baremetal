"""Headless tests of the TUI home screen on the fake firmware (C1, C6).

No board. HilApp runs with App.run_test() and its real Session thread, on
the FakePort of tests/host/hil/unit/hil_fake.py and a fake programmer whose
reset queues a banner. The fake firmware answers HELLO and CAPS like
hil-bench and every other command with status=OK and its arguments echoed;
a value "bad" gets ERR INVALID_ARGUMENT, so a rejected case goes through the
real result view. The tests are synchronous and drive the pilot with
asyncio.run, so no async pytest plugin is needed. The fake firmware answers
at once, so its timeouts are only margins: wide enough that a loaded CI host
which pauses the session thread does not take a ready answer for a timeout.

Checked: the list follows CAPS and the catalogue, each catalogue command is
sent from its form with its default arguments, a typed error sends nothing,
the free form sends a rejected value, the confirmation of a command with an
effect, Send only in a session, a timeout and an unexpected reset lose the
session and Recover brings it back, a busy port names its holder, the keys
work from a field, Quit frees the port, and hil_tui.py stops on a bad bench
or catalogue.

Not tested here: the real port and board (E16), the make targets, and the
rendering in a real terminal (the VS Code key capture was checked by hand).

Version: 1.1
Date: 13/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
  1.1  13/11/2026  Wider timeouts of the fake bench and a longer wait: a loaded CI host missed the 0.3 s answer.
"""

import asyncio
import copy

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Checkbox, Input, OptionList, Static  # noqa: E402

import hil_tui  # noqa: E402
from adapters.serial_adapter import PortBusy, SerialAdapter  # noqa: E402
from core.catalog import default_text, load  # noqa: E402
from core.session import Session, State, load_bench  # noqa: E402
from ui.app import ConfirmScreen, HilApp  # noqa: E402
from ui.monitor import Monitor  # noqa: E402
from unit.hil_fake import FakePort  # noqa: E402

pytestmark = pytest.mark.ui

CATALOG = load()
NAMES = CATALOG.names()
BANNER = b"READY name=hil-bench fw=1.3.0 proto=1.3 build=abc1234 reset=PIN reset_flags=0x04000000\r\n"
SW_BANNER = BANNER.replace(b"reset=PIN reset_flags=0x04000000", b"reset=SW reset_flags=0x14000000")
CAPS_PAGE = 8  # Names per CAPS page, as hil-bench
HOLDER = "python3 -m serial.tools.miniterm (PID 42)"
SIZE = (120, 36)
WAIT = 6.0  # Seconds a test waits for a state, well above the response timeout
STEP = 0.05


# Fake bench

class Port(FakePort):
    """FakePort that remembers whether it was closed."""

    def __init__(self, responder):
        super().__init__(responder)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class Programmer:
    """Fake programmer: reset() queues the banner the board would send."""

    def __init__(self, port: Port):
        self.port = port

    def reset(self) -> None:
        self.port.incoming += BANNER

    def build_id(self) -> str:
        return "abc1234"


class Rig:
    """The fake bench behind one HilApp: firmware, port, programmer and port lock."""

    def __init__(self, caps: list = NAMES):
        self.bench = copy.deepcopy(load_bench())
        self.bench["delays"]["port_open_settle"] = 0.0
        self.bench["timeouts"]["startup"] = 2.0  # Margins only: the fake answers at once
        self.bench["timeouts"]["response"] = 1.0
        self.caps = caps
        self.silent = False  # The firmware stops answering
        self.holder = None  # Program that holds the port, or None
        self.port = Port(self.respond)

    def respond(self, line: str) -> bytes:
        if self.silent:
            return b""
        tokens = dict(token.split("=", 1) for token in line.split()[1:])
        request_id, command = tokens.pop("id"), tokens.pop("command")
        if command == "HELLO":
            body = "status=OK name=hil-bench proto=1.3 fw=1.3.0 build=abc1234"
        elif command == "CAPS":
            start = int(tokens.get("start", "0"))
            body = f"status=OK total={len(self.caps)} start={start} names={','.join(self.caps[start:start + CAPS_PAGE])}"
            if start + CAPS_PAGE < len(self.caps):
                body += f" next={start + CAPS_PAGE}"
        elif "bad" in tokens.values():
            body = "status=ERR code=INVALID_ARGUMENT"
        else:
            body = " ".join(["status=OK"] + [f"{key}={value}" for key, value in tokens.items()])
        return f"RESULT id={request_id} {body}\r\nEND id={request_id}\r\n".encode()

    def open(self, serial_config, timeout, name):
        if self.holder is not None:
            raise PortBusy(name, self.holder)
        self.port.closed = False
        return SerialAdapter(self.port, timeout)

    def session(self, bench, on_event, port=None) -> Session:
        return Session(bench, on_event, port=port, open_port=self.open, programmer=Programmer(self.port))

    def requests(self) -> list:
        """Requests written after HELLO and CAPS, without their id."""
        lines = [line.split(" ", 2)[2] for line in self.port.written if line.startswith("CMD ")]
        return [line for line in lines if line != "command=HELLO" and not line.startswith("command=CAPS ")]


def drive(rig: Rig, scenario, connected: bool = True) -> HilApp:
    """Run the application on the rig, wait for the session, then play the scenario."""

    async def main():
        app = HilApp(rig.bench, CATALOG, rig.session)
        try:
            async with app.run_test(size=SIZE) as pilot:
                if connected:
                    await until(pilot, app, State.CONNECTED)
                await scenario(pilot, app)
        finally:
            if app.session is not None:
                app.session.shutdown()  # Idempotent: the thread may already be gone
        return app

    return asyncio.run(main())


async def wait_for(pilot, condition, what: str) -> None:
    """Poll the UI until condition() holds; conditions, not fixed delays, keep a loaded CI stable."""
    for _ in range(int(WAIT / STEP)):
        if condition():
            return
        await pilot.pause(STEP)
    pytest.fail(f"timed out waiting for {what}")


async def until(pilot, app: HilApp, state: State) -> None:
    """The session reached state and the UI shows it (the badge is written by the event handler)."""
    await wait_for(pilot, lambda: app.session.state is state and f" {state.value} " in text(app, "#status"),
                   f"state {state.value}")
    await settle(pilot, app)


async def settle(pilot, app: HilApp) -> None:
    """Let the messages run and the form worker finish (CAPS highlights a command, then builds its form)."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def select(pilot, app: HilApp, name: str) -> None:
    commands = app.query_one("#commands", OptionList)
    commands.highlighted = commands.get_option_index(name)
    await settle(pilot, app)


async def send(pilot, confirm: bool | None = None) -> None:
    """Press Send, answer the confirmation when one is expected, wait for the answer if sent."""
    app = pilot.app
    await pilot.click("#send")
    await pilot.pause()
    if confirm is not None:
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen), "the confirmation")
        await pilot.click("#yes" if confirm else "#no")
        await pilot.pause()
    await wait_for(pilot, lambda: app.pending is None, "the answer")
    await pilot.pause()


def text(app: HilApp, selector: str) -> str:
    return str(app.query_one(selector, Static).render())


# List

def test_list_follows_caps_and_catalogue():
    rig = Rig(caps=[name for name in NAMES if name != "LCD_PIXEL"] + ["SELF_TEST"])

    async def scenario(pilot, app):
        commands = app.query_one("#commands", OptionList)
        for name in NAMES + ["SELF_TEST"]:
            commands.get_option(name)  # Raises if missing
        assert commands.get_option("LCD_PIXEL").disabled
        assert not commands.get_option("LED_SET").disabled
        assert "free" in str(commands.get_option("SELF_TEST").prompt)
        assert "not in this firmware" in str(commands.get_option("LCD_PIXEL").prompt)

    drive(rig, scenario)


# Send

@pytest.mark.parametrize("name", NAMES)
def test_send_with_defaults(name):
    """Each catalogue command goes out from its form with its default arguments."""
    rig = Rig()
    command = CATALOG.commands[name]
    expected = CATALOG.check(name, {arg.name: default_text(arg) for arg in command.args if default_text(arg)})

    async def scenario(pilot, app):
        await select(pilot, app, name)
        await send(pilot, confirm=True if command.needs_confirmation else None)
        line = " ".join([f"command={name}"] + [f"{key}={value}" for key, value in expected.items()])
        assert rig.port.written[-1].endswith(line)
        result = text(app, "#result")
        assert name in result and "status" in result and "OK" in result
        for key, value in expected.items():
            assert key in result and value in result

    drive(rig, scenario)


def test_typed_error_sends_nothing():
    rig = Rig()

    async def scenario(pilot, app):
        await select(pilot, app, "QSPI_READ")
        app.query_one("#arg-addr", Input).value = "00FF0000"  # No 0x prefix
        written = len(rig.port.written)
        await send(pilot)
        assert len(rig.port.written) == written
        assert "addr:" in text(app, "#err-addr")
        assert "Not sent" in text(app, "#form-error")

    drive(rig, scenario)


def test_free_form_sends_a_rejected_value():
    """C1 rejected case: the free form sends the value as typed, the ERR is shown."""
    rig = Rig()

    async def scenario(pilot, app):
        await select(pilot, app, "LED_SET")
        app.query_one("#free", Checkbox).value = True
        await settle(pilot, app)
        app.query_one("#free-line", Input).value = "state=bad"
        await send(pilot)
        assert rig.requests()[-1] == "command=LED_SET state=bad"
        result = text(app, "#result")
        assert "ERR" in result and "INVALID_ARGUMENT" in result

    drive(rig, scenario)


@pytest.mark.parametrize("answer", ["no", "escape", "enter"])
def test_confirmation_refused_sends_nothing(answer):
    rig = Rig()

    async def scenario(pilot, app):
        await select(pilot, app, "QSPI_ERASE")
        await pilot.click("#send")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen), "the confirmation")
        await pilot.pause()
        if answer == "no":
            await pilot.click("#no")
        else:
            await pilot.press(answer)  # The focus is on No
        await wait_for(pilot, lambda: not isinstance(app.screen, ConfirmScreen), "the confirmation to close")
        await pilot.pause(0.2)  # A wrong answer would have written by now
        assert rig.requests() == []
        await send(pilot, confirm=True)
        assert rig.requests() == ["command=QSPI_ERASE addr=0x00FF0000"]

    drive(rig, scenario)


def test_send_only_in_a_session():
    rig = Rig()

    async def scenario(pilot, app):
        assert not app.query_one("#send", Button).disabled
        await pilot.press("ctrl+b")
        await until(pilot, app, State.DISCONNECTED)
        assert app.query_one("#send", Button).disabled
        assert rig.port.closed

    drive(rig, scenario)


# Faults

def test_timeout_loses_the_session_and_recover():
    rig = Rig()

    async def scenario(pilot, app):
        await select(pilot, app, "LED_GET")
        rig.silent = True
        await send(pilot)
        await until(pilot, app, State.SESSION_LOST)
        assert "LED_GET" in text(app, "#result")
        assert "Press Recover" in text(app, "#message")
        assert app.query_one("#send", Button).disabled
        sent = rig.requests().count("command=LED_GET")
        rig.silent = False
        await pilot.press("ctrl+r")
        await until(pilot, app, State.CONNECTED)
        assert rig.requests().count("command=LED_GET") == sent  # Never sent again (section 8.3)

    drive(rig, scenario)


def test_unexpected_reset_shows_its_cause():
    rig = Rig()

    async def scenario(pilot, app):
        assert "reset=PIN (0x04000000)" in text(app, "#status")
        rig.port.incoming += SW_BANNER
        await until(pilot, app, State.SESSION_LOST)
        assert "unexpected reset=SW (0x14000000)" in text(app, "#status")
        await pilot.press("f7")
        await until(pilot, app, State.CONNECTED)
        assert "unexpected" not in text(app, "#status")

    drive(rig, scenario)


def test_busy_port_names_its_holder():
    rig = Rig()
    rig.holder = HOLDER

    async def scenario(pilot, app):
        await wait_for(pilot, lambda: "held by" in text(app, "#message"), "the busy port message")
        assert app.session.state is State.DISCONNECTED
        assert f"held by {HOLDER}" in text(app, "#message")
        rig.holder = None
        await pilot.press("ctrl+n")
        await until(pilot, app, State.CONNECTED)

    drive(rig, scenario, connected=False)


# Keys

def test_keys_work_from_a_field_and_quit_frees_the_port():
    rig = Rig()

    async def scenario(pilot, app):
        monitor = app.query_one(Monitor)
        await pilot.press("f2")
        await pilot.pause()
        assert not monitor.display
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert monitor.display
        await select(pilot, app, "QSPI_READ")
        app.query_one("#arg-addr", Input).focus()
        await pilot.press("ctrl+b")
        await until(pilot, app, State.DISCONNECTED)
        await pilot.press("ctrl+n")
        await until(pilot, app, State.CONNECTED)
        app.query_one("#arg-addr", Input).focus()
        await pilot.press("ctrl+l")
        await pilot.pause(0.3)

    app = drive(rig, scenario)
    assert app.return_code == 0
    assert rig.port.closed


# Entry point

def test_entry_point_bad_bench(capsys):
    assert hil_tui.main(["--bench", "/nonexistent/bench.yaml"]) == hil_tui.EXIT_USAGE
    error = capsys.readouterr().err
    assert error.startswith("hil_tui.py: ") and error.count("\n") == 1


def test_entry_point_bad_catalogue(tmp_path, capsys):
    bad = tmp_path / "commands.yaml"
    bad.write_text("schema_version: 1\ncommands: {}\n", encoding="utf-8")
    assert hil_tui.main(["--catalog", str(bad)]) == hil_tui.EXIT_USAGE
    error = capsys.readouterr().err
    assert "catalogue" in error and error.count("\n") == 1


def test_entry_point_passes_the_port(monkeypatch):
    seen = {}

    class FakeApp:
        def __init__(self, bench, catalog, port=None):
            seen.update(bench=bench, catalog=catalog, port=port)

        def run(self):
            seen["run"] = True

    monkeypatch.setattr("ui.app.HilApp", FakeApp)
    assert hil_tui.main(["--port", "/dev/ttyACM1"]) == 0
    assert seen["port"] == "/dev/ttyACM1" and seen["run"]
    assert set(seen["catalog"].names()) == set(NAMES)
