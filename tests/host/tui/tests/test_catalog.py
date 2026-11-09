"""Host tests of core/catalog.py against tests/host/config/commands.yaml.

No board. The tests check that the catalogue and hil_protocol.h hold the same
command names, in both directions (C1), that the catalogue merges with the
CAPS list, that destructive commands are marked, and that the form checks
follow tests/protocol.md section 6. Broken catalogues written in tmp_path
check that the loader names the faulty field.

Not tested here: the checks between arguments (QSPI_READ addr + len,
QSPI_WRITE page), which stay with the firmware, and sending the commands to
the board (tests/test_catalog_board.py).

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import pytest

from cases.expected import COMMANDS
from core.catalog import ArgumentError, CatalogError, EntryStatus, default_text, firmware_names, load

CATALOGUE = load()

LCD_AFTER_INIT = ["LCD_CLOCK", "LCD_TIMING", "LCD_LAYER", "LCD_SCAN", "LCD_FILL", "LCD_PIXEL"]


# Firmware and catalogue: C1, both directions

def test_every_firmware_command_is_in_the_catalogue():
    missing = [name for name in firmware_names() if name not in CATALOGUE.commands]
    assert not missing, f"in hil_protocol.h, not in commands.yaml: {missing}"


def test_every_catalogue_command_is_in_the_firmware():
    header = firmware_names()
    extra = [name for name in CATALOGUE.names() if name not in header]
    assert not extra, f"in commands.yaml, not in hil_protocol.h: {extra}"


def test_firmware_names_reads_quoted_names_only(tmp_path):
    header = tmp_path / "hil_protocol.h"
    header.write_text(
        '#define HIL_CMD_HELLO "HELLO"\n'
        '#  define HIL_CMD_CAPS   "CAPS"\n'
        "#define HIL_CMD_NAME_MAX_LEN 32u\n"
        '#define HIL_KEY_ID "id"\n'
    )
    assert firmware_names(header) == ["HELLO", "CAPS"]


# CAPS merge: README.md section 4.2

def test_caps_of_protocol_1_3_gives_typed_forms():
    entries = CATALOGUE.merge(COMMANDS)
    assert [entry.name for entry in entries] == COMMANDS
    assert all(entry.status is EntryStatus.TYPED for entry in entries)


def test_merge_free_and_absent():
    caps = ["NEW_CMD"] + COMMANDS[:-1]
    entries = CATALOGUE.merge(caps)
    assert [entry.name for entry in entries] == caps + [COMMANDS[-1]]
    assert entries[0].status is EntryStatus.FREE
    assert entries[0].command is None
    assert entries[-1].status is EntryStatus.ABSENT
    assert entries[-1].command is CATALOGUE.commands[COMMANDS[-1]]


# Marked commands: C1

def test_only_flash_writes_ask_for_confirmation():
    # protocol.md section 6.6: erase and write change the test area
    marked = [name for name, command in CATALOGUE.commands.items() if command.needs_confirmation]
    assert marked == ["QSPI_ERASE", "QSPI_WRITE"]


def test_lcd_commands_require_lcd_init():
    # protocol.md section 6.12: BUSY before LCD_INIT
    requiring = [name for name, command in CATALOGUE.commands.items() if command.requires == "LCD_INIT"]
    assert requiring == LCD_AFTER_INIT


# Form checks: protocol.md section 6

@pytest.mark.parametrize("name", CATALOGUE.names())
def test_defaults_are_accepted(name):
    command = CATALOGUE.commands[name]
    values = {arg.name: default_text(arg) for arg in command.args}
    assert list(CATALOGUE.check(name, values)) == [arg.name for arg in command.args if values[arg.name]]


@pytest.mark.parametrize("name, values", [
    ("QSPI_READ", {"addr": "0xff0000", "len": "32"}),
    ("QSPI_READ", {"addr": "0x0", "len": "1"}),
    ("QSPI_ERASE", {"addr": "0x00FFF000"}),
    ("QSPI_WRITE", {"addr": "0x00FFFFFF", "data": "ab"}),
    ("GPIO_CONFIG", {"port": "K", "pin": "15"}),
    ("LED_SET", {"state": "off"}),
    ("LCD_SCAN", {"ms": "1000"}),
    ("LCD_FILL", {"color": "0xffff"}),
    ("LCD_FILL", {"color": "0x0"}),
    ("LCD_PIXEL", {"x": "479", "y": "271"}),
], ids=["lowercase_hex", "one_digit", "last_block", "last_byte", "last_port_pin", "enum", "max_window",
        "max_color", "short_color", "last_pixel"])
def test_check_accepts(name, values):
    # Sent as typed: the firmware accepts either digit case (section 6.6)
    assert CATALOGUE.check(name, values) == values


def test_empty_optional_argument_is_left_out():
    assert CATALOGUE.check("CAPS", {"start": "  "}) == {}
    assert CATALOGUE.check("CAPS", {}) == {}


def test_values_are_stripped():
    assert CATALOGUE.check("LCD_SCAN", {"ms": " 500 "}) == {"ms": "500"}


@pytest.mark.parametrize("name, values, arg", [
    ("QSPI_READ", {"addr": "0x00FF0000", "len": "04"}, "len"),
    ("QSPI_READ", {"addr": "0x00FF0000", "len": "0"}, "len"),
    ("QSPI_READ", {"addr": "0x00FF0000", "len": "33"}, "len"),
    ("QSPI_READ", {"addr": "00FF0000", "len": "4"}, "addr"),
    ("QSPI_READ", {"addr": "0X00FF0000", "len": "4"}, "addr"),
    ("QSPI_READ", {"addr": "0x123456789", "len": "4"}, "addr"),
    ("QSPI_READ", {"addr": "0x01000000", "len": "4"}, "addr"),
    ("QSPI_ERASE", {"addr": "0x00FF0100"}, "addr"),
    ("QSPI_ERASE", {"addr": "0x00FE0000"}, "addr"),
    ("QSPI_WRITE", {"addr": "0x00FF0000", "data": "ABC"}, "data"),
    ("QSPI_WRITE", {"addr": "0x00FF0000", "data": "00" * 33}, "data"),
    ("QSPI_WRITE", {"addr": "0x00FF0000", "data": "0G"}, "data"),
    ("GPIO_CONFIG", {"port": "L", "pin": "1"}, "port"),
    ("GPIO_CONFIG", {"port": "i", "pin": "1"}, "port"),
    ("GPIO_CONFIG", {"port": "IJ", "pin": "1"}, "port"),
    ("GPIO_CONFIG", {"port": "I", "pin": "16"}, "pin"),
    ("LED_SET", {"state": "ON"}, "state"),
    ("LED_SET", {}, "state"),
    ("LED_SET", {"state": "on", "level": "1"}, "level"),
    ("LCD_SCAN", {"ms": "99"}, "ms"),
    ("LCD_FILL", {"color": "0x10000"}, "color"),
    ("LCD_FILL", {"color": "F800"}, "color"),
    ("LCD_PIXEL", {"x": "480", "y": "0"}, "x"),
    ("LCD_PIXEL", {"x": "0", "y": "272"}, "y"),
], ids=["leading_zero", "len_zero", "len_too_big", "no_prefix", "uppercase_prefix", "nine_digits",
        "beyond_flash", "not_aligned", "below_test_area", "odd_digits", "too_many_bytes", "bad_digit",
        "port_after_k", "lowercase_port", "two_letters", "pin_too_big", "uppercase_enum", "missing",
        "unknown_argument", "window_too_short", "color_too_big", "color_no_prefix", "x_too_big",
        "y_too_big"])
def test_check_rejects(name, values, arg):
    with pytest.raises(ArgumentError) as error:
        CATALOGUE.check(name, values)
    assert error.value.arg == arg


def test_check_unknown_command():
    with pytest.raises(KeyError):
        CATALOGUE.check("NO_SUCH_COMMAND", {})


# Schema: the loader names the faulty field

BASE_ENTRY = """\
  LED_SET:
    group: LED
    summary: Drive LD1
    spec: "6.4"
    args:
      state: {type: enum, values: ["on", "off"]}
