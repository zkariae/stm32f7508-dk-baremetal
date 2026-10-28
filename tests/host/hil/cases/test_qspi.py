"""QSPI_ID, QSPI_READ, QSPI_ERASE and QSPI_WRITE commands: protocol.md sections 6.6 to 6.10.

Each test starts after the four commands were found in the CAPS list (section
3.4) and block 0 of the test area was erased: the tests assume nothing about
the content left by an earlier session (section 6.6). Writes start at a
multiple of 32 or are split at the page boundary. A rejected request must
leave the flash unchanged (section 7.1): the tests read the target before and
after it. Erase and write are never sent outside the test area except to check
they are rejected. DEVICE_TIMEOUT needs a faulty flash and is not tested here.

Version: 1.0
Date: 28/10/2026
Author: Z. BEN-AKKA
History:
  1.0  28/10/2026  Initial version.
"""

import pytest

from cases.expected import (QSPI_DATA_MAX, QSPI_ERASE_SIZE, QSPI_FLASH_SIZE, QSPI_JEDEC_ID, QSPI_PAGE_SIZE,
                            QSPI_TEST_START)

pytestmark = pytest.mark.qspi

QSPI_COMMANDS = ("QSPI_ID", "QSPI_READ", "QSPI_ERASE", "QSPI_WRITE")
PATTERN = bytes(range(0x10, 0x10 + QSPI_DATA_MAX))  # 32 distinct bytes, none 0xFF


def hex_addr(addr: int) -> str:
    """Address as sent by the host: 0x and eight uppercase digits (section 6.6)."""
    return f"0x{addr:08X}"


def read(board, addr: int, n: int) -> bytes:
    """n bytes from addr, read with QSPI_READ."""
    response = board.request("QSPI_READ", addr=hex_addr(addr), len=n)
    assert response.ok
    return bytes.fromhex(response.fields["data"])


def erase(board, addr: int) -> None:
    """Erase the 4 KB block at addr."""
    assert board.request("QSPI_ERASE", addr=hex_addr(addr)).ok


def write(board, addr: int, data: bytes) -> None:
    """Program data at addr, written in uppercase."""
    assert board.request("QSPI_WRITE", addr=hex_addr(addr), data=data.hex().upper()).ok


def assert_rejected(response) -> None:
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


@pytest.fixture
def qspi(fresh_board):
    """The session board, QSPI commands supported, block 0 of the test area erased."""
    for command in QSPI_COMMANDS:
        fresh_board.require(command)
    erase(fresh_board, QSPI_TEST_START)
    return fresh_board


def test_qspi_id(qspi):
    response = qspi.request("QSPI_ID")
    assert response.ok
    assert response.fields == {"jedec_id": hex_addr(QSPI_JEDEC_ID)}


@pytest.mark.parametrize("n", [1, QSPI_DATA_MAX])
def test_qspi_read(qspi, n):
    response = qspi.request("QSPI_READ", addr="0x0", len=n)  # Outside the test area: reads are allowed
    assert response.ok
    data = response.fields["data"]
    assert len(data) == 2 * n
    assert data == data.upper()
    bytes.fromhex(data)


def test_qspi_read_last_byte(qspi):
    assert len(read(qspi, QSPI_FLASH_SIZE - 1, 1)) == 1


def test_qspi_erase(qspi):
    write(qspi, QSPI_TEST_START, PATTERN)
    erase(qspi, QSPI_TEST_START)
    blank = b"\xff" * QSPI_DATA_MAX
    assert read(qspi, QSPI_TEST_START, QSPI_DATA_MAX) == blank
    assert read(qspi, QSPI_TEST_START + QSPI_ERASE_SIZE - QSPI_DATA_MAX, QSPI_DATA_MAX) == blank


def test_qspi_write_read(qspi):
    write(qspi, QSPI_TEST_START, PATTERN)
    assert read(qspi, QSPI_TEST_START, QSPI_DATA_MAX) == PATTERN


def test_qspi_write_lowercase(qspi):
    assert qspi.request("QSPI_WRITE", addr=hex_addr(QSPI_TEST_START), data="0123abcd").ok
    response = qspi.request("QSPI_READ", addr=hex_addr(QSPI_TEST_START), len=4)
    assert response.fields == {"data": "0123ABCD"}


def test_qspi_write_page_end(qspi):
    page_end = QSPI_TEST_START + QSPI_PAGE_SIZE - 2
    write(qspi, page_end, b"\x01\x02")  # Last two bytes of page 0
    write(qspi, QSPI_TEST_START + QSPI_PAGE_SIZE, b"\x03")  # First byte of page 1
    assert read(qspi, page_end, 3) == b"\x01\x02\x03"
    assert read(qspi, QSPI_TEST_START, 1) == b"\xff"  # No wrap to the start of page 0


