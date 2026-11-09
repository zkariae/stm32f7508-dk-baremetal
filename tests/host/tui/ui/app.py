"""Home screen of the TUI: the session, the command pane and the monitor.

HilApp owns one Session (core/session.py) and connects at launch, so the
board state is checked again each time the TUI starts (C6). A status bar
shows the session state, the port, the firmware identity and the reset cause
of the last start (a watchdog, brown-out or low-power reset in yellow); the
build is shown only when it differs from the local one. While the session is
lost, the bar shows the reset cause of the unexpected banner instead (a
software reset made elsewhere shows reset=SW). A message line gives each
fault its own text and the next step: a busy port names its holder, a lost
port asks for the cable, no banner asks to flash hil-bench, a lost session
asks for Recover, a build mismatch is shown and does not block.

The command pane posts Send; a command with an effect (destructive or
reboots) asks for confirmation first. The answer goes back to the form as a
result, or as a failure when the session was lost on that request.

The monitor is shown by default; F2 hides it and the command pane takes the
whole height. Each F key also has a ctrl key, since the VS Code terminal
keeps F5 and F6 for itself. Its handler stays attached, so lines keep arriving while it is
hidden. Quit detaches the handler and stops the session, which frees the
port. The session factory is a parameter, so tests run the application on
the fake firmware.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import time

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, Static

from adapters.board import parse_banner  # tests/host/hil is on the path once core.session is imported
from core.catalog import Catalog
from core.session import Session, State
from ui.commands_pane import CommandsPane
from ui.monitor import Monitor, MonitorHandler, MonitorLine, attach, detach

STATE_STYLES = {
    State.DISCONNECTED: "bold white on grey30",
    State.CONNECTING: "bold white on dodger_blue3",
    State.CONNECTED: "bold white on green4",
    State.RUNNING: "bold white on dodger_blue3",
    State.UNKNOWN_IMAGE: "bold black on yellow3",
    State.SESSION_LOST: "bold black on yellow3",
}
# Buttons usable in each state, as core/session.py accepts them
CONNECT_STATES = (State.DISCONNECTED, State.RUNNING, State.UNKNOWN_IMAGE, State.SESSION_LOST)
RECOVER_STATES = (State.UNKNOWN_IMAGE, State.SESSION_LOST)
ABNORMAL_RESETS = ("IWDG", "WWDG", "BOR", "LPWR")  # Never expected on the bench: shown in yellow


class ConfirmScreen(ModalScreen[bool]):
    """Yes or No before a command with an effect."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical { width: 64; height: auto; border: thick $warning; padding: 1 2; background: $surface; }
    ConfirmScreen Horizontal { height: auto; margin-top: 1; align-horizontal: right; }
    ConfirmScreen Button { margin-left: 2; }
    """
    BINDINGS = [("escape", "answer(False)", "No")]

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.question)
            with Horizontal():
                yield Button("No", id="no", variant="primary")
                yield Button("Yes", id="yes", variant="warning")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()  # The safe answer is the default

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, answer: bool) -> None:
        self.dismiss(answer)


class HilApp(App):
    """The HIL bench TUI."""

    TITLE = "HIL bench"
    CSS = """
    #status { height: 1; }
    #bar { height: auto; }
    #bar Button { margin-right: 1; }
    #message { width: 1fr; padding: 0 1; content-align: left middle; height: 1; }
    CommandsPane { height: 1fr; }
    Monitor { height: 40%; }
    """
    # The VS Code terminal keeps F5 (debug) and F6 (focus): each action also has a ctrl key no field uses
    BINDINGS = [
        Binding("f2,ctrl+t", "toggle_monitor", "Monitor", key_display="F2/^T"),
        Binding("f5,ctrl+n", "connect", "Connect", key_display="F5/^N"),
        Binding("f6,ctrl+g", "disconnect", "Disconnect", key_display="F6/^G"),
        Binding("f7,ctrl+r", "recover", "Recover", key_display="F7/^R"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, bench: dict, catalog: Catalog, session_factory=Session, port: str | None = None):
        super().__init__()
        self.bench = bench
        self.catalog = catalog
        self.session_factory = session_factory
        self.port = port or bench["serial"]["port"]
        self.session = None
        self.handler = None
        self.pending = None  # Command sent and not answered yet
        self.warning = ""  # Build mismatch of the current session, kept until the next connection
        self.unexpected = None  # Banner received after CONNECTED: the cause of a lost session

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        with Horizontal(id="bar"):
            yield Button("Connect", id="connect", compact=True)
            yield Button("Disconnect", id="disconnect", compact=True)
            yield Button("Recover", id="recover", compact=True)
            yield Static(id="message")
        yield CommandsPane(self.catalog)
        monitor = Monitor()
        monitor.border_title = "Monitor (F2/^T)"
        yield monitor
        yield Footer()

    def on_mount(self) -> None:
        self.monitor = self.query_one(Monitor)
        self.pane = self.query_one(CommandsPane)
        self.handler = MonitorHandler(lambda line: self.call_from_thread(self._monitor_line, line))
        attach(self.handler)
        self.session = self.session_factory(self.bench, self._from_session, port=self.port)
        self._refresh(State.DISCONNECTED)
        self.session.connect()  # The board state is checked at each launch

    def on_unmount(self) -> None:
        if self.handler is not None:
            detach(self.handler)
            self.handler = None

    def _monitor_line(self, line: MonitorLine) -> None:
        """A monitor line; a banner is kept to show the cause of an unexpected reset.

        Lines and session events reach the UI thread in the order they were made,
        so the CONNECTING and CONNECTED events clear the banner of a normal start.
        """
        self.monitor.add(line)
        if line.kind == "RX":
            banner = parse_banner(line.text)
            if banner is not None:
                self.unexpected = banner

    # Session events, called from the session thread

    def _from_session(self, event) -> None:
        try:
            self.call_from_thread(self._on_event, event)
        except RuntimeError:  # The application has already stopped
            pass

    def _on_event(self, event) -> None:
        kind = "WARN" if event.kind == "error" or event.state in RECOVER_STATES else "INFO"
        self.monitor.add(MonitorLine(time.time(), kind, f"session: {event.kind} {event.state.value} {event.text}"))
        if event.kind == "state" and event.state in (State.CONNECTING, State.CONNECTED):
            self.unexpected = None  # The banner of this start is expected
        if event.kind == "state" and event.state is State.CONNECTING:
            self.warning = ""
        if event.kind == "build_mismatch":
            self.warning = f"Build mismatch: {event.text} (not blocking)"
        if event.kind == "state" and event.state is State.CONNECTED:
            self.pane.set_caps(event.data["names"])
        if event.kind == "response":
            response = event.data["response"]
            self.pane.show_result(event.data["command"], response.status, response.fields, response.code)
            self.pending = None
        elif event.state is State.SESSION_LOST and self.pending and event.text.startswith(f"{self.pending}: "):
            self.pane.show_failure(self.pending, event.text.split(": ", 1)[1])
            self.pending = None
        self._refresh(event.state, self._message(event))

    @staticmethod
    def _message(event) -> tuple:
        """Message line of an event: (text, style), or None to keep the current one."""
        text = event.text
        if event.kind == "error" and event.state is State.DISCONNECTED:
            if " is busy: " in text:
                return f"{text}. Close it, then Connect.", "bold yellow"
            if text.startswith("port lost: "):
                return f"Port lost ({text[len('port lost: '):]}). Check the cable, then Connect.", "bold red"
            if text.startswith("reset failed: "):
                return f"{text}. Check the ST-LINK, then Connect.", "bold red"
            return text, "bold red"
        if event.kind == "error":
            return text, "yellow"
        if event.kind == "state":
            if event.state is State.UNKNOWN_IMAGE:
                return f"{text}. Flash hil-bench (make hil-bench-flash), then Recover.", "bold yellow"
            if event.state is State.SESSION_LOST:
                return f"{text}. Press Recover.", "bold yellow"
            if event.state is State.CONNECTING:
                return "Reset, banner, HELLO and CAPS...", ""
            if event.state is State.CONNECTED:
                return "Connected", "green"
            if event.state is State.DISCONNECTED:
                return "Disconnected: the board was not reset", ""
            if event.state is State.RUNNING:
                return "Port released for a run", ""
        return None

    def _refresh(self, state: State, message: tuple | None = None) -> None:
        """Status bar, message line, buttons and Send for a state."""
        banner = self.session.banner if self.session is not None else None
        status = Text.assemble((f" {state.value} ", STATE_STYLES[state]), f"  {self.port}")
        if banner is not None and state is State.CONNECTED:
            # Cause of the last start (section 4.1); the build only shows when it differs (warning)
            status.append(f"  {banner.name}  fw={banner.fw}  proto={banner.proto}  ")
            status.append(f"reset={banner.reset} (0x{banner.reset_flags:08X})",
                          style="bold yellow" if banner.reset in ABNORMAL_RESETS else "")
        elif self.unexpected is not None and state is State.SESSION_LOST:
            lost = self.unexpected
            status.append(f"  unexpected reset={lost.reset} (0x{lost.reset_flags:08X})", style="bold yellow")
        if self.warning:
            status.append(f"  {self.warning}", style="bold yellow")
        self.query_one("#status", Static).update(status)
        if message is not None:
            self.query_one("#message", Static).update(Text(*message))
        self.query_one("#connect", Button).disabled = state not in CONNECT_STATES
        self.query_one("#disconnect", Button).disabled = state is State.DISCONNECTED
        self.query_one("#recover", Button).disabled = state not in RECOVER_STATES
        self.pane.set_enabled(state is State.CONNECTED)

    # Commands

    def on_commands_pane_send(self, message: CommandsPane.Send) -> None:
        if message.effect:
            question = f"{message.name} is {message.effect}. Send it?"
            self.push_screen(ConfirmScreen(question),
                             lambda yes: self._send(message.name, message.args) if yes else None)
        else:
            self._send(message.name, message.args)

    def _send(self, name: str, args: dict) -> None:
        self.pending = name
        self.session.send(name, args)

    # Actions

    @on(Button.Pressed, "#connect")
    def action_connect(self) -> None:
        if self.session.state in CONNECT_STATES:
            self.session.connect()

    @on(Button.Pressed, "#disconnect")
    def action_disconnect(self) -> None:
        if self.session.state is not State.DISCONNECTED:
            self.session.disconnect()

    @on(Button.Pressed, "#recover")
    def action_recover(self) -> None:
        if self.session.state in RECOVER_STATES:
            self.session.recover()

    def action_toggle_monitor(self) -> None:
        """Show or hide the monitor; lines keep arriving while it is hidden."""
        self.monitor.display = not self.monitor.display

    async def action_quit(self) -> None:
        if self.handler is not None:
            detach(self.handler)
            self.handler = None
        self.session.shutdown()  # Closes the port
        self.exit()
