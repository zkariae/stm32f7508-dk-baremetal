"""Host tests of the run options: the file, the values and the environment of a run.

No board, no Textual. The files of these tests are written in tmp_path; the
real run_options.yaml is loaded too, and checked against its sources:
test_touch.py must read every variable, and no file of ui/, core/, plugins/
or hil_tui.py may name one, so a new option never needs the TUI code.

Not tested here: the Options window (test_ui_options.py) and the environment
that reaches pytest (test_runner.py).

Version: 1.0
Date: 23/11/2026
Author: Z. BEN-AKKA
History:
  1.0  23/11/2026  Initial version.
"""

from pathlib import Path

import pytest

from core.run_options import DEFAULT_FILE, OptionsError, ValueRefused, load

TUI_DIR = Path(__file__).resolve().parents[1]
TEST_TOUCH = TUI_DIR.parent / "hil" / "cases" / "test_touch.py"

COLORS = """\
colors:
  black: {rgb565: "0x0000", aliases: [noir]}
  red: {rgb565: "0xF800", aliases: [rouge]}
  cyan: {rgb565: "0x07FF", aliases: []}
"""
GOOD = """\
schema_version: 1
options:
  FAKE_OPERATOR: {type: bool, label: Operator, help: Runs more tests.}
  FAKE_COLOUR:
    type: choice
    label: Colour
    help: Colour of the test.
    values_from: {file: colors.yaml, key: colors}
    other: {pattern: "0x[0-9A-F]{4}", hint: "0x and 4 digits"}
    default: black
  FAKE_SEED: {type: int, label: Seed, help: Replays a run., min: 0, max: 99}
"""


def write(folder: Path, text: str, colors: str = COLORS) -> Path:
    (folder / "colors.yaml").write_text(colors, encoding="utf-8")
    path = folder / "run_options.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def options(tmp_path):
    return load(write(tmp_path, GOOD))


# File

def test_load(options):
    assert [option.name for option in options.options] == ["FAKE_OPERATOR", "FAKE_COLOUR", "FAKE_SEED"]
    assert options.defaults() == {"FAKE_OPERATOR": False, "FAKE_COLOUR": "black", "FAKE_SEED": ""}
    colour = options.options[1]
    assert colour.choices == (("black", ("noir",)), ("red", ("rouge",)), ("cyan", ()))


BAD = {
    "missing-field": (GOOD.replace("label: Operator, ", ""), "FAKE_OPERATOR: missing fields ['label']"),
    "unknown-field": (GOOD.replace("max: 99", "max: 99, step: 2"), "FAKE_SEED: unknown fields ['step']"),
    "type": (GOOD.replace("type: int", "type: float"), "FAKE_SEED.type: must be one of"),
    "name": (GOOD.replace("FAKE_SEED", "fake seed"), "fake seed: invalid variable name"),
    "range": (GOOD.replace("min: 0", "min: 100"), "FAKE_SEED: min and max"),
    "default": (GOOD.replace("default: black", "default: pink"), "FAKE_COLOUR.default: must be one of the values"),
    "pattern": (GOOD.replace("{4}", "{4}["), "FAKE_COLOUR.other.pattern:"),
    "other": (GOOD.replace(', hint: "0x and 4 digits"', ""), "FAKE_COLOUR.other: must be {pattern, hint}"),
    "no-values-file": (GOOD.replace("file: colors.yaml", "file: missing.yaml"), "FAKE_COLOUR.values_from:"),
    "values-elsewhere": (GOOD.replace("file: colors.yaml", "file: ../colors.yaml"), "FAKE_COLOUR.values_from.file:"),
    "values-key": (GOOD.replace("key: colors", "key: tints"), "tints of colors.yaml must be a non-empty mapping"),
    "no-options": ("schema_version: 1\noptions: {}\n", "options must be a non-empty mapping"),
    "version": (GOOD.replace("schema_version: 1", "schema_version: 2"), "schema_version must be 1"),
    "top-key": (GOOD + "extra: 1\n", "unknown keys ['extra']"),
    "not-a-mapping": ("- 1\n", "not a mapping"),
    "not-yaml": ("options: [", "run_options.yaml"),
}


@pytest.mark.parametrize("text, message", BAD.values(), ids=BAD)
def test_bad_file_names_the_field(tmp_path, text, message):
    with pytest.raises(OptionsError) as failure:
        load(write(tmp_path, text))
    assert message in str(failure.value)


