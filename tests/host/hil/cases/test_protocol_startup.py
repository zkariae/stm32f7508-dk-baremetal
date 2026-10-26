"""Readiness banner and reset cause: protocol.md sections 4.1 and 4.2.

Each test starts its own session. make reset drives NRST, so the banner
reports PIN; make reset-sw writes SYSRESETREQ, which also drives NRST, so
the banner reports SW with both SFTRSTF and PINRSTF set (section 4.2 note).

Version: 1.0
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
"""

import pytest

from adapters.serial_adapter import parse_record

pytestmark = pytest.mark.protocol

BANNER_KEYS = ["name", "fw", "proto", "build", "reset", "reset_flags"]  # Section 4.1 order
PINRSTF = 0x04000000
SFTRSTF = 0x10000000
SECOND_BANNER_WAIT = 1.0  # Seconds without a second READY after the first


def test_banner_fields_in_order(fresh_board):
    banner = fresh_board.start_session()
    record = parse_record(banner.text)
    assert record.type == "READY"
    assert record.keys() == BANNER_KEYS
    assert banner.name == "hil-bench"


def test_pin_reset(fresh_board):
    banner = fresh_board.start_session()
    assert banner.reset == "PIN"
    assert banner.reset_flags == PINRSTF


def test_software_reset(fresh_board, monkeypatch):
    monkeypatch.setattr(fresh_board.programmer, "reset", fresh_board.programmer.reset_sw)
    banner = fresh_board.start_session()
    assert banner.reset == "SW"
    assert banner.reset_flags == SFTRSTF | PINRSTF


def test_one_banner_per_boot(fresh_board):
    fresh_board.start_session()
    assert fresh_board.adapter.read_records(SECOND_BANNER_WAIT) == []
