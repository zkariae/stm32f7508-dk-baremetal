"""A new command, test and scenario reach the TUI without a change of its code (C5, E31).

No board. A command GPIO_READ (port letter, pin number: argument types that
already exist) is added the way C5 adds one: to a copy of commands.yaml in
tmp_path and to the CAPS of the fake firmware of test_ui_commands, which
echoes the arguments of any command. A scenario that uses it is put in a
scenarios folder of tmp_path, a pytest file in a tests folder of tmp_path.
HilApp gets them through its parameters only (catalog, scenarios_dir,
discover), as hil_tui.py passes the real ones.

Checked: the command is listed, its form shows its arguments with their
defaults and Send writes the request and shows the answer; the scenario is
listed in the Tests tab and runs to PASS; the pytest file is listed in the
pytest family; and no file of ui/, core/, plugins/ or hil_tui.py holds a
command name of the catalogue as a string, so a new command never needs
them (this check needs no Textual).

Not tested here: the command in the real firmware, hil_protocol.h and a HIL
test on the board. That is the C5 proof on a throwaway branch (README.md
section 7), checked by hand.

Version: 1.1
Date: 16/11/2026
Author: Z. BEN-AKKA
History:
  1.0  16/11/2026  Initial version.
  1.1  16/11/2026  No short CAPS pages: the fake firmware pages by line length since test_ui_commands.py 1.2.
"""

import ast
import asyncio
from pathlib import Path

import pytest
import yaml

from core import catalog as catalog_module
from core.suites import discover_all

try:
    import textual  # noqa: F401
except ModuleNotFoundError:
    textual = None

needs_textual = pytest.mark.skipif(textual is None, reason="Textual is not installed")

if textual is not None:
    from textual.widgets import Input, OptionList  # noqa: E402

    import test_ui_commands as ui  # noqa: E402
    from core.session import State  # noqa: E402
    from ui import tests_pane  # noqa: E402  (the module: pytest would try to collect the class TestsPane)
    from ui.app import HilApp  # noqa: E402

TUI_DIR = Path(__file__).resolve().parents[1]
NEW = "GPIO_READ"
NEW_ENTRY = {
    "group": "GPIO",
    "summary": "Read the input level of one pin",
    "spec": "6.21",
    "args": {"port": {"type": "letter", "min": "A", "max": "K", "default": "I"},
             "pin": {"type": "int", "min": 0, "max": 15, "default": 11}},
}
SCENARIO_FILE = "gpio_read.yaml"
SCENARIO = f"""\
name: User button
description: Read the pin of the user button.
steps:
  - {{command: {NEW}, args: {{port: I, pin: 11}}, expect: {{port: I, pin: "11"}}}}
"""
PYTEST_FILE = "test_gpio_read.py"
PYTEST_TEST = '''\
def test_button_level():
    assert True
'''
RUN_WAIT = 30.0


# The new command, test and scenario

@pytest.fixture
def catalog(tmp_path):
    """commands.yaml with GPIO_READ added, as the C5 change does."""
    data = yaml.safe_load(catalog_module.DEFAULT_CATALOGUE.read_text(encoding="utf-8"))
    data["commands"][NEW] = NEW_ENTRY
    path = tmp_path / "commands.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return catalog_module.load(path)


@pytest.fixture
def scenarios(tmp_path) -> Path:
    folder = tmp_path / "scenarios"
    folder.mkdir()
    (folder / SCENARIO_FILE).write_text(SCENARIO, encoding="utf-8")
    return folder


@pytest.fixture
def tests(tmp_path) -> Path:
    folder = tmp_path / "tests"
    folder.mkdir()
    (folder / PYTEST_FILE).write_text(PYTEST_TEST, encoding="utf-8")
    return folder


def drive(catalog, scenario, scenarios_dir=None, tests_dir=None):
    """test_ui_commands.drive with the catalogue, scenarios and tests of the C5 change."""
    rig = ui.Rig(caps=ui.NAMES + [NEW])
    kwargs = {}
    if scenarios_dir is not None:
        kwargs["scenarios_dir"] = scenarios_dir
    if tests_dir is not None:
        kwargs["discover"] = lambda cat, work_dir, folder: discover_all(cat, work_dir, tests=tests_dir, folder=folder)

    async def main():
        app = HilApp(rig.bench, catalog, rig.session, **kwargs)
        try:
            async with app.run_test(size=ui.SIZE) as pilot:
                await ui.until(pilot, app, State.CONNECTED)
                await scenario(pilot, app, rig)
        finally:
            if app.session is not None:
                app.session.shutdown()

    asyncio.run(main())


async def open_tests_tab(pilot, app) -> None:
    await pilot.press("ctrl+o")
    await ui.wait_for(pilot, lambda: app.tests.suites, "the discovery")


async def wait_long(pilot, condition, what: str) -> None:
    for _ in range(int(RUN_WAIT / ui.STEP)):
        if condition():
            return
        await pilot.pause(ui.STEP)
    pytest.fail(f"timed out waiting for {what}")


# TUI

@needs_textual
def test_new_command_in_the_command_pane(catalog):
    async def scenario(pilot, app, rig):
        commands = app.query_one("#commands", OptionList)
        assert not commands.get_option(NEW).disabled  # In the catalogue and in CAPS
        await ui.select(pilot, app, NEW)
        fields = {field.id: field.value for field in app.query(Input) if field.id}
        assert any(key.endswith("port") and value == "I" for key, value in fields.items()), fields
        assert any(key.endswith("pin") and value == "11" for key, value in fields.items()), fields
        await ui.send(pilot)
        assert rig.port.written[-1].endswith(f"command={NEW} port=I pin=11")
        result = ui.text(app, "#result")
        assert NEW in result and "OK" in result and "port" in result and "pin" in result

    drive(catalog, scenario)


@needs_textual
def test_new_scenario_in_the_tests_tab(catalog, scenarios):
    async def scenario(pilot, app, rig):
        await open_tests_tab(pilot, app)
        assert [item.id for item in app.tests.suites["scenario"].items] == [SCENARIO_FILE]
        app.tests.post_message(tests_pane.TestsPane.Run("scenario", [SCENARIO_FILE], False))
        pane = app.tests
        await wait_long(pilot, lambda: pane.verdict is not None and not pane.running, "the scenario end")
        assert pane.verdict == "PASS"
        assert f"command={NEW} port=I pin=11" in " ".join(rig.port.written)

    drive(catalog, scenario, scenarios_dir=scenarios)


@needs_textual
def test_new_pytest_file_in_the_tests_tab(catalog, tests):
    async def scenario(pilot, app, rig):
        await open_tests_tab(pilot, app)
        suite = app.tests.suites["pytest"]
        assert not suite.errors, suite.errors
        assert [item.id for item in suite.items if item.id.endswith(f"{PYTEST_FILE}::test_button_level")]

    drive(catalog, scenario, tests_dir=tests)


# Code of the TUI

def code_files() -> list:
    files = [TUI_DIR / "hil_tui.py"]
    for folder in ("ui", "core", "plugins"):
        files += sorted((TUI_DIR / folder).rglob("*.py"))
    return files


def test_tui_code_names_no_command():
    """No string of the TUI code is a command name: the catalogue is the only place that knows them."""
    names = set(catalog_module.load().names()) | {NEW}
    found = []
    for path in code_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in names:
                found.append(f"{path.relative_to(TUI_DIR)}:{node.lineno} {node.value!r}")
    assert len(code_files()) > 10  # The folders were found
    assert not found, found
