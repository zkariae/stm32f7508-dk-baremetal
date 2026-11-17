"""Tests pane of the TUI: what can run, the selection, and the run live (C2, C3).

The tree shows the three families of core/suites.py discover_all(): pytest
files and their tests, T1-T8, and the scenarios. A family that could not be
discovered shows its error in red; the others stay usable. Nothing is
written here about a test: every name comes from the discovery.

Space marks or unmarks the node under the cursor (a file or a family marks
all its tests); Enter opens or closes it. A run covers one family, so a mark
in another family clears the selection; one scenario at a time. The line
"Will run" gives the effective selection: for T1-T8 through rx_selection(),
so T7 brings T3 to T6; the whole pytest family is the whole suite
(everything), a whole file is passed as the file.

The pane runs nothing: Run, Stop and Refresh post TestsPane.Run,
TestsPane.Stop and TestsPane.Refresh, and the application wires them to the
runner (E24). It calls set_enabled() and set_running() for the buttons,
start_run() when a run starts, and show_event() on the UI thread for each
event of the run. The counters are counted here by core/runner.py Totals
from the events received, never read from the runner (C3). Each finished
test gets one result line (outcome, test, duration, message) and a mark in
the tree; a scenario node takes the worst outcome of its steps. Notes of the
runner (Stop deferred, Stop forced) show on the progress line, run_end
gives the verdict.

Not done here: the session, the runner, freeing the port and UNKNOWN_IMAGE
(app.py), the report (report.py).

Version: 1.0
Date: 10/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
"""

import time

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, RichLog, Static, Tree

from core.runner import Totals
from core.suites import SuitesError, rx_selection

FAMILY_TITLES = {"pytest": "pytest", "rx_check": "UART RX T1-T8", "scenario": "Scenarios"}
KIND_OF_PREFIX = {"rx:": "rx_check", "scenario:": "scenario"}  # Event nodeid prefixes; pytest has none
OUTCOME_STYLES = {"PASS": "bold green", "SKIPPED": "dim", "FUNCTIONAL_ERROR": "bold red"}  # Others: yellow
VERDICT_STYLES = {"PASS": "bold white on green4", "FAIL": "bold white on red3",
                  "BENCH ERROR": "bold black on yellow3", "INTERRUPTED": "bold black on yellow3"}
ERROR_MAX = 200  # Characters of a family error shown in the tree
RESULT_LINES = 5000  # Result lines kept: a full suite fits


def outcome_style(outcome: str) -> str:
    return OUTCOME_STYLES.get(outcome, "bold yellow")


def worst(current: str | None, new: str) -> str:
    """Outcome of a test over its phases or of a scenario over its steps: the first one not PASS wins."""
    if current is None or current == "PASS" or (current == "SKIPPED" and new not in ("PASS", "SKIPPED")):
        return new
    return current


def item_key(nodeid: str) -> tuple:
    """(kind, item id) of an event nodeid: rx:T3, scenario:<file>::stepN, or a pytest nodeid."""
    for prefix, kind in KIND_OF_PREFIX.items():
        if nodeid.startswith(prefix):
            return kind, nodeid[len(prefix):].split("::")[0]
    return "pytest", nodeid


class TestTree(Tree):
    """Tree of the families; space marks, enter opens."""

    BINDINGS = [Binding("space", "mark", "Mark", show=False)]

    class Marked(Message):
        def __init__(self, node):
            super().__init__()
            self.node = node

    def action_mark(self) -> None:
        if self.cursor_node is not None:
            self.post_message(self.Marked(self.cursor_node))


