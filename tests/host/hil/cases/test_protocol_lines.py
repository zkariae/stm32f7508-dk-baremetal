"""Line framing and line errors: protocol.md sections 2.2 to 2.4.

The lines are sent with send_raw(), as bytes a conforming host never sends.
A line error must give exactly one ERROR record (read_records() until the
link is quiet) and leave the next request unaffected, so each error test
ends with a HELLO. A line in error is not a request: it shows the next ID of
the session without using it. The framing error is caused as in
uart_rx_check.py T3: one byte sent at a wrong baud rate in the middle of a
line.

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import pytest

from adapters.serial_adapter import LINE_MAX_LEN

pytestmark = pytest.mark.protocol

FRAME_ERROR_BAUD = 9600  # 0x00 at 9600 baud is a framing error at 115200 (uart_rx.yaml T3)


def hello_line(board) -> str:
    """A HELLO request with the next ID, which a line in error does not use."""
    return f"CMD id={board.adapter.next_id} command=HELLO"


def texts(records) -> list:
    return [record.text for record in records]


def assert_next_request_ok(board) -> None:
    assert board.request("HELLO").ok


@pytest.mark.parametrize("length", [LINE_MAX_LEN + 1, 300])
def test_line_too_long(fresh_board, quiet, length):
    fresh_board.adapter.send_raw(hello_line(fresh_board).ljust(length).encode() + b"\r\n")
    assert texts(fresh_board.adapter.read_records(quiet)) == ["ERROR code=LINE_TOO_LONG"]
    assert_next_request_ok(fresh_board)


def test_line_of_max_length_accepted(fresh_board):
    adapter = fresh_board.adapter
    request_id = adapter.take_id()
    adapter.send_raw(f"CMD id={request_id} command=HELLO".ljust(LINE_MAX_LEN).encode() + b"\r\n")
    assert adapter.read_response(request_id, "HELLO").ok


@pytest.mark.parametrize("bad", [b"\x7f", b"\r"], ids=["del_0x7f", "lone_cr"])
def test_invalid_byte(fresh_board, quiet, bad):
    line = hello_line(fresh_board).encode()
    fresh_board.adapter.send_raw(line[:-3] + bad + line[-3:] + b"\r\n")
    assert texts(fresh_board.adapter.read_records(quiet)) == ["ERROR code=BAD_FRAME"]
    assert_next_request_ok(fresh_board)


def test_framing_error_mid_line(fresh_board, quiet, bench_config):
    adapter = fresh_board.adapter
    line = hello_line(fresh_board).encode()
    adapter.send_raw(line[:12])
    adapter.send_at_baud(b"\x00", FRAME_ERROR_BAUD, bench_config["delays"]["baud_switch_settle"])
    adapter.send_raw(line[12:] + b"\r\n")
    assert texts(adapter.read_records(quiet)) == ["ERROR code=BAD_FRAME"]
    assert_next_request_ok(fresh_board)


def test_lf_alone_accepted(fresh_board):
    assert fresh_board.adapter.transaction("HELLO", eol=b"\n").ok


@pytest.mark.parametrize("blank", [b"\r\n", b"\n", b"    \r\n"], ids=["crlf", "lf", "spaces"])
def test_blank_line_ignored(fresh_board, quiet, blank):
    fresh_board.adapter.send_raw(blank)
    assert fresh_board.adapter.read_records(quiet) == []
    assert_next_request_ok(fresh_board)


def test_multiple_spaces_accepted(fresh_board):
    adapter = fresh_board.adapter
    request_id = adapter.take_id()
    adapter.send_raw(f"  CMD   id={request_id}  command=HELLO   \r\n".encode())
    response = adapter.read_response(request_id, "HELLO")
    assert response.ok
    assert response.fields["name"] == "hil-bench"
