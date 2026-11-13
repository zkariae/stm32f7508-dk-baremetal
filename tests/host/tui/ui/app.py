"""Home screen of the TUI: the session, the Commands and Tests tabs and the monitor.

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

The Tests tab (ui/tests_pane.py) is filled by core/suites.py discover_all()
in a thread, the first time it is shown and on Refresh. Its Run starts a
core/runner.py Run (C2):
  - pytest and T1-T8 open the port themselves: the session releases it
    first, and the run starts once the session is RUNNING (port closed);
  - a scenario runs in the open session, so it needs CONNECTED. Its requests
    go through Session.send: the scenario thread waits for the answer the UI
    thread hands over, and a lost session ends the scenario with the outcome
    of the session text. Its prompts use the Yes or No dialog.
Each event of the run reaches the tests pane and the monitor on the UI
thread: the runner dispatcher queues it, and every RUN_REFRESH the queue is
handed over with one screen update for all, so a full suite (up to 300
events per second) stays near 100 kB/s on the terminal (C6); a dialog holds
the display. The TX and RX lines of a run keep the time of their log record,
for the display delay (C3).
After a pytest run the TUI connects again, which shows the port is free.
After T1-T8 (uart-diag stays on the board) or a Stop forced during a flash,
the bar shows UNKNOWN_IMAGE and the TUI offers to flash hil-bench, then
connects. Quitting during a run asks first, stops the run (a flash still
ends first; a second Quit forces it) and waits for its end, so no process of
the group is left behind.

Export (C4) writes report.md and report.html of the last run in its folder
(core/report.py), in a thread. It is grey until a run ends, then active
whatever the verdict, INTERRUPTED after a Stop included, and grey again while
a run or an export is on its way. The report is written only on request; the
report of a run killed with the TUI is rebuilt on the command line.

The monitor is shown by default; F2 hides it and the tabs take the whole
height. Each F key also has a ctrl key, since the VS Code terminal keeps F5
and F6 for itself. Its handler stays attached, so lines keep arriving while
it is hidden. Quit detaches the handler and stops the session, which frees
the port. The session and run factories are parameters, so tests run the
application on the fake firmware and on fake runs.

The TUI opens with the dialog theme of ui/theme.py and its ANSI palette, so
the named colours of the panes stay readable on the grey. The Yes or No box
has no frame, the screen behind it turns dark blue and No keeps the focus.
The command palette (ctrl+p) still offers the Textual themes; a dark one
brings back the Textual palette, since ANSI replaces only the light one.

Version: 1.4
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
  1.1  09/11/2026  Disconnect on ctrl+b and quit on ctrl+l: the VS Code terminal keeps ctrl+g and ctrl+q.
  1.2  10/11/2026  Tests tab: run pytest, T1-T8 and the scenarios with live display, the board state after.
  1.3  11/11/2026  Export the report of the last run, in a worker, from the Export button, F4 or ctrl+y.
  1.4  11/11/2026  Open with the dialog theme and its ANSI palette; dialog-style Yes or No box.
"""

import collections
import re
import threading
import time
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, Static, TabbedContent, TabPane

from adapters.board import parse_banner  # tests/host/hil is on the path once core.session is imported
from adapters.outcomes import HilOutcome
from core import report
from core.catalog import Catalog
from core.runner import RESULTS, Run
from core.scenario import ScenarioError, load as load_scenario
from core.session import Session, State
from core.suites import SCENARIOS_DIR, discover_all
from ui import theme
from ui.commands_pane import CommandsPane
from ui.monitor import DIRECTIONS, Monitor, MonitorHandler, MonitorLine, attach, detach
from ui.tests_pane import TestsPane

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
COLLECT_DIR = RESULTS / ".tui-collect"  # Collection files of the discovery, apart from the run folders
OUTCOME_NAME = re.compile(r"[A-Z_]+")
TAB_COMMANDS, TAB_TESTS = "tab-commands", "tab-tests"
RUN_TITLES = {"pytest": "pytest", "rx_check": "UART RX", "scenario": "Scenario"}
RUN_REFRESH = 0.2  # Seconds between two screen updates of a run, whatever its event rate
RUN_BATCH = 2000  # Events handed over per update at most, so a backlog never blocks the UI


