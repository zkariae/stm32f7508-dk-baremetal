"""Discovery of what the TUI can run: pytest tests, T1-T8 and scenarios (C2, C5).

Nothing is written in the TUI: each family is read again at each discovery,
so a new test, a new T entry or a new scenario file shows up without any
change in tests/host/tui/ (C5).

  - pytest: tests/host/hil is collected in a subprocess with the hil_events
    plugin (plugins/hil_events.py); the tests come from its collected event,
    grouped by file. The collection has its own --log-file, since a
    collection would otherwise overwrite pytest.log (README.md section 3). It
    does not touch the board.
  - rx_check: the entries of tests/host/rx_check/plans/uart_rx.yaml.
    uart_rx_check.py refuses a test whose after entries do not run before it
    in the same run, so rx_selection() adds them, in plan order (T7 needs T3
    to T6).
  - scenario: the YAML files of tests/host/tui/scenarios, through
    core/scenario.py; a bad file is an error of the family, the others stay.

discover_all() keeps a failure inside its family: with pytest broken, T1-T8
and the scenarios are still offered.

Not done here: building the run commands and running them (runner.py), and
the display (tests_pane.py). No Textual import.

Version: 1.0
Date: 10/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core import scenario as scenarios
from core.catalog import Catalog

TUI_DIR = Path(__file__).resolve().parents[1]
REPO = TUI_DIR.parents[2]
HIL_DIR = REPO / "tests" / "host" / "hil"
PLUGINS_DIR = TUI_DIR / "plugins"
RX_PLAN = REPO / "tests" / "host" / "rx_check" / "plans" / "uart_rx.yaml"
SCENARIOS_DIR = TUI_DIR / "scenarios"
COLLECT_TIMEOUT = 60.0  # Seconds; a collection takes about one second
ERROR_LINES = 5  # Last stderr lines kept in a collection error
EXIT_NO_TESTS = 5  # pytest: nothing collected, not an error


class SuitesError(Exception):
    """A family that cannot be discovered, or a selection that cannot run."""


@dataclass(frozen=True)
class Item:
    """One selectable test: a pytest nodeid, a T id or a scenario file name."""

    id: str
    title: str
    group: str
    after: tuple = ()  # rx_check: tests that must run before it


@dataclass
class Suite:
    kind: str  # pytest, rx_check or scenario
    name: str
    items: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# pytest

def discover_pytest(work_dir: Path | str, tests: Path | str = HIL_DIR, timeout: float = COLLECT_TIMEOUT) -> Suite:
    """Collect tests (tests/host/hil) in a subprocess; SuitesError if the collection fails."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    events, log = work_dir / "collect.jsonl", work_dir / "collect.log"
    events.unlink(missing_ok=True)  # A stale stream must not pass for this collection
    command = [sys.executable, "-m", "pytest", str(tests), "--collect-only", "-q", "-p", "no:cacheprovider",
               "-p", "hil_events", "--hil-events", str(events), "--log-file", str(log)]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(PLUGINS_DIR), env.get("PYTHONPATH")]))
    try:
        done = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SuitesError(f"pytest collection: no answer after {timeout:.0f} s") from None
    except OSError as error:
        raise SuitesError(f"pytest collection: {error}") from None
    collected = _collected(events)
    if done.returncode not in (0, EXIT_NO_TESTS) or collected is None:
        output = [line.strip() for line in (done.stderr.strip() or done.stdout.strip()).splitlines()]
        output = [line for line in output if line and not line.startswith(("=", "!", "_"))]  # pytest rulers
        detail = " | ".join(output[-ERROR_LINES:])
        raise SuitesError(f"pytest collection failed (exit {done.returncode}): {detail or 'no output'}")
    suite = Suite("pytest", "pytest (tests/host/hil)")
    for nodeid in collected:
        group, _, title = nodeid.partition("::")
        suite.items.append(Item(nodeid, title or nodeid, group))
    return suite


def _collected(path: Path) -> list | None:
    """nodeids of the collected event, or None without one."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "collected":
            return list(event.get("nodeids", []))
    return None


# T1-T8

def discover_rx(plan: Path | str = RX_PLAN) -> Suite:
    """The entries of the UART RX plan, in plan order."""
    plan = Path(plan)
    try:
        data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SuitesError(f"{plan}: {error}") from None
    tests = data.get("tests") if isinstance(data, dict) else None
    if not isinstance(tests, list) or not tests:
        raise SuitesError(f"{plan}: tests must be a non-empty list")
    suite = Suite("rx_check", "UART RX T1-T8 (uart_rx_check.py)")
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("id"), str):
            raise SuitesError(f"{plan}: each test needs an id")
        suite.items.append(Item(test["id"], str(test.get("title", "")), "uart_rx", tuple(test.get("after", []))))
    return suite


def rx_selection(ids: list, suite: Suite) -> list:
    """The ids to pass to --only: the selection and its after entries, in plan order."""
    known = {item.id: item for item in suite.items}
    unknown = [test_id for test_id in ids if test_id not in known]
    if unknown:
        raise SuitesError(f"not in the UART RX plan: {', '.join(unknown)}")
    wanted = set()

    def add(test_id):
        if test_id in wanted:
            return
        if test_id not in known:
            raise SuitesError(f"{test_id} (an after entry) is not in the UART RX plan")
        wanted.add(test_id)
        for before in known[test_id].after:
            add(before)

    for test_id in ids:
        add(test_id)
    return [item.id for item in suite.items if item.id in wanted]


# Scenarios

def discover_scenarios(catalog: Catalog, folder: Path | str = SCENARIOS_DIR) -> Suite:
    """Scenario files of a folder; a bad file is kept as an error of the family."""
    suite = Suite("scenario", "Scenarios (tests/host/tui/scenarios)")
    found, suite.errors = scenarios.load_all(folder, catalog)
    for item in found:
        suite.items.append(Item(item.path.name, item.name, "scenarios"))
    return suite


# All

def discover_all(catalog: Catalog, work_dir: Path | str, tests: Path | str = HIL_DIR, plan: Path | str = RX_PLAN,
                 folder: Path | str = SCENARIOS_DIR) -> list:
    """The three families; a family that fails is returned empty with its error."""
    families = [
        ("pytest", "pytest (tests/host/hil)", lambda: discover_pytest(work_dir, tests)),
        ("rx_check", "UART RX T1-T8 (uart_rx_check.py)", lambda: discover_rx(plan)),
        ("scenario", "Scenarios (tests/host/tui/scenarios)", lambda: discover_scenarios(catalog, folder)),
    ]
    suites = []
    for kind, name, discover in families:
        try:
            suites.append(discover())
        except SuitesError as error:
            suites.append(Suite(kind, name, errors=[str(error)]))
    return suites
