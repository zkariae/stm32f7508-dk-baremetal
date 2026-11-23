"""Run options of the TUI: environment variables chosen for a pytest run.

tests/host/config/run_options.yaml lists the options (its header gives the
format); this module reads and checks it, checks the values typed in the
Options window and turns them into the environment of the run. No option
name is written here: a new option is a new entry of the file.

Values are kept as a mapping {name: value}: True or False for a bool, a text
for a choice or an int ("" for an int left empty). environment() gives each
variable the text to send, or None for a value equal to its default: the
runner then removes the variable from the environment of the run, so a run
uses what the Tests tab shows and nothing else. initial() takes the values
already set in the environment of the TUI, so HIL variables given on its
command line still work; a value that breaks its rules is ignored.

A choice reads its values from a mapping of another YAML file of the same
folder; an alias is turned into its value, without case.

No Textual import.

Version: 1.0
Date: 23/11/2026
Author: Z. BEN-AKKA
History:
  1.0  23/11/2026  Initial version.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[4]
DEFAULT_FILE = _REPO / "tests" / "host" / "config" / "run_options.yaml"
SCHEMA_VERSION = 1
BOOL_SENT = "1"  # Text of a ticked bool

_COMMON = {"type", "label", "help"}
# type: (required fields, optional fields), besides _COMMON
_TYPES = {
    "bool": (set(), set()),
    "choice": ({"values_from", "default"}, {"other"}),
    "int": ({"min", "max"}, set()),
}
_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
_DECIMAL = re.compile(r"0|[1-9][0-9]*")  # No leading zeros


class OptionsError(Exception):
    """The options file is missing, unreadable or breaks the schema."""


class ValueRefused(Exception):
    """A value breaks the rules of its option."""

    def __init__(self, name: str, message: str):
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message


@dataclass(frozen=True)
class RunOption:
    """One option, already checked against the schema."""

    name: str
    type: str
    label: str
    help: str
    default: object  # False for a bool, "" for an int, one of the choices for a choice
    choices: tuple = ()  # choice: (value, aliases) pairs, in file order
    pattern: str = ""  # choice: accepted typed text, "" for none
    hint: str = ""
    low: int = 0  # int
    high: int = 0

    def check(self, value):
        """The value to keep, or ValueRefused."""
        if self.type == "bool":
            return bool(value)
        text = str(value).strip()
        if self.type == "int":
            if not text:
                return ""
            if not _DECIMAL.fullmatch(text) or not self.low <= int(text) <= self.high:
                raise ValueRefused(self.name, f"a whole number from {self.low} to {self.high}, or nothing")
            return text
        for choice, aliases in self.choices:
            if text.lower() in (choice.lower(), *(alias.lower() for alias in aliases)):
                return choice
        if self.pattern and re.fullmatch(self.pattern, text):
            return text
        rules = ["one of " + ", ".join(choice for choice, _ in self.choices)]
        if self.pattern:
            rules.append(self.hint)
        raise ValueRefused(self.name, ", or ".join(rules))


class RunOptions:
    """The options of a file, in file order."""

    def __init__(self, options: list):
        self.options = tuple(options)

    def defaults(self) -> dict:
        return {option.name: option.default for option in self.options}

    def initial(self, environ) -> dict:
        """The defaults, replaced by the values already set in environ when they are valid."""
        values = self.defaults()
        for option in self.options:
            text = environ.get(option.name)
            if text is None:
                continue
            try:
                values[option.name] = text == BOOL_SENT if option.type == "bool" else option.check(text)
            except ValueRefused:
                pass  # The default stays
        return values

    def environment(self, values: dict) -> dict:
        """{variable: text, or None for a default value}; ValueRefused names a bad value."""
        result = {}
        for option in self.options:
            value = option.check(values.get(option.name, option.default))
            if value == option.default:
                result[option.name] = None
            else:
                result[option.name] = BOOL_SENT if option.type == "bool" else value
        return result

    def text(self, values: dict) -> str:
        """The variables sent, as on a command line; "" when all are default."""
        return " ".join(f"{name}={value}" for name, value in self.environment(values).items() if value is not None)


def load(path: Path | str | None = None) -> RunOptions:
    """Read and check the options file; raises OptionsError naming the faulty field."""
    path = Path(path) if path else DEFAULT_FILE
    data = _read(path)
    unknown = set(data) - {"schema_version", "options"}
    if unknown:
        raise OptionsError(f"{path.name}: unknown keys {sorted(map(str, unknown))}")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise OptionsError(f"{path.name}: schema_version must be {SCHEMA_VERSION}")
    raw = data.get("options")
    if not isinstance(raw, dict) or not raw:
        raise OptionsError(f"{path.name}: options must be a non-empty mapping")
    return RunOptions([_option(path.parent, name, entry) for name, entry in raw.items()])


def _read(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise OptionsError(f"{path}: {error}") from error
    if not isinstance(data, dict):
        raise OptionsError(f"{path.name}: not a mapping")
    return data


def _option(folder: Path, name, entry) -> RunOption:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise OptionsError(f"{name}: invalid variable name")
    if not isinstance(entry, dict):
        raise OptionsError(f"{name}: not a mapping")
    kind = entry.get("type")
    if kind not in _TYPES:
        raise OptionsError(f"{name}.type: must be one of {', '.join(_TYPES)}")
    needed, optional = _TYPES[kind]
    unknown = set(entry) - _COMMON - needed - optional
    if unknown:
        raise OptionsError(f"{name}: unknown fields {sorted(map(str, unknown))} for type {kind}")
    missing = (_COMMON | needed) - set(entry)
    if missing:
        raise OptionsError(f"{name}: missing fields {sorted(missing)}")
    for key in ("label", "help"):
        if not isinstance(entry[key], str) or not entry[key]:
            raise OptionsError(f"{name}.{key}: must be a non-empty string")
    common = (name, kind, entry["label"], entry["help"])
    if kind == "bool":
        return RunOption(*common, default=False)
    if kind == "int":
        low, high = entry["min"], entry["max"]
        if type(low) is not int or type(high) is not int or not 0 <= low <= high:  # bool is an int: refused
            raise OptionsError(f"{name}: min and max must be whole numbers, 0 <= min <= max")
        return RunOption(*common, default="", low=low, high=high)
    choices = _choices(folder, name, entry["values_from"])
    pattern, hint = _other(name, entry.get("other"))
    if entry["default"] not in [choice for choice, _ in choices]:
        raise OptionsError(f"{name}.default: must be one of the values")
    return RunOption(*common, default=entry["default"], choices=choices, pattern=pattern, hint=hint)


def _choices(folder: Path, name: str, source) -> tuple:
    """(value, aliases) pairs of the mapping named by values_from."""
    where = f"{name}.values_from"
    if not isinstance(source, dict) or set(source) != {"file", "key"}:
        raise OptionsError(f"{where}: must be {{file, key}}")
    file, key = source["file"], source["key"]
    if not isinstance(file, str) or Path(file).name != file:
        raise OptionsError(f"{where}.file: must be a file name of the folder of the options file")
    try:
        mapping = _read(folder / file).get(key)
    except OptionsError as error:
        raise OptionsError(f"{where}: {error}") from error
    if not isinstance(mapping, dict) or not mapping:
        raise OptionsError(f"{where}: {key} of {file} must be a non-empty mapping")
    pairs, seen = [], set()
    for value, entry in mapping.items():
        aliases = entry.get("aliases", []) if isinstance(entry, dict) else []
        names = [value, *aliases] if isinstance(aliases, list) else [None]
        if not all(isinstance(text, str) and text for text in names):
            raise OptionsError(f"{where}: {value} of {file}: the value and its aliases must be texts")
        for text in names:
            if text.lower() in seen:
                raise OptionsError(f"{where}: {text} of {file} is defined twice")
            seen.add(text.lower())
        pairs.append((value, tuple(aliases)))
    return tuple(pairs)


def _other(name: str, other) -> tuple:
    """(pattern, hint) of a choice that also accepts a typed text; empty texts without it."""
    if other is None:
        return "", ""
    where = f"{name}.other"
    if not isinstance(other, dict) or set(other) != {"pattern", "hint"}:
        raise OptionsError(f"{where}: must be {{pattern, hint}}")
    if not all(isinstance(text, str) and text for text in other.values()):
        raise OptionsError(f"{where}: pattern and hint must be non-empty strings")
    try:
        re.compile(other["pattern"])
    except re.error as error:
        raise OptionsError(f"{where}.pattern: {error}") from error
    return other["pattern"], other["hint"]
