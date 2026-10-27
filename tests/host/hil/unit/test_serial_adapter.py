"""Host tests of adapters/serial_adapter.py against a fake firmware (unit/hil_fake.py).

No board: the fake firmware answers right or wrong on purpose, and each test
checks that the adapter accepts a conforming record and raises the outcome of
protocol.md section 7.3 for each violation of sections 2, 4.3 and 5. The
lower-level calls of the conformance tests (send_raw, send_at_baud,
read_records, take_id, read_response) are checked too.

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import time

import pytest

from adapters.outcomes import ProtocolFailure, UnexpectedReset
from adapters.serial_adapter import RecordError, SerialAdapter, SessionExhausted, format_request, parse_record
from unit.hil_fake import FakePort, firmware

pytestmark = pytest.mark.unit

BANNER = "READY name=hil-bench fw=1.0.0 proto=1.0 build=abc1234 reset=PIN reset_flags=0x04000000"


def adapter(responder=None, timeout=0.3) -> SerialAdapter:
    return SerialAdapter(FakePort(responder), timeout)


def reply(*lines):
    """Responder that answers any request with these lines."""
    return lambda line: "".join(f"{text}\r\n" for text in lines).encode()


def soon(seconds=0.5) -> float:
    return time.monotonic() + seconds


# parse_record and format_request: sections 2.2, 2.3 and 5.1

def test_parse_ok():
    record = parse_record("RESULT id=1 status=OK name=hil-bench")
    assert record.type == "RESULT"
    assert record.keys() == ["id", "status", "name"]


def test_parse_multiple_spaces_accepted():
    assert parse_record("  END   id=3 ").fields == (("id", "3"),)


@pytest.mark.parametrize("line", [
    "A" * 129, "END id=1\x7f", "end id=1", "END id", "END id=", "END =1", "END id=a=b",
    "END id=1 id=2", "END Id=1", "",
], ids=["too_long", "del_0x7f", "lowercase_type", "no_equal", "empty_value", "empty_key", "equal_in_value",
        "duplicate_key", "uppercase_key", "empty_line"])
def test_parse_rejects(line):
    with pytest.raises(RecordError):
        parse_record(line)


def test_format_request():
    assert format_request(7, "CAPS", {"start": 1}) == "CMD id=7 command=CAPS start=1"


# read_line: section 2.2

def test_read_line_lf_only_and_crlf():
    link = adapter()
    link._port.incoming += b"ONE\nTWO\r\n"
    assert link.read_line(soon()) == "ONE"
    assert link.read_line(soon()) == "TWO"


def test_read_line_partial_then_complete():
    link = adapter()
    link._port.incoming += b"REA"
    assert link.read_line(soon(0.1)) is None
    link._port.incoming += b"DY x=1\r\n"
    assert link.read_line(soon()) == "READY x=1"


# transaction: sections 4.3, 5.1 and 5.2

def test_hello_ok_and_ids_increment():
    link = adapter(firmware())
    first = link.transaction("HELLO")
    second = link.transaction("CAPS")
    assert first.ok and first.id == 1 and first.fields["build"] == "abc1234"
    assert second.id == 2 and second.fields["names"] == "HELLO,CAPS"
    assert link._port.written == ["CMD id=1 command=HELLO", "CMD id=2 command=CAPS"]


def test_err_response():
    response = adapter(reply("RESULT id=1 status=ERR code=UNKNOWN_COMMAND", "END id=1")).transaction("FOO")
    assert not response.ok
    assert response.code == "UNKNOWN_COMMAND"
    assert response.fields == {}


def test_blank_lines_ignored():
    assert adapter(reply("", "RESULT id=1 status=OK", "   ", "END id=1")).transaction("HELLO").ok


@pytest.mark.parametrize("lines, message", [
    (("RESULT id=2 status=OK", "END id=2"), "id differs"),
    (("END id=1",), "END before RESULT"),
    (("RESULT id=1 status=OK", "RESULT id=1 status=OK", "END id=1"), "second RESULT"),
    (("ERROR code=BAD_FRAME",), "ERROR"),
    (("RESULT id=1 status=OK", "END id=2"), "END is not"),
    (("RESULT id=1 status=OK", "END id=1 x=1"), "END is not"),
    (("RESULT status=OK id=1", "END id=1"), "does not start"),
    (("RESULT id=1 status=ERR", "END id=1"), "without code"),
    (("RESULT id=1 status=ERR x=1 code=A", "END id=1"), "without code"),
    (("RESULT id=1 status=OK code=A", "END id=1"), "reserved"),
    (("RESULT id=1 status=MAYBE", "END id=1"), "neither"),
    (("RESULT id=1 status=OK",), "no END"),
    ((), "no END"),
    (("HELLO x=1",), "unexpected HELLO"),
    (("RESULT id=1 status=OK bad",), "invalid record"),
])
def test_protocol_failures(lines, message):
    with pytest.raises(ProtocolFailure, match=message):
        adapter(reply(*lines), timeout=0.2).transaction("HELLO")


def test_ready_is_unexpected_reset():
    with pytest.raises(UnexpectedReset) as reset:
        adapter(reply(BANNER)).transaction("HELLO")
    assert reset.value.banner_line == BANNER


def test_session_exhausted_after_65535():
    link = adapter(firmware())
    link.next_id = 65535
    assert link.transaction("HELLO").id == 65535
    with pytest.raises(SessionExhausted):
        link.transaction("HELLO")


# Lower-level calls of the conformance tests

def test_send_raw_writes_bytes_unchanged():
    link = adapter()
    link.send_raw(b"CMD id=1 command=HE\x7fLLO\r\n")
    assert link._port.writes == [(115200, b"CMD id=1 command=HE\x7fLLO\r\n")]


def test_read_records_until_silence():
    link = adapter()
    link._port.incoming += b"ERROR code=BAD_FRAME\r\n\r\nERROR code=LINE_TOO_LONG\n"
    assert [record.text for record in link.read_records(0.1)] == ["ERROR code=BAD_FRAME",
                                                                  "ERROR code=LINE_TOO_LONG"]
    assert link.read_records(0.1) == []


def test_read_records_invalid_line():
    link = adapter()
    link._port.incoming += b"garbage line\r\n"
    with pytest.raises(ProtocolFailure, match="invalid record"):
        link.read_records(0.1)


def test_send_at_baud_restores_the_baud_rate():
    link = adapter()
    link._port.incoming += b"glitch"
    link.send_at_baud(b"\x00", 9600, 0)
    assert link._port.writes == [(9600, b"\x00")]
    assert link._port.baudrate == 115200
    assert link._port.incoming == b""


def test_transaction_lf_alone():
    link = adapter(firmware())
    assert link.transaction("HELLO", eol=b"\n").ok
    assert link._port.writes == [(115200, b"CMD id=1 command=HELLO\n")]


def test_take_id_and_read_response():
    link = adapter(firmware())
    request_id = link.take_id()
    assert (request_id, link.next_id) == (1, 2)
    link.send_raw(f"  CMD   id={request_id}  command=HELLO  \r\n".encode())
    assert link.read_response(request_id, "HELLO").ok


def test_take_id_after_65535():
    link = adapter()
    link.next_id = 65536
    with pytest.raises(SessionExhausted):
        link.take_id()