def test_missing_file(tmp_path):
    with pytest.raises(OptionsError):
        load(tmp_path / "nothing.yaml")


@pytest.mark.parametrize("colors, message", [
    (COLORS.replace("[rouge]", "[Noir]"), "Noir of colors.yaml is defined twice"),
    (COLORS.replace("[rouge]", "[1]"), "must be texts"),
    (COLORS.replace("[rouge]", "rouge"), "must be texts"),
], ids=["twice", "number", "not-a-list"])
def test_bad_values_file(tmp_path, colors, message):
    with pytest.raises(OptionsError) as failure:
        load(write(tmp_path, GOOD, colors))
    assert message in str(failure.value)


# Values

@pytest.mark.parametrize("value, kept", [("red", "red"), ("ROUGE", "red"), (" noir ", "black"), ("0xF800", "0xF800")])
def test_choice_kept(options, value, kept):
    assert options.options[1].check(value) == kept


@pytest.mark.parametrize("value", ["", "pink", "0xF80", "F800", "0xF8000"])
def test_choice_refused(options, value):
    with pytest.raises(ValueRefused) as failure:
        options.options[1].check(value)
    assert failure.value.name == "FAKE_COLOUR"
    assert failure.value.message == "one of black, red, cyan, or 0x and 4 digits"


@pytest.mark.parametrize("value", ["", "0", "99"])
def test_int_kept(options, value):
    assert options.options[2].check(value) == value


@pytest.mark.parametrize("value", ["100", "-1", "07", "1.5", "x", "²"])
def test_int_refused(options, value):
    with pytest.raises(ValueRefused) as failure:
        options.options[2].check(value)
    assert "from 0 to 99" in failure.value.message


# Environment

def test_defaults_are_not_sent(options):
    assert options.environment(options.defaults()) == dict.fromkeys(options.defaults())
    assert options.text(options.defaults()) == ""


def test_chosen_values_are_sent(options):
    values = {"FAKE_OPERATOR": True, "FAKE_COLOUR": "rouge", "FAKE_SEED": "42"}
    assert options.environment(values) == {"FAKE_OPERATOR": "1", "FAKE_COLOUR": "red", "FAKE_SEED": "42"}
    assert options.text(values) == "FAKE_OPERATOR=1 FAKE_COLOUR=red FAKE_SEED=42"


def test_empty_option_is_not_sent(options):
    assert options.environment({"FAKE_OPERATOR": True, "FAKE_COLOUR": "noir", "FAKE_SEED": ""}) == {
        "FAKE_OPERATOR": "1", "FAKE_COLOUR": None, "FAKE_SEED": None}


def test_environment_refuses_a_bad_value(options):
    with pytest.raises(ValueRefused):
        options.environment({"FAKE_COLOUR": "pink"})


def test_initial_values_come_from_the_environment(options):
    environ = {"FAKE_OPERATOR": "1", "FAKE_COLOUR": "Rouge", "FAKE_SEED": "7", "OTHER": "x"}
    assert options.initial(environ) == {"FAKE_OPERATOR": True, "FAKE_COLOUR": "red", "FAKE_SEED": "7"}


def test_initial_ignores_bad_values(options):
    environ = {"FAKE_OPERATOR": "0", "FAKE_COLOUR": "pink", "FAKE_SEED": "-1"}
    assert options.initial(environ) == options.defaults()


# The real file

def test_real_file():
    options = load()
    source = TEST_TOUCH.read_text(encoding="utf-8")
    for option in options.options:
        assert f'"{option.name}"' in source, f"no test reads {option.name}"
    colour = next(option for option in options.options if option.type == "choice")
    assert colour.check("rouge") == "red"
    assert colour.check("0x07E0") == "0x07E0"
    assert colour.check("blanc") == "white"  # Accepted here; the drawing test refuses it with its reason


def test_tui_code_names_no_option():
    files = [TUI_DIR / "hil_tui.py"]
    for folder in ("ui", "core", "plugins"):
        files += sorted((TUI_DIR / folder).rglob("*.py"))
    assert len(files) > 10  # The folders were found
    names = [option.name for option in load(DEFAULT_FILE).options]
    found = [f"{path.relative_to(TUI_DIR)}: {name}" for path in files for name in names
             if name in path.read_text(encoding="utf-8")]
    assert not found, found