def test_qspi_program_clears_bits_only(qspi):
    write(qspi, QSPI_TEST_START, b"\xf0")
    write(qspi, QSPI_TEST_START, b"\x0f")
    assert read(qspi, QSPI_TEST_START, 1) == b"\x00"


def test_qspi_persist_after_reset(qspi):
    write(qspi, QSPI_TEST_START, PATTERN)
    qspi.start_session()
    qspi.require("QSPI_READ")  # New session: CAPS again before any other command
    assert read(qspi, QSPI_TEST_START, QSPI_DATA_MAX) == PATTERN


@pytest.mark.parametrize("args", [
    {"len": 4},
    {"addr": "0x00FF0000"},
    {"addr": "0x00FF0000", "len": 0},
    {"addr": "0x00FF0000", "len": QSPI_DATA_MAX + 1},
    {"addr": "0x00FF0000", "len": "04"},
    {"addr": "0x00FFFFFF", "len": 2},
    {"addr": "0x01000000", "len": 1},
    {"addr": "00FF0000", "len": 4},
    {"addr": "0x000FF0000", "len": 4},
    {"addr": "0xG0", "len": 4},
    {"addr": "0x00FF0000", "len": 4, "x": 1},
], ids=["missing_addr", "missing_len", "len_zero", "len_too_big", "leading_zero", "beyond_flash", "flash_end",
        "no_prefix", "nine_digits", "bad_digit", "extra_argument"])
def test_qspi_read_invalid(qspi, args):
    assert_rejected(qspi.request("QSPI_READ", **args))


@pytest.mark.parametrize("args, check", [
    ({}, QSPI_TEST_START),
    ({"addr": "0x00FF0800"}, QSPI_TEST_START),
    ({"addr": "0x00FEF000"}, 0x00FEF000),
    ({"addr": "0x01000000"}, QSPI_TEST_START),
    ({"addr": "0x00FF0000", "x": 1}, QSPI_TEST_START),
], ids=["missing_addr", "not_aligned", "below_test_area", "beyond_flash", "extra_argument"])
def test_qspi_erase_invalid(qspi, args, check):
    write(qspi, QSPI_TEST_START, PATTERN)  # Not blank: an erase of block 0 would show
    before = read(qspi, check, QSPI_DATA_MAX)
    assert_rejected(qspi.request("QSPI_ERASE", **args))
    assert read(qspi, check, QSPI_DATA_MAX) == before  # Not executed: block unchanged


@pytest.mark.parametrize("args, check", [
    ({"addr": "0x00FF0000"}, QSPI_TEST_START),
    ({"data": "01"}, QSPI_TEST_START),
    ({"addr": "0x00FF0000", "data": "012"}, QSPI_TEST_START),
    ({"addr": "0x00FF0000", "data": "zz"}, QSPI_TEST_START),
    ({"addr": "0x00FF0000", "data": "00" * (QSPI_DATA_MAX + 1)}, QSPI_TEST_START),
    ({"addr": "0x00FF00FE", "data": "000000"}, QSPI_TEST_START + QSPI_PAGE_SIZE - 2),
    ({"addr": "0x00FEFF00", "data": "00"}, 0x00FEFF00),
    ({"addr": "0x00FF0000", "data": "00", "x": 1}, QSPI_TEST_START),
], ids=["missing_data", "missing_addr", "odd_digits", "bad_digit", "too_many_bytes", "page_crossing",
        "below_test_area", "extra_argument"])
def test_qspi_write_invalid(qspi, args, check):
    before = read(qspi, check, QSPI_DATA_MAX)
    assert_rejected(qspi.request("QSPI_WRITE", **args))
    assert read(qspi, check, QSPI_DATA_MAX) == before  # Not executed: bytes unchanged


def test_qspi_outside_area_unchanged(qspi):
    """The start of the flash may hold an application executed in place (section 6.6)."""
    before = read(qspi, 0, QSPI_DATA_MAX)
    assert_rejected(qspi.request("QSPI_ERASE", addr="0x00000000"))
    assert_rejected(qspi.request("QSPI_WRITE", addr="0x00000000", data="00"))
    assert read(qspi, 0, QSPI_DATA_MAX) == before


def test_qspi_id_argument(qspi):
    assert_rejected(qspi.request("QSPI_ID", x=1))
