"""Board tests of the catalogue through the TUI (C1).

Needs the board with hil-bench flashed, and the port free (TUI, miniterm and
minicom closed). Runs only on request:

    python3 -m pytest tests/host/tui -m board -v

Each test starts the real HilApp headless with its real Session: real port,
make reset, banner, HELLO and CAPS. Commands go through the form, Send and the
confirmation, as an operator sends them. Every catalogue command is sent with
its default arguments and must answer status=OK; a command with a requires is
preceded by it. A destructive command is kept only when its default addresses
stay in the QSPI test area (cases/expected.py), otherwise the test fails
before sending; a rebooting command is skipped. A rejected case goes through
the free form and must leave the LED state unchanged.

Not tested here: flashing (an unknown image fails with the command to run),
the values read against the datasheets (tests/host/hil does it), and the
rendering in a real terminal.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import asyncio
import re

import pytest

pytest.importorskip("textual")

from textual.widgets import Checkbox, Input, OptionList, Static  # noqa: E402

from cases.expected import QSPI_TEST_END, QSPI_TEST_START  # noqa: E402
from core.catalog import EntryStatus, default_text, load  # noqa: E402
from core.session import State, load_bench  # noqa: E402
from ui.app import ConfirmScreen, HilApp  # noqa: E402

pytestmark = pytest.mark.board

CATALOG = load()
NAMES = CATALOG.names()
SIZE = (120, 36)
CONNECT_WAIT = 20.0  # Seconds for make reset, the banner, HELLO and CAPS
ANSWER_WAIT = 10.0  # Seconds for one answer; the firmware bounds each wait under 2 s
STEP = 0.05


def defaults(name: str) -> dict:
    command = CATALOG.commands[name]
    return CATALOG.check(name, {arg.name: default_text(arg) for arg in command.args if default_text(arg)})


def unsafe(name: str) -> list:
    """Default hex arguments of a destructive command that leave the QSPI test area."""
    command = CATALOG.commands[name]
    values = defaults(name)
    return [arg.name for arg in command.args
            if arg.type == "hex" and arg.name in values
            and not QSPI_TEST_START <= int(values[arg.name], 16) < QSPI_TEST_END]


# Driving the TUI

def text(app: HilApp, selector: str) -> str:
    return str(app.query_one(selector, Static).render())


async def wait_for(pilot, condition, what: str, timeout: float) -> None:
    for _ in range(int(timeout / STEP)):
        if condition():
            return
        await pilot.pause(STEP)
    pytest.fail(f"timed out waiting for {what}")


async def settle(pilot, app: HilApp) -> None:
    """Let the messages run and the form worker finish."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def connected(pilot, app: HilApp) -> None:
    """Wait for CONNECTED; an unknown image or a busy port fails with the message of the TUI."""

    def done():
        state = app.session.state
        if state in (State.UNKNOWN_IMAGE, State.SESSION_LOST):
            pytest.fail(f"{state.value}: {text(app, '#message')}")
        if state is State.DISCONNECTED and text(app, "#message").endswith("then Connect."):
            pytest.fail(f"not connected: {text(app, '#message')}")  # Busy or lost port, failed reset
        return state is State.CONNECTED and " CONNECTED " in text(app, "#status")

    await wait_for(pilot, done, "CONNECTED", CONNECT_WAIT)
    await settle(pilot, app)


async def select(pilot, app: HilApp, name: str) -> None:
    commands = app.query_one("#commands", OptionList)
    commands.highlighted = commands.get_option_index(name)
    await settle(pilot, app)


async def send(pilot, app: HilApp, name: str, free: str | None = None) -> str:
    """Send name from its form (or the free form), confirm if asked; the result text."""
    await select(pilot, app, name)
    if free is not None:
        app.query_one("#free", Checkbox).value = True
        await settle(pilot, app)
        app.query_one("#free-line", Input).value = free
    await pilot.click("#send")
    await pilot.pause()
    if CATALOG.commands[name].needs_confirmation:
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen), "the confirmation", ANSWER_WAIT)
        await pilot.click("#yes")
        await pilot.pause()
    await wait_for(pilot, lambda: app.pending is None, f"the answer to {name}", ANSWER_WAIT)
    await pilot.pause()
    if free is not None:
        app.query_one("#free", Checkbox).value = False
        await settle(pilot, app)
    return text(app, "#result")


def run(scenario) -> None:
    """Run the TUI on the real bench, wait for the session, then play the scenario."""

    async def main():
        app = HilApp(load_bench(), CATALOG)
        try:
            async with app.run_test(size=SIZE) as pilot:
                await connected(pilot, app)
                await scenario(pilot, app)
        finally:
            if app.session is not None:
                app.session.shutdown()  # Closes the port

    asyncio.run(main())


# Tests

def test_caps_matches_the_catalogue():
    """Same names on the board and in the catalogue, both ways: no free entry, no grey one."""

    async def scenario(pilot, app):
        pane = app.pane
        statuses = {name: entry.status for name, entry in pane.entries.items()}
        assert {name for name, status in statuses.items() if status is not EntryStatus.TYPED} == set()
        assert set(statuses) == set(NAMES)

    run(scenario)


@pytest.mark.parametrize("name", NAMES)
def test_command_with_defaults(name):
    command = CATALOG.commands[name]
    if command.effect == "reboots":
        pytest.skip(f"{name} reboots the board: excluded from the default-argument run")
    if command.effect == "destructive":
        outside = unsafe(name)
        assert not outside, f"{name}: default {outside} outside the QSPI test area, not sent"

    async def scenario(pilot, app):
        if command.requires is not None:
            result = await send(pilot, app, command.requires)
            assert re.search(r"status\s+OK", result), f"{command.requires}: {result}"
        result = await send(pilot, app, name)
        assert re.search(r"status\s+OK", result), f"{name} {defaults(name)}: {result}"
        assert app.session.state is State.CONNECTED

    run(scenario)


def test_rejected_value_leaves_the_led_unchanged():
    """C1 rejected case: the free form sends state=bad, the board answers INVALID_ARGUMENT."""

    async def scenario(pilot, app):
        before = re.search(r"state\s+(\w+)", await send(pilot, app, "LED_GET")).group(1)
        result = await send(pilot, app, "LED_SET", free="state=bad")
        assert re.search(r"status\s+ERR", result) and "INVALID_ARGUMENT" in result, result
        assert app.session.state is State.CONNECTED
        after = re.search(r"state\s+(\w+)", await send(pilot, app, "LED_GET")).group(1)
        assert after == before

    run(scenario)