class ConfirmScreen(ModalScreen[bool]):
    """Yes or No before a command with an effect, or for a scenario prompt."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; background: #000080 70%; }
    ConfirmScreen > Vertical { width: 64; height: auto; padding: 1 2; background: $surface; }
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
                yield Button("< No >", id="no", variant="primary")
                yield Button("< Yes >", id="yes")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()  # The safe answer is the default

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, answer: bool) -> None:
        self.dismiss(answer)


class SessionLost(HilOutcome):
    """A scenario request lost with the session; the outcome is read from the session text."""

    def __init__(self, text: str):
        _, _, rest = text.partition(": ")  # "<command>: <outcome>: <detail>"
        head, _, detail = rest.partition(": ")
        if OUTCOME_NAME.fullmatch(head):
            self.outcome = head
        else:
            self.outcome, detail = "PROTOCOL_FAILURE", rest or text
        super().__init__(detail)


class ScenarioLink:
    """Requests and prompts of a scenario thread, answered on the UI thread."""

    def __init__(self, app, timeout: float):
        self.app = app
        self.timeout = timeout
        self.waiting = None  # Command waiting for its answer
        self._answer = None
        self._done = threading.Event()
        self.cancelled = False

    def request(self, name: str, args: dict):
        self._answer, self.waiting = None, name
        self._done.clear()
        self.app.call_from_thread(self.app.scenario_send, name, args)
        if not self._done.wait(self.timeout):
            self.waiting = None
            raise SessionLost(f"{name}: PROTOCOL_FAILURE: no answer within {self.timeout:.0f} s")
        self.waiting = None
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer

    def answer(self, value) -> None:
        """A Response, or the exception that ends the scenario."""
        if self.waiting is not None:
            self._answer = value
            self._done.set()

    def ask(self, text: str) -> bool:
        box, done = {}, threading.Event()

        def answered(yes):
            box["yes"] = bool(yes)
            done.set()

        self.app.call_from_thread(self.app.show_prompt, text, answered)
        while not done.wait(0.1):
            if self.cancelled:
                return False
        return box.get("yes", False)

    def cancel(self) -> None:
        self.cancelled = True
        self.answer(RuntimeError("the TUI is quitting"))


class HilApp(App):
    """The HIL bench TUI."""

    TITLE = "HIL bench"
    CSS = """
    #status { height: 1; }
    #bar { height: auto; }
    #bar Button { margin-right: 1; }
    #message { width: 1fr; padding: 0 1; content-align: left middle; height: 1; }
    #tabs { height: 1fr; }
    #tabs TabPane { padding: 0; }
    CommandsPane, TestsPane { height: 1fr; }
    Monitor { height: 40%; }
    /* Textual greys an inactive tab at 50% and a group title of the command list at 38%: 3.5:1 and 2.6:1 on the
       grey of the theme; 75% keeps them apart from the active tab and the commands, above 4.5:1 */
    #tabs Tab { color: $foreground 75%; }
    #commands > .option-list--option-disabled { color: $foreground 75%; }
    """
    # The VS Code terminal keeps F5 (debug), F6 (focus), ctrl+g (go to line) and ctrl+q (quit):
    # each action also has a ctrl key that reaches the application there and that no field uses
    BINDINGS = [
        Binding("f2,ctrl+t", "toggle_monitor", "Monitor", key_display="F2/^T"),
        Binding("f3,ctrl+o", "switch_tab", "Tab", key_display="F3/^O"),
        Binding("f4,ctrl+y", "export", "Export", key_display="F4/^Y"),
        Binding("f5,ctrl+n", "connect", "Connect", key_display="F5/^N"),
        Binding("f6,ctrl+b", "disconnect", "Disconnect", key_display="F6/^B"),
        Binding("f7,ctrl+r", "recover", "Recover", key_display="F7/^R"),
        Binding("ctrl+q,ctrl+l", "quit", "Quit", key_display="^Q/^L", priority=True),
    ]

    def __init__(self, bench: dict, catalog: Catalog, session_factory=Session, port: str | None = None,
                 run_factory=Run, scenarios_dir=SCENARIOS_DIR, discover=discover_all):
        super().__init__()
        self.bench = bench
        self.catalog = catalog
        self.session_factory = session_factory
        self.run_factory = run_factory
        self.scenarios_dir = scenarios_dir
        self.discover = discover
        self.port = port or bench["serial"]["port"]
        self.session = None
        self.handler = None
        self.pending = None  # Command sent and not answered yet
        self.warning = ""  # Build mismatch of the current session, kept until the next connection
        self.unexpected = None  # Banner received after CONNECTED: the cause of a lost session
        self.active_run = None  # Run in progress
        self.pending_run = None  # pytest or T1-T8 run waiting for the port to be released
        self.link = None  # ScenarioLink of the scenario in progress
        self.image_unknown = ""  # Why the board image is unknown after a run, until the next connection
        self.flashing = False  # hil-bench flashed by the TUI after a run
        self.quitting = False
        self.discovered = False
        self.run_events = collections.deque()  # Run events waiting for the next refresh
        self.last_folder = None  # Folder of the last finished run: what Export writes the report of
        self.exporting = False

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        with Horizontal(id="bar"):
            yield Button("Connect", id="connect", compact=True)
            yield Button("Disconnect", id="disconnect", compact=True)
            yield Button("Recover", id="recover", compact=True)
            yield Button("Export", id="export", compact=True)
            yield Static(id="message")
        with TabbedContent(id="tabs"):
            with TabPane("Commands", id=TAB_COMMANDS):
                yield CommandsPane(self.catalog)
            with TabPane("Tests", id=TAB_TESTS):
                yield TestsPane()
        monitor = Monitor()
        monitor.border_title = "Monitor (F2/^T)"
        yield monitor
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(theme.HIL_DIALOG)
        self.ansi_theme_light = theme.ANSI  # Before the theme: Textual reads the palette when the theme changes
        self.theme = theme.NAME
        self.monitor = self.query_one(Monitor)
        self.pane = self.query_one(CommandsPane)
        self.tests = self.query_one(TestsPane)
        self.handler = MonitorHandler(lambda line: self.call_from_thread(self._monitor_line, line))
        attach(self.handler)
        self.session = self.session_factory(self.bench, self._from_session, port=self.port)
        self._refresh(State.DISCONNECTED)
        self.set_interval(RUN_REFRESH, self._drain_run_events)
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

    @property
    def busy(self) -> bool:
        """A run, a run waiting for the port, or a flash of hil-bench is in progress."""
        return self.active_run is not None or self.pending_run is not None or self.flashing

    @property
    def can_export(self) -> bool:
        """A run has ended, no other one is on its way and no export is being written (C4)."""
        return (self.last_folder is not None and self.active_run is None and self.pending_run is None
                and not self.exporting)

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
            self.image_unknown = ""
        if event.kind == "build_mismatch":
            self.warning = f"Build mismatch: {event.text} (not blocking)"
        if event.kind == "state" and event.state is State.CONNECTED:
            self.pane.set_caps(event.data["names"])
        if self.link is not None and self.link.waiting is not None:
            self._to_scenario(event)
        elif event.kind == "response":
            response = event.data["response"]
            self.pane.show_result(event.data["command"], response.status, response.fields, response.code)
            self.pending = None
        elif event.state is State.SESSION_LOST and self.pending and event.text.startswith(f"{self.pending}: "):
            self.pane.show_failure(self.pending, event.text.split(": ", 1)[1])
            self.pending = None
        self._refresh(event.state, self._message(event))
        if event.kind == "state" and event.state is State.RUNNING and self.pending_run is not None:
            self._start_pending_run()  # The port is closed now

    def _to_scenario(self, event) -> None:
        """Answer of the request a scenario waits for."""
        if event.kind == "response":
            self.link.answer(event.data["response"])
        elif event.kind == "state" and event.state is State.SESSION_LOST:
            self.link.answer(SessionLost(event.text))
        elif event.kind == "error" or (event.kind == "state" and event.state is not State.CONNECTED):
            self.link.answer(RuntimeError(event.text or f"session is {event.state.value}"))

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
        shown = State.UNKNOWN_IMAGE if self.image_unknown and state is State.RUNNING else state
        status = Text.assemble((f" {shown.value} ", STATE_STYLES[shown]), f"  {self.port}")
        if banner is not None and state is State.CONNECTED:
            # Cause of the last start (section 4.1); the build only shows when it differs (warning)
            status.append(f"  {banner.name}  fw={banner.fw}  proto={banner.proto}  ")
            status.append(f"reset={banner.reset} (0x{banner.reset_flags:08X})",
                          style="bold yellow" if banner.reset in ABNORMAL_RESETS else "")
        elif self.unexpected is not None and state is State.SESSION_LOST:
            lost = self.unexpected
            status.append(f"  unexpected reset={lost.reset} (0x{lost.reset_flags:08X})", style="bold yellow")
        elif shown is not state:
            status.append(f"  {self.image_unknown}", style="bold yellow")
        if self.warning:
            status.append(f"  {self.warning}", style="bold yellow")
        self.query_one("#status", Static).update(status)
        if message is not None:
            self.query_one("#message", Static).update(Text.assemble(message))  # A span: the theme palette applies
        busy = self.busy
        self.query_one("#connect", Button).disabled = busy or state not in CONNECT_STATES
        self.query_one("#disconnect", Button).disabled = busy or state in (State.DISCONNECTED, State.RUNNING)
        self.query_one("#recover", Button).disabled = busy or state not in RECOVER_STATES
        self.query_one("#export", Button).disabled = not self.can_export
        self.pane.set_enabled(state is State.CONNECTED and not busy)
        self.tests.set_enabled(not busy and state is not State.CONNECTING and not self.quitting)

    def _say(self, text: str, style: str = "") -> None:
        self._refresh(self.session.state, (text, style))

    # Commands

    def on_commands_pane_send(self, message: CommandsPane.Send) -> None:
        if message.effect:
            question = f"{message.name} is {message.effect}. Send it?"
            self.push_screen(ConfirmScreen(question),
                             lambda yes: self._send(message.name, message.args) if yes else None)
        else:
            self._send(message.name, message.args)

    def _send(self, name: str, args: dict) -> None:
        if self.busy:
            return
        self.pending = name
        self.session.send(name, args)

    def show_prompt(self, text: str, answered) -> None:
        """A scenario prompt: the steps already done are shown first, the dialog then holds the display."""
        self._drain_run_events()
        self.push_screen(ConfirmScreen(text), answered)

    def scenario_send(self, name: str, args: dict) -> None:
        """A request of the scenario thread, on the UI thread."""
        if self.session.state is not State.CONNECTED:
            self.link.answer(RuntimeError(f"{name} not sent: session is {self.session.state.value}"))
            return
        self.session.send(name, args)

    # Tests tab

    @on(TabbedContent.TabActivated, "#tabs")
    def _tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == TAB_TESTS and not self.discovered:
            self._discover()

    def on_tests_pane_refresh(self, message: TestsPane.Refresh) -> None:
        self._discover()

    def _discover(self) -> None:
        self.discovered = True
        self._say("Discovering the tests...")
        self.run_worker(self._discover_job, thread=True, exclusive=True, group="discover")

    def _discover_job(self) -> None:
        suites = self.discover(self.catalog, COLLECT_DIR, folder=self.scenarios_dir)
        self.call_from_thread(self._discovered, suites)

    def _discovered(self, suites: list) -> None:
        self.tests.set_suites(suites)
        errors = sum(len(suite.errors) for suite in suites)
        count = sum(len(suite.items) for suite in suites)
        self._say(f"{count} tests found" + (f", {errors} discovery errors" if errors else ""),
                  "yellow" if errors else "")

    def on_tests_pane_run(self, message: TestsPane.Run) -> None:
        if self.busy or self.quitting:
            return
        title = f"{RUN_TITLES[message.kind]}: " + (" ".join(message.selection) or "whole suite")
        if message.kind == "scenario":
            self._start_scenario(message.selection[0], title)
            return
        self.pending_run = (message.kind, list(message.selection), message.everything, title)
        self._say("Releasing the port for the run...")
        self.session.release()  # The run starts on the RUNNING event: the port is closed then

    def _start_scenario(self, name: str, title: str) -> None:
        if self.session.state is not State.CONNECTED:
            self._say("A scenario runs in the open session: Connect first", "bold yellow")
            return
        try:
            scenario = load_scenario(self.scenarios_dir / name, self.catalog)
        except ScenarioError as error:
            self._say(str(error), "bold red")
            return
        timeout = 3 * float(self.bench["timeouts"]["response"]) + 5.0
        self.link = ScenarioLink(self, timeout)
        self._start_run(lambda on_event: self.run_factory("scenario", on_event=on_event, scenario=scenario,
                                                          request=self.link.request, ask=self.link.ask),
                        "scenario", title)

    def _start_pending_run(self) -> None:
        kind, selection, everything, title = self.pending_run
        self.pending_run = None
        self._start_run(lambda on_event: self.run_factory(kind, selection, on_event, everything=everything),
                        kind, title)

    def _start_run(self, build, kind: str, title: str) -> None:
        try:
            self.active_run = build(self._from_run)
            self.tests.start_run(kind, title)
            self.tests.set_running(True)
            self.active_run.start()
        except Exception as error:  # The run could not start: the bench comes back
            self.active_run, self.link = None, None
            self.tests.set_running(False)
            self._say(f"run not started: {error}", "bold red")
            if kind != "scenario":
                self.session.connect()
            return
        self._say(f"Running {title}  ({self.active_run.folder.name})")

    def on_tests_pane_stop(self, message: TestsPane.Stop) -> None:
        if self.active_run is not None:
            self.active_run.stop()

    def _from_run(self, event: dict) -> None:
        """An event of the run, from the runner dispatcher thread: queued for the next refresh."""
        self.run_events.append(event)

    def _drain_run_events(self) -> None:
        """Every RUN_REFRESH on the UI thread: hand the queued events over, one screen update for all.

        A full suite sends up to 300 events per second; one update per event wrote
        up to 600 kB/s to the terminal and froze the VS Code terminal (C6). While a
        dialog is open the events wait: each update would redraw the whole screen
        under it. A scenario waits for its prompt anyway, and the flash question
        comes after the run.
        """
        if isinstance(self.screen, ConfirmScreen):
            return
        for _ in range(min(len(self.run_events), RUN_BATCH)):
            self._run_event(self.run_events.popleft())

    def _run_event(self, event: dict) -> None:
        self.tests.show_event(event)
        kind = event.get("event")
        if kind == "log":
            self.monitor.add(self._run_line(event))
        elif kind == "run_end":
            self._run_over(event)

    @staticmethod
    def _run_line(event: dict) -> MonitorLine:
        """Monitor line of a run log event, with the time of its record."""
        text, logger = str(event.get("text", "")), str(event.get("logger", ""))
        head, _, rest = text.partition("  ")
        if head in DIRECTIONS and rest:
            return MonitorLine(event.get("t", time.time()), head, rest)
        level = event.get("level", "INFO")
        kind = "ERROR" if level in ("ERROR", "CRITICAL") else "WARN" if level == "WARNING" else "INFO"
        return MonitorLine(event.get("t", time.time()), kind, f"{logger.rpartition('.')[2]}: {text}")

    def _run_over(self, event: dict) -> None:
        run, self.active_run, self.link = self.active_run, None, None
        self.tests.set_running(False)
        verdict = event.get("verdict")
        folder = event.get("folder") or (run.folder if run is not None else None)
        if folder:
            self.last_folder = Path(folder)  # Export is active whatever the verdict, INTERRUPTED included
        if self.quitting:
            self._leave()
            return
        if run is None or run.kind == "scenario":
            self._say(f"Scenario {verdict}", "green" if verdict == "PASS" else "bold yellow")
            return
        if run.forced:
            self.image_unknown = "image unknown: Stop forced during the flash"
        elif run.kind == "rx_check":
            self.image_unknown = "uart-diag left on the board by T1-T8"
        if not self.image_unknown:
            self._say(f"Run {verdict}: connecting again")
            self.session.connect()
            return
        self._say(f"Run {verdict}: {self.image_unknown}", "bold yellow")
        self.push_screen(ConfirmScreen(f"{self.image_unknown}. Flash hil-bench now?"), self._flash_answer)

    def _flash_answer(self, yes: bool) -> None:
        if not yes:
            self._say(f"{self.image_unknown}: flash hil-bench (make hil-bench-flash), then Connect", "bold yellow")
            return
        self.flashing = True
        self._say("Flashing hil-bench...")
        self.run_worker(self._flash_job, thread=True, exclusive=True, group="flash")

    def _flash_job(self) -> None:
        try:
            self.session.programmer.flash()
            error = None
        except Exception as failure:  # ProgrammingFailure, make missing
            error = str(failure)
        self.call_from_thread(self._flashed, error)

    def _flashed(self, error: str | None) -> None:
        self.flashing = False
        if error is not None:
            self._say(f"{error}. Check the ST-LINK, then flash hil-bench by hand", "bold red")
            return
        self.session.connect()

    # Actions

    @on(Button.Pressed, "#connect")
    def action_connect(self) -> None:
        if not self.busy and self.session.state in CONNECT_STATES:
            self.session.connect()

    @on(Button.Pressed, "#disconnect")
    def action_disconnect(self) -> None:
        if not self.busy and self.session.state not in (State.DISCONNECTED, State.RUNNING):
            self.session.disconnect()

    @on(Button.Pressed, "#recover")
    def action_recover(self) -> None:
        if not self.busy and self.session.state in RECOVER_STATES:
            self.session.recover()

    @on(Button.Pressed, "#export")
    def action_export(self) -> None:
        """Write report.md and report.html of the last run, in a thread: a full suite takes a moment (C6)."""
        if not self.can_export:
            return
        self.exporting = True
        self._say(f"Writing the report of {self.last_folder.name}...")
        self.run_worker(lambda: self._export_job(self.last_folder), thread=True, exclusive=True, group="export")

    def _export_job(self, folder: Path) -> None:
        try:
            markdown, _ = report.export(folder)
            error = None
        except Exception as failure:  # ReportError, OSError: the folder was removed or is not writable
            markdown, error = None, str(failure)
        try:
            self.call_from_thread(self._exported, folder, markdown, error)
        except RuntimeError:  # The application has already stopped
            pass

    def _exported(self, folder: Path, markdown: Path | None, error: str | None) -> None:
        self.exporting = False
        if error is not None:
            self._say(f"Report not written: {error}", "bold red")
        else:
            self._say(f"Report written: {markdown.parent}/report.md and report.html", "green")

    def action_toggle_monitor(self) -> None:
        """Show or hide the monitor; lines keep arriving while it is hidden."""
        self.monitor.display = not self.monitor.display

    def action_switch_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = TAB_TESTS if tabs.active == TAB_COMMANDS else TAB_COMMANDS

    async def action_quit(self) -> None:
        if self.active_run is None:
            self._leave()
        elif self.quitting:
            self.active_run.stop()  # Second Quit: a deferred Stop is forced
        else:
            self.push_screen(ConfirmScreen("A run is in progress. Stop it and quit?"), self._quit_answer)

    def _quit_answer(self, yes: bool) -> None:
        if not yes or self.active_run is None:
            return
        self.quitting = True
        if self.link is not None:
            self.link.cancel()
        self.active_run.stop()
        self._say("Stopping the run before quitting (Quit again forces it during a flash)...", "bold yellow")

    def _leave(self) -> None:
        if self.handler is not None:
            detach(self.handler)
            self.handler = None
        self.session.shutdown()  # Closes the port
        self.exit()
