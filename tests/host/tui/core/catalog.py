"""Command catalogue of the TUI: loading, CAPS merge and argument checks.

CAPS gives the command names only; tests/host/config/commands.yaml tells how
to ask for each command (README.md section 4.2). This module is the only
place that knows the argument types, so ui/ holds no command name (C1, C5).
The rules come from tests/protocol.md section 6, never from the firmware.

Checks between arguments (QSPI_READ addr + len, QSPI_WRITE page) stay with
the firmware. The free form, used to send a deliberately invalid value,
does not go through Catalog.check.

No Textual or pyserial import: the catalogue tests need no installation.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import enum
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[4]
DEFAULT_CATALOGUE = _REPO / "tests" / "host" / "config" / "commands.yaml"
DEFAULT_HEADER = _REPO / "tests" / "firmware" / "hil_bench" / "inc" / "hil_protocol.h"

SCHEMA_VERSION = 1
NAME_MAX_LEN = 32  # HIL_CMD_NAME_MAX_LEN in hil_protocol.h
RESERVED_KEYS = ("id", "command")  # protocol.md section 5.1

_COMMAND_FIELDS = {"group", "summary", "spec", "effect", "requires", "args"}
_COMMAND_REQUIRED = {"group", "summary", "spec", "args"}
_EFFECTS = ("destructive", "reboots")
_ARG_COMMON = {"type", "default", "required"}

# type: (required parameters, optional parameters)
_TYPES = {
    "enum": ({"values"}, set()),
    "int": ({"min", "max"}, set()),
    "hex": ({"digits", "min", "max"}, {"multiple_of"}),
    "hexdata": ({"bytes"}, set()),
    "letter": ({"min", "max"}, set()),
    "color": (set(), set()),
}

_COMMAND_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
_ARG_NAME = re.compile(r"[a-z][a-z0-9_]*")
_DECIMAL = re.compile(r"0|[1-9][0-9]*")  # No leading zeros
_HEX = re.compile(r"0x([0-9A-Fa-f]+)")  # Lowercase prefix, either digit case
_HEXDATA = re.compile(r"[0-9A-Fa-f]+")
_COLOR = re.compile(r"0x[0-9A-Fa-f]{1,4}")  # protocol.md section 6.12
_LETTER = re.compile(r"[A-Z]")
_HEADER_NAME = re.compile(r'^\s*#\s*define\s+HIL_CMD_\w+\s+"([^"]*)"', re.MULTILINE)


class CatalogError(Exception):
    """The catalogue file is missing, unreadable or breaks the schema."""


class ArgumentError(Exception):
    """A value typed in a form breaks the rules of its argument."""

    def __init__(self, arg: str, message: str):
        super().__init__(f"{arg}: {message}")
        self.arg = arg
        self.message = message


class EntryStatus(enum.Enum):
    """How a command is shown, from CAPS and the catalogue (README.md section 4.2)."""

    TYPED = "typed"  # In CAPS and in the catalogue: typed form
    FREE = "free"  # In CAPS only: free key=value form
    ABSENT = "absent"  # In the catalogue only: grey, not in this firmware


@dataclass(frozen=True)
class Arg:
    """One argument of a command, already checked against the schema."""

    name: str
    type: str
    required: bool
    default: object
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Command:
    """One catalogue entry, already checked against the schema."""

    name: str
    group: str
    summary: str
    spec: str
    effect: str | None
    requires: str | None
    args: tuple

    @property
    def needs_confirmation(self) -> bool:
        """Destructive or rebooting commands ask before sending."""
        return self.effect is not None


@dataclass(frozen=True)
class Entry:
    """A command as the interface shows it."""

    name: str
    status: EntryStatus
    command: Command | None  # None for FREE


def default_text(arg: Arg) -> str:
    """The default value as typed in a form, or "" without default."""
    value = arg.default
    if value is None:
        return ""
    if arg.type == "hex":
        return f"0x{value:0{arg.params['digits'][1]}X}"
    if arg.type == "color":
        return f"0x{value:04X}"
    if arg.type == "hexdata":
        return str(value).upper()
    return str(value)


def check_value(arg: Arg, text: str) -> str:
    """The value to send, or ArgumentError if it breaks the argument rules."""
    params = arg.params
    if arg.type == "enum":
        if text not in params["values"]:
            raise ArgumentError(arg.name, f"one of {', '.join(params['values'])}")
        return text
    if arg.type == "int":
        if not _DECIMAL.fullmatch(text):
            raise ArgumentError(arg.name, "unsigned decimal without leading zeros")
        _check_range(arg, int(text), str(params["min"]), str(params["max"]))
        return text
    if arg.type == "hex":
        match = _HEX.fullmatch(text)
        low, high = params["digits"]
        if not match or not low <= len(match.group(1)) <= high:
            raise ArgumentError(arg.name, f"0x followed by {low} to {high} hexadecimal digits")
        value = int(match.group(1), 16)
        _check_range(arg, value, f"0x{params['min']:0{high}X}", f"0x{params['max']:0{high}X}")
        step = params.get("multiple_of")
        if step and value % step:
            raise ArgumentError(arg.name, f"a multiple of {step}")
        return text
    if arg.type == "hexdata":
        low, high = params["bytes"]
        if not _HEXDATA.fullmatch(text) or len(text) % 2:
            raise ArgumentError(arg.name, "an even number of hexadecimal digits")
        if not low <= len(text) // 2 <= high:
            raise ArgumentError(arg.name, f"{low} to {high} bytes")
        return text
    if arg.type == "letter":
        if not _LETTER.fullmatch(text) or not params["min"] <= text <= params["max"]:
            raise ArgumentError(arg.name, f"one uppercase letter from {params['min']} to {params['max']}")
        return text
    if arg.type == "color":
        if not _COLOR.fullmatch(text):
            raise ArgumentError(arg.name, "RGB565 colour: 0x followed by 1 to 4 hexadecimal digits")
        return text
    raise ArgumentError(arg.name, f"unknown type {arg.type}")


def _check_range(arg: Arg, value: int, low: str, high: str) -> None:
    if not arg.params["min"] <= value <= arg.params["max"]:
        raise ArgumentError(arg.name, f"from {low} to {high}")


class Catalog:
    """The checked catalogue, in file order."""

    def __init__(self, commands: dict):
        self.commands = commands

    def names(self) -> list:
        return list(self.commands)

    def merge(self, caps_names: list) -> list:
        """Entries in CAPS order, then the catalogue commands missing from CAPS."""
        entries = []
        for name in caps_names:
            command = self.commands.get(name)
            status = EntryStatus.TYPED if command else EntryStatus.FREE
            entries.append(Entry(name, status, command))
        for name, command in self.commands.items():
            if name not in caps_names:
                entries.append(Entry(name, EntryStatus.ABSENT, command))
        return entries

    def check(self, name: str, values: dict) -> dict:
        """The arguments to send, in catalogue order, from the texts typed in a form.

        An empty optional argument is left out. Raises ArgumentError for a
        missing, unknown or invalid argument, and KeyError for a command that
        is not in the catalogue.
        """
        command = self.commands[name]
        known = {arg.name for arg in command.args}
        for key in values:
            if key not in known:
                raise ArgumentError(key, f"not an argument of {name}")
        result = {}
        for arg in command.args:
            text = (values.get(arg.name) or "").strip()
            if not text:
                if arg.required:
                    raise ArgumentError(arg.name, "required")
                continue
            result[arg.name] = check_value(arg, text)
        return result


def load(path: Path | str | None = None) -> Catalog:
    """Read and check the catalogue; raises CatalogError naming the faulty field."""
    path = Path(path) if path else DEFAULT_CATALOGUE
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CatalogError(f"{path}: {error}") from error
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: not a mapping")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    unknown = set(data) - {"schema_version", "commands"}
    if unknown:
        raise CatalogError(f"{path}: unknown keys {sorted(unknown)}")
    raw = data.get("commands")
    if not isinstance(raw, dict) or not raw:
        raise CatalogError(f"{path}: commands must be a non-empty mapping")
    commands = {}
    for name, entry in raw.items():
        commands[name] = _command(name, entry)
    for command in commands.values():
        if command.requires is not None and command.requires not in commands:
            raise CatalogError(f"{command.name}.requires: {command.requires} is not in the catalogue")
    return Catalog(commands)


def firmware_names(header: Path | str | None = None) -> list:
    """The quoted HIL_CMD_* names of hil_protocol.h, in file order."""
    path = Path(header) if header else DEFAULT_HEADER
    return _HEADER_NAME.findall(path.read_text(encoding="utf-8"))


def _command(name, entry) -> Command:
    if not isinstance(name, str) or not _COMMAND_NAME.fullmatch(name) or len(name) > NAME_MAX_LEN:
        raise CatalogError(f"{name}: invalid command name")
    if not isinstance(entry, dict):
        raise CatalogError(f"{name}: not a mapping")
    unknown = set(entry) - _COMMAND_FIELDS
    if unknown:
        raise CatalogError(f"{name}: unknown fields {sorted(unknown)}")
    missing = _COMMAND_REQUIRED - set(entry)
    if missing:
        raise CatalogError(f"{name}: missing fields {sorted(missing)}")
    for key in ("group", "summary", "spec"):
        if not isinstance(entry[key], str) or not entry[key]:
            raise CatalogError(f"{name}.{key}: must be a non-empty string")
    effect = entry.get("effect")
    if effect is not None and effect not in _EFFECTS:
        raise CatalogError(f"{name}.effect: must be one of {', '.join(_EFFECTS)}")
    requires = entry.get("requires")
    if requires is not None and not isinstance(requires, str):
        raise CatalogError(f"{name}.requires: must be a command name")
    raw_args = entry["args"]
    if not isinstance(raw_args, dict):
        raise CatalogError(f"{name}.args: must be a mapping")
    args = tuple(_arg(name, arg_name, spec) for arg_name, spec in raw_args.items())
    return Command(name, entry["group"], entry["summary"], entry["spec"], effect, requires, args)


def _arg(command: str, name, spec) -> Arg:
    where = f"{command}.{name}"
    if not isinstance(name, str) or not _ARG_NAME.fullmatch(name) or name in RESERVED_KEYS:
        raise CatalogError(f"{where}: invalid argument name")
    if not isinstance(spec, dict):
        raise CatalogError(f"{where}: not a mapping")
    kind = spec.get("type")
    if kind not in _TYPES:
        raise CatalogError(f"{where}.type: must be one of {', '.join(_TYPES)}")
    needed, optional = _TYPES[kind]
    params = {key: value for key, value in spec.items() if key not in _ARG_COMMON}
    unknown = set(params) - needed - optional
    if unknown:
        raise CatalogError(f"{where}: unknown fields {sorted(unknown)} for type {kind}")
    missing = needed - set(params)
    if missing:
        raise CatalogError(f"{where}: missing fields {sorted(missing)} for type {kind}")
    _check_params(where, kind, params)
    required = spec.get("required", True)
    if not isinstance(required, bool):
        raise CatalogError(f"{where}.required: must be true or false")
    arg = Arg(name, kind, required, spec.get("default"), params)
    _check_default(where, arg)
    return arg


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_pair(where: str, value) -> None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(_is_int(item) for item in value)
        or not 1 <= value[0] <= value[1]
    ):
        raise CatalogError(f"{where}: must be [min, max] with 1 <= min <= max")


def _check_params(where: str, kind: str, params: dict) -> None:
    if kind == "enum":
        values = params["values"]
        # A bare on or off would be a boolean in YAML 1.1
        if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
            raise CatalogError(f"{where}.values: must be a non-empty list of quoted strings")
        if len(set(values)) != len(values):
            raise CatalogError(f"{where}.values: duplicate value")
    if kind in ("int", "hex"):
        low, high = params["min"], params["max"]
        if not _is_int(low) or not _is_int(high) or not 0 <= low <= high:
            raise CatalogError(f"{where}: min and max must be integers with 0 <= min <= max")
    if kind == "hex":
        _check_pair(f"{where}.digits", params["digits"])
        if params["max"] >= 16 ** params["digits"][1]:
            raise CatalogError(f"{where}.max: does not fit in {params['digits'][1]} digits")
        step = params.get("multiple_of")
        if step is not None and (not _is_int(step) or step < 1):
            raise CatalogError(f"{where}.multiple_of: must be a positive integer")
    if kind == "hexdata":
        _check_pair(f"{where}.bytes", params["bytes"])
    if kind == "letter":
        low, high = params["min"], params["max"]
        for value in (low, high):
            if not isinstance(value, str) or not _LETTER.fullmatch(value):
                raise CatalogError(f"{where}: min and max must be uppercase letters")
        if low > high:
            raise CatalogError(f"{where}: min is after max")


def _check_default(where: str, arg: Arg) -> None:
    if arg.default is None:
        return
    numeric = arg.type in ("int", "hex", "color")
    if numeric != _is_int(arg.default) or (not numeric and not isinstance(arg.default, str)):
        raise CatalogError(f"{where}.default: wrong value type for {arg.type}")
    try:
        check_value(arg, default_text(arg))
    except (ArgumentError, ValueError) as error:
        raise CatalogError(f"{where}.default: {error}") from error
