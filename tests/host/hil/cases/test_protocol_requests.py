"""Request checks: protocol.md sections 5.1, 5.2 and 7.

The requests are sent with send_raw(), since format_request() refuses to
write them. Without CMD and a valid id there is no request to answer: the
firmware sends an uncorrelated ERROR code=BAD_FRAME (section 5.2.2). With a
valid id, any other fault gets a correlated RESULT status=ERR code=BAD_REQUEST
(section 5.2.1), and a command the firmware does not have gets
UNKNOWN_COMMAND (section 7.1). Each test ends with a HELLO that must succeed.

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import pytest

pytestmark = pytest.mark.protocol

BAD_FRAMES = {
    "id_zero": "CMD id=0 command=HELLO",
    "id_above_max": "CMD id=65536 command=HELLO",
    "id_leading_zero": "CMD id=01 command=HELLO",
    "id_negative": "CMD id=-1 command=HELLO",
    "id_missing": "CMD command=HELLO",
    "not_cmd": "REQ id=1 command=HELLO",
}

BAD_REQUESTS = {  # What follows CMD id=<id>
    "command_missing": "",
    "command_not_third": "start=0 command=CAPS",
    "duplicate_key": "command=CAPS start=0 start=1",
    "reserved_key_id": "command=HELLO id=2",
    "reserved_key_command": "command=HELLO command=CAPS",
    "token_without_equal": "command=HELLO verbose",
}


def assert_next_request_ok(board) -> None:
    assert board.request("HELLO").ok


@pytest.mark.parametrize("line", BAD_FRAMES.values(), ids=BAD_FRAMES.keys())
def test_bad_frame(fresh_board, quiet, line):
    fresh_board.adapter.send_raw(line.encode() + b"\r\n")
    assert [record.text for record in fresh_board.adapter.read_records(quiet)] == ["ERROR code=BAD_FRAME"]
    assert_next_request_ok(fresh_board)


@pytest.mark.parametrize("rest", BAD_REQUESTS.values(), ids=BAD_REQUESTS.keys())
def test_bad_request(fresh_board, rest):
    adapter = fresh_board.adapter
    request_id = adapter.take_id()
    adapter.send_raw(f"CMD id={request_id} {rest}".rstrip().encode() + b"\r\n")
    response = adapter.read_response(request_id, "malformed request")
    assert (response.status, response.code) == ("ERR", "BAD_REQUEST")
    assert_next_request_ok(fresh_board)


@pytest.mark.parametrize("command", ["NO_SUCH_COMMAND", "hello"])
def test_unknown_command(fresh_board, command):
    response = fresh_board.request(command)
    assert (response.status, response.code) == ("ERR", "UNKNOWN_COMMAND")