"""


def write_catalogue(tmp_path, entries=BASE_ENTRY, version=1):
    path = tmp_path / "commands.yaml"
    path.write_text(f"schema_version: {version}\ncommands:\n{entries}")
    return path


def test_minimal_catalogue_loads(tmp_path):
    assert load(write_catalogue(tmp_path)).names() == ["LED_SET"]


@pytest.mark.parametrize("old, new, field", [
    ('values: ["on", "off"]', "values: [on, off]", "LED_SET.state.values"),
    ("group: LED", "group: LED\n    colour: red", "LED_SET"),
    ("type: enum", "type: float", "LED_SET.state.type"),
    ('values: ["on", "off"]', "default: x", "LED_SET.state"),
    ("group: LED", "group: LED\n    effect: dangerous", "LED_SET.effect"),
    ("group: LED", "group: LED\n    requires: LCD_INIT", "LED_SET.requires"),
    ('values: ["on", "off"]}', 'values: ["on", "off"], default: toggle}', "LED_SET.state.default"),
    ("state:", "id:", "LED_SET.id"),
    ("spec: \"6.4\"", "spec: \"\"", "LED_SET.spec"),
    ("LED_SET:", "led_set:", "led_set"),
], ids=["bare_on_off", "unknown_field", "unknown_type", "missing_parameter", "bad_effect",
        "unknown_requires", "default_not_in_values", "reserved_key", "empty_spec", "lowercase_name"])
def test_load_rejects(tmp_path, old, new, field):
    assert old in BASE_ENTRY
    with pytest.raises(CatalogError, match=f"^{field}"):
        load(write_catalogue(tmp_path, BASE_ENTRY.replace(old, new)))


@pytest.mark.parametrize("arg, field", [
    ("{type: int, min: 1, max: 5, default: 6}", "CMD.n.default"),
    ("{type: int, min: 5, max: 1}", "CMD.n"),
    ("{type: hex, digits: [1, 2], min: 0, max: 0x100}", "CMD.n.max"),
    ("{type: hex, digits: [1, 8], min: 0, max: 0xFF, multiple_of: 0}", "CMD.n.multiple_of"),
    ("{type: hexdata, bytes: [0, 32]}", "CMD.n.bytes"),
    ("{type: letter, min: K, max: A}", "CMD.n"),
    ("{type: color, default: 0x10000}", "CMD.n.default"),
    ("{type: color, default: \"0xF800\"}", "CMD.n.default"),
    ("{type: int, min: 0, max: 9, required: maybe}", "CMD.n.required"),
], ids=["default_out_of_range", "min_above_max", "max_beyond_digits", "zero_step", "zero_bytes",
        "letters_reversed", "color_too_big", "default_as_text", "required_not_boolean"])
def test_load_rejects_argument(tmp_path, arg, field):
    entry = f'  CMD:\n    group: G\n    summary: s\n    spec: "6.1"\n    args:\n      n: {arg}\n'
    with pytest.raises(CatalogError, match=f"^{field}"):
        load(write_catalogue(tmp_path, entry))


def test_load_rejects_schema_version(tmp_path):
    with pytest.raises(CatalogError, match="schema_version"):
        load(write_catalogue(tmp_path, version=2))


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(CatalogError, match="commands.yaml"):
        load(tmp_path / "commands.yaml")
