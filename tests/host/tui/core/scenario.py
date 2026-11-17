"""YAML scenarios of the TUI: load, check and run them in the open session (C2, C5).

A scenario is a list of steps played in the session already open (README.md
section 4.5); adding a YAML file adds a scenario, without code (C5):

    name: LCD colour check
    description: optional text
    steps:
      - {command: LCD_INIT}
      - {command: LCD_FILL, args: {color: "0xF800"}}
      - {command: LCD_PIXEL, args: {x: 0, y: 0}, expect: {color: "0xF800"}}
      - {prompt: "Is the screen red?"}

A step has either command (with optional args and expect) or prompt. The
command must be in the catalogue and its args pass Catalog.check, so only
the existing argument types are accepted; quote hex values, YAML reads an
unquoted 0xF800 as a number. load() raises ScenarioError naming the file
and the step; load_all() keeps going past a bad file and returns its error.

run() plays the steps in order. It knows neither the session nor the
interface: request(name, args) returns a Response or raises when the
session is lost, ask(text) returns the operator's answer, emit(event)
receives each event, stop is checked between steps. The events have the
format of plugins/hil_events.py (session_start, collected, test_start,
report with when=call, test_end, session_end), with one test per step, so
the runner, the counters and the report treat pytest and scenarios alike.

A step passes on status=OK with every expect value equal (text compare,
case ignored for 0x values). status=ERR, another value or a No to a prompt
is FUNCTIONAL_ERROR and the next steps still run. A lost session (a
HilOutcome, by its outcome, or any other exception as BENCH_ERROR) ends
the scenario with exitstatus 1; stop ends it with exitstatus 2
(INTERRUPTED). No Textual import.

Not done here: the discovery and the display (suites.py, tests_pane.py),
writing events.jsonl (runner.py), the first real scenario (scenarios/).

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.catalog import ArgumentError, Catalog

STEP_KEYS = {"command", "args", "expect", "prompt"}
SCENARIO_KEYS = {"name", "description", "steps"}
EXIT_PASSED, EXIT_FAILED, EXIT_INTERRUPTED = 0, 1, 2
LOGGER = "tui.scenario"


class ScenarioError(Exception):
    """A scenario file that cannot be played."""


@dataclass(frozen=True)
class Step:
    """One checked step: a command with its checked args and expected values, or a prompt."""

    number: int  # From 1
    command: str | None = None
    args: dict = field(default_factory=dict)
    expect: dict = field(default_factory=dict)
    prompt: str | None = None

    @property
    def label(self) -> str:
        return self.command if self.command is not None else "prompt"


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    steps: tuple
    path: Path

    def nodeid(self, step: Step) -> str:
        return f"scenario:{self.path.name}::step{step.number}"


# Loading

def load(path: Path | str, catalog: Catalog) -> Scenario:
    """Read and check one scenario; ScenarioError names the file and the step."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ScenarioError(f"{path}: {error}") from None
    if not isinstance(data, dict):
        raise ScenarioError(f"{path}: not a mapping")
    unknown = set(data) - SCENARIO_KEYS
    if unknown:
        raise ScenarioError(f"{path}: unknown keys {sorted(unknown)}")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ScenarioError(f"{path}: name must be a non-empty string")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise ScenarioError(f"{path}: description must be a string")
    raw = data.get("steps")
    if not isinstance(raw, list) or not raw:
        raise ScenarioError(f"{path}: steps must be a non-empty list")
    steps = tuple(_step(path, number, entry, catalog) for number, entry in enumerate(raw, 1))
    return Scenario(name.strip(), description, steps, path)


def load_all(folder: Path | str, catalog: Catalog) -> tuple:
    """(scenarios, errors) of the *.yaml files of a folder, by file name; a bad file does not stop the others."""
    scenarios, errors = [], []
    for path in sorted(Path(folder).glob("*.yaml")):
        try:
            scenarios.append(load(path, catalog))
        except ScenarioError as error:
            errors.append(str(error))
    return scenarios, errors