class TestsPane(Horizontal):
    """Test tree on the left; selection, progress, results and buttons on the right."""

    DEFAULT_CSS = """
    TestsPane { height: auto; min-height: 12; }
    TestsPane > TestTree { width: 2fr; border: round $primary; }
    TestsPane > Vertical { width: 3fr; border: round $primary; padding: 0 1; }
    TestsPane #selection { height: auto; max-height: 3; }
    TestsPane #progress { height: auto; border-top: solid $primary; }
    TestsPane #results { height: 1fr; border-top: solid $primary; }
    TestsPane #actions { height: auto; }
    TestsPane #actions Button { margin-right: 1; }
    """

    class Run(Message):
        """Run request: kind, selection for the runner, everything for the whole pytest suite."""

        def __init__(self, kind: str, selection: list, everything: bool):
            super().__init__()
            self.kind = kind
            self.selection = selection
            self.everything = everything

    class Stop(Message):
        """Stop request for the run in progress."""

    class Refresh(Message):
        """Discover the families again."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suites = {}  # Kind: Suite
        self.items = {}  # (kind, item id): Item
        self.nodes = {}  # (kind, item id): tree node of the item
        self.kind = None  # Family of the marks
        self.marked = set()  # Item ids marked in that family
        self.enabled = False
        self.running = False
        self.outcomes = {}  # (kind, item id): outcome of the last run
        self.totals = Totals()
        self._reset_run()

    def compose(self) -> ComposeResult:
        tree = TestTree("Tests", id="tree")
        tree.show_root = False
        tree.border_title = "Tests (space marks, enter opens)"
        yield tree
        with Vertical() as right:
            right.border_title = "Run"
            yield Static("", id="selection")
            yield Static("", id="progress")
            yield RichLog(max_lines=RESULT_LINES, markup=False, highlight=False, wrap=False, id="results")
            with Horizontal(id="actions"):
                yield Button("Run", id="run", variant="primary", disabled=True, compact=True)
                yield Button("Stop", id="stop", variant="error", disabled=True, compact=True)
                yield Button("Refresh", id="refresh", compact=True)

    def on_mount(self) -> None:
        self._show_selection()
        self._show_progress()

    # Called by the application

    def set_suites(self, suites: list) -> None:
        """Rebuild the tree from discover_all(); marks still present are kept."""
        self.suites = {suite.kind: suite for suite in suites}
        self.items = {(suite.kind, item.id): item for suite in suites for item in suite.items}
        self.nodes = {}
        tree = self.query_one("#tree", TestTree)
        tree.clear()
        for suite in suites:
            family = tree.root.add(Text(), data=("family", suite.kind, None), expand=True)
            groups = {}
            for item in suite.items:
                parent = family
                if suite.kind == "pytest":
                    if item.group not in groups:
                        groups[item.group] = family.add(Text(), data=("group", suite.kind, item.group))
                    parent = groups[item.group]
                self.nodes[(suite.kind, item.id)] = parent.add_leaf(Text(), data=("item", suite.kind, item.id))
            for error in suite.errors:
                text = error if len(error) <= ERROR_MAX else error[:ERROR_MAX - 3] + "..."
                family.add_leaf(Text(text, style="bold red"), data=("error", suite.kind, None))
        known = {item.id for item in self._items(self.kind)}
        self.marked &= known
        if not self.marked:
            self.kind = None
        self._relabel()
        self._show_selection()

    def set_enabled(self, enabled: bool) -> None:
        """Run is possible: the application decides (session, port)."""
        self.enabled = enabled
        self._update_buttons()

    def set_running(self, running: bool) -> None:
        self.running = running
        self._update_buttons()

    def start_run(self, kind: str, title: str) -> None:
        """A run starts: counters, results and the marks of the last run are cleared."""
        self.totals = Totals()
        self.outcomes = {key: value for key, value in self.outcomes.items() if key[0] != kind}
        self._reset_run()
        self.run_title = title
        self.query_one("#results", RichLog).clear()
        self._relabel()
        self._show_progress()

    def show_event(self, event: dict) -> None:
        """One event of the run, on the UI thread."""
        kind = event.get("event")
        self.totals.add(event)
        if kind == "collected":
            self.total = int(event.get("count", 0))
        elif kind == "test_start":
            self.current = event.get("nodeid")
            self.phases = {}
        elif kind == "report":
            nodeid = event.get("nodeid")
            state = self.phases.setdefault(nodeid, {"outcome": None, "duration": 0.0, "message": ""})
            state["outcome"] = worst(state["outcome"], event.get("hil_outcome", "BENCH_ERROR"))
            state["duration"] += float(event.get("duration") or 0.0)
            if event.get("message") and not state["message"]:
                state["message"] = event["message"]
        elif kind == "test_end":
            self._finish_test(event.get("nodeid"))
        elif kind == "log" and event.get("logger") == "tui.runner":
            self.note = event.get("text", "")
            self._result_line(Text(f"note  {self.note}", style="bold yellow"))
        elif kind == "run_end":
            self.verdict = event.get("verdict")
            self.current = None
        else:
            return
        self._show_progress()

    # Tree and selection

    def _items(self, kind: str | None) -> list:
        suite = self.suites.get(kind)
        return list(suite.items) if suite is not None else []

    def _node_items(self, node) -> list:
        level, kind, value = node.data
        if level == "family":
            return [item.id for item in self._items(kind)]
        if level == "group":
            return [item.id for item in self._items(kind) if item.group == value]
        if level == "item":
            return [value]
        return []

    @on(TestTree.Marked)
    def _marked(self, message: TestTree.Marked) -> None:
        if self.running or message.node.data is None:
            return
        _, kind, _ = message.node.data
        ids = self._node_items(message.node)
        if not ids:
            return
        if kind != self.kind:
            self.kind, self.marked = kind, set()
        if kind == "scenario":
            self.marked = set() if self.marked == set(ids) else set(ids[:1])
        elif set(ids) <= self.marked:
            self.marked -= set(ids)
        else:
            self.marked |= set(ids)
        if not self.marked:
            self.kind = None
        self._relabel()
        self._show_selection()

    def selection(self) -> tuple:
        """(kind, selection, everything, text) of the marks; selection [] when nothing is marked."""
        if not self.marked:
            return None, [], False, "nothing marked"
        items = self._items(self.kind)
        if self.kind == "pytest":
            if len(self.marked) == len(items):
                return "pytest", [], True, f"the whole pytest suite ({len(items)} tests)"
            selection, groups = [], {}
            for item in items:
                groups.setdefault(item.group, []).append(item.id)
            for group, ids in groups.items():
                chosen = [test_id for test_id in ids if test_id in self.marked]
                selection += [group] if len(chosen) == len(ids) else chosen
            return "pytest", selection, False, f"{len(self.marked)} pytest tests: " + " ".join(selection)
        if self.kind == "rx_check":
            try:
                ids = rx_selection([item.id for item in items if item.id in self.marked], self.suites["rx_check"])
            except SuitesError as error:
                return None, [], False, str(error)
            return "rx_check", ids, False, "UART RX " + " ".join(ids)
        chosen = next(item for item in items if item.id in self.marked)
        return "scenario", [chosen.id], False, f"scenario {chosen.title} ({chosen.id})"

    def _relabel(self) -> None:
        tree = self.query_one("#tree", TestTree)
        stack = list(tree.root.children)
        while stack:
            node = stack.pop()
            stack += list(node.children)
            if node.data is not None and node.data[0] != "error":
                node.set_label(self._label(node))

    def _label(self, node) -> Text:
        level, kind, value = node.data
        ids = self._node_items(node)
        chosen = sum(test_id in self.marked for test_id in ids) if kind == self.kind else 0
        box = "[x]" if ids and chosen == len(ids) else "[-]" if chosen else "[ ]"
        text = Text(f"{box} ", style="bold" if chosen else "dim")
        if level == "family":
            text.append(FAMILY_TITLES.get(kind, kind), style="bold")
            text.append(f"  {len(ids)}", style="dim")
        elif level == "group":
            text.append(value)
            text.append(f"  {len(ids)}", style="dim")
            failed = [self.outcomes[(kind, test_id)] for test_id in ids
                      if self.outcomes.get((kind, test_id), "PASS") not in ("PASS", "SKIPPED")]
            if failed:
                text.append(f"  {len(failed)} not passed", style="bold red")
        else:
            item = self.items.get((kind, value))
            text.append(value.partition("::")[2] or value if kind == "pytest" else value)
            if item is not None and kind != "pytest" and item.title:
                text.append(f"  {item.title}", style="dim")
            outcome = self.outcomes.get((kind, value))
            if outcome is not None:
                text.append(f"  {outcome}", style=outcome_style(outcome))
        return text

    def _show_selection(self) -> None:
        _, _, _, text = self.selection()
        self.query_one("#selection", Static).update(Text.assemble(("Will run  ", "bold"), text))
        self._update_buttons()

    # Run

    def _reset_run(self) -> None:
        self.run_title = ""
        self.total = 0
        self.done = 0
        self.current = None
        self.phases = {}
        self.note = ""
        self.verdict = None

    def _finish_test(self, nodeid: str | None) -> None:
        state = self.phases.pop(nodeid, None) if nodeid else None
        self.done += 1
        self.current = None
        if state is None or state["outcome"] is None:
            return  # Interrupted before its first report: not counted, as Totals does
        outcome = state["outcome"]
        key = item_key(nodeid)
        self.outcomes[key] = worst(self.outcomes.get(key), outcome) if key[0] == "scenario" else outcome
        line = Text(time.strftime("%H:%M:%S "), style="dim")
        line.append(f"{outcome:<17} ", style=outcome_style(outcome))
        line.append(nodeid)
        line.append(f"  {state['duration']:.2f} s", style="dim")
        if state["message"]:
            line.append(f"  {state['message']}", style="" if outcome == "PASS" else outcome_style(outcome))
        self._result_line(line)
        node = self.nodes.get(key)
        while node is not None and node.data is not None:  # The item, its file and its family only
            node.set_label(self._label(node))
            node = node.parent

    def _result_line(self, line: Text) -> None:
        self.query_one("#results", RichLog).write(line)

    def _show_progress(self) -> None:
        counts = self.totals.counts()
        text = Text()
        if self.verdict is not None:
            text.append(f" {self.verdict} ", style=VERDICT_STYLES.get(self.verdict, "bold"))
            text.append("  ")
        if self.run_title:
            text.append(self.run_title, style="bold")
            text.append(f"  {self.done}/{self.total}" if self.total else "", style="dim")
        text.append("\n")
        for key, style in (("tests", ""), ("passed", "green"), ("failed", "red"), ("errors", "yellow"),
                           ("skipped", "dim")):
            text.append(f"{key} ", style="dim")
            text.append(f"{counts[key]}  ", style=f"bold {style}".strip() if counts[key] else "")
        if self.current:
            text.append(f"\nnow  {self.current}", style="cyan")
        if self.note:
            text.append(f"\n{self.note}", style="bold yellow")
        self.query_one("#progress", Static).update(text)

    def _update_buttons(self) -> None:
        if not self.is_mounted:
            return
        kind = self.selection()[0]
        self.query_one("#run", Button).disabled = not self.enabled or self.running or kind is None
        self.query_one("#stop", Button).disabled = not self.running
        self.query_one("#refresh", Button).disabled = self.running

    @on(Button.Pressed, "#run")
    def _run(self) -> None:
        kind, selection, everything, _ = self.selection()
        if kind is not None and self.enabled and not self.running:
            self.post_message(self.Run(kind, selection, everything))

    @on(Button.Pressed, "#stop")
    def _stop(self) -> None:
        if self.running:
            self.post_message(self.Stop())

    @on(Button.Pressed, "#refresh")
    def _refresh(self) -> None:
        if not self.running:
            self.post_message(self.Refresh())