def _step(path: Path, number: int, entry, catalog: Catalog) -> Step:
    where = f"{path}: step {number}"
    if not isinstance(entry, dict):
        raise ScenarioError(f"{where}: not a mapping")
    unknown = set(entry) - STEP_KEYS
    if unknown:
        raise ScenarioError(f"{where}: unknown keys {sorted(unknown)}")
    if ("command" in entry) == ("prompt" in entry):
        raise ScenarioError(f"{where}: needs either command or prompt")
    if "prompt" in entry:
        if set(entry) != {"prompt"}:
            raise ScenarioError(f"{where}: a prompt step has no args or expect")
        if not isinstance(entry["prompt"], str) or not entry["prompt"].strip():
            raise ScenarioError(f"{where}: prompt must be a non-empty string")
        return Step(number, prompt=entry["prompt"].strip())
    command = entry["command"]
    if command not in catalog.commands:
        raise ScenarioError(f"{where}: {command} is not in the catalogue")
    args = _mapping(where, "args", entry.get("args", {}))
    try:
        checked = catalog.check(command, args)
    except ArgumentError as error:
        types = {arg.name: arg.type for arg in catalog.commands[command].args}
        raw = (entry.get("args") or {}).get(error.arg)
        hint = " (quote hex values)" if types.get(error.arg) in ("hex", "color") and isinstance(raw, int) else ""
        raise ScenarioError(f"{where}: {command} {error.arg}: {error.message}{hint}") from None
    return Step(number, command=command, args=checked, expect=_mapping(where, "expect", entry.get("expect", {})))


def _mapping(where: str, key: str, value) -> dict:
    """args or expect as texts; a bool or a nested value is refused."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScenarioError(f"{where}: {key} must be a mapping")
    result = {}
    for name, item in value.items():
        if not isinstance(name, str) or isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ScenarioError(f"{where}: {key}.{name} must be a string or a number")
        result[name] = str(item)
    return result


# Running

def same(expected: str, got: str) -> bool:
    """Text compare; case ignored for 0x values."""
    if expected.lower().startswith("0x") and got.lower().startswith("0x"):
        return expected.lower() == got.lower()
    return expected == got


def outcome_of(error: BaseException) -> str:
    """hil_outcome of a lost session: a HilOutcome by its outcome, anything else BENCH_ERROR."""
    if any(cls.__name__ == "HilOutcome" for cls in type(error).__mro__):
        return str(getattr(error, "outcome", "PROTOCOL_FAILURE"))
    return "BENCH_ERROR"


def run(scenario: Scenario, request, ask, emit, stop: threading.Event | None = None) -> int:
    """Play the steps; returns the exitstatus (0 passed, 1 failed, 2 interrupted)."""
    stop = stop or threading.Event()
    emit(_event("session_start", pid=os.getpid(), args=[str(scenario.path)], rootdir=str(scenario.path.parent),
                scenario=scenario.name))
    emit(_event("collected", count=len(scenario.steps), nodeids=[scenario.nodeid(step) for step in scenario.steps]))
    status = EXIT_PASSED
    for step in scenario.steps:
        if stop.is_set():
            status = EXIT_INTERRUPTED
            break
        nodeid = scenario.nodeid(step)
        emit(_event("test_start", nodeid=nodeid, label=step.label))
        started = time.monotonic()
        lost = False
        try:
            outcome, message = _play(step, request, ask, emit, nodeid)
        except Exception as error:  # The session is lost: the next steps cannot run
            outcome, message, lost = outcome_of(error), _first_line(str(error) or type(error).__name__), True
        emit(_event("report", nodeid=nodeid, when="call", outcome="passed" if outcome == "PASS" else "failed",
                    hil_outcome=outcome, duration=round(time.monotonic() - started, 6), message=message,
                    xfail=False))
        emit(_event("test_end", nodeid=nodeid))
        if outcome != "PASS":
            status = EXIT_FAILED
        if lost:
            break
    emit(_event("session_end", exitstatus=status))
    return status


def _play(step: Step, request, ask, emit, nodeid: str) -> tuple:
    """(hil_outcome, message) of one step; raises when the session is lost."""
    if step.prompt is not None:
        answer = bool(ask(step.prompt))
        emit(_event("log", nodeid=nodeid, logger=LOGGER, level="INFO",
                    text=f"PROMPT {step.prompt} -> {'yes' if answer else 'no'}"))
        return ("PASS", "") if answer else ("FUNCTIONAL_ERROR", f"operator answered no: {step.prompt}")
    response = request(step.command, step.args)
    if response.status != "OK":
        return "FUNCTIONAL_ERROR", f"{step.command}: status={response.status} code={response.code}"
    for key, expected in step.expect.items():
        got = response.fields.get(key)
        if got is None:
            return "FUNCTIONAL_ERROR", f"{key}: expected {expected}, missing"
        if not same(expected, str(got)):
            return "FUNCTIONAL_ERROR", f"{key}: expected {expected}, got {got}"
    return "PASS", ""


def _event(event: str, **fields) -> dict:
    return {"t": time.time(), "event": event, **fields}


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else ""
