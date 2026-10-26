"""Exchange protocol records with the hil-bench firmware over the serial link.

Implements the host side of protocol.md sections 2, 5.1 and 5.2:
- read_line() returns one received line without its terminator (LF, with
  one CR before it removed); parse_record() checks it against sections 2.2
  and 2.3;
- transaction() sends CMD with the next ID of the session and waits for
  RESULT then END within the response timeout. Any other record, a wrong ID,
  END before RESULT, a second RESULT, an ERROR record or the timeout raise
  ProtocolFailure (section 5.2.3); a READY record raises UnexpectedReset
  (section 4.3).
For the conformance tests, lower-level calls drive the link the way a
conforming host never does: send_raw() sends bytes as they are, send_at_baud()
sends them at another baud rate to cause a UART framing error (as
uart_rx_check.py T3), and read_records() returns every record received until
the link stays silent, ERROR records included. take_id() and read_response()
are the two halves of transaction(), for a raw request with a valid ID.
Every line sent and received is logged at INFO on the hil.serial logger, as
text, or as escaped bytes when it holds a byte outside 0x20-0x7E; pytest
--log-cli-level=INFO shows them live in the terminal.

Version: 1.2
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
  1.1  26/10/2026  Log TX and RX lines at INFO, non-printable bytes escaped.
  1.2  26/10/2026  Add raw bytes, other baud rates and reading records until silence.
"""

import logging
import re
import time
from dataclasses import dataclass

from adapters.outcomes import ProtocolFailure, UnexpectedReset

LINE_MAX_LEN = 128  # Bytes, without the terminator (section 2.2)
ID_MIN = 1
ID_MAX = 65535
PENDING_MAX = 4 * LINE_MAX_LEN  # A line still unterminated past this is returned as is

TYPE_RE = re.compile(r"[A-Z]+")
KEY_RE = re.compile(r"[a-z][a-z0-9_]*")
VALUE_RE = re.compile(r"[\x21-\x3c\x3e-\x7e]+")  # Printable, without space and '='
RESULT_RESERVED = ("id", "status", "code")

log = logging.getLogger("hil.serial")


def show(data: bytes) -> str:
    """Log form of a line: its text if printable ASCII, else the escaped bytes."""
    if all(0x20 <= byte <= 0x7E for byte in data):
        return data.decode("ascii")
    return repr(data)


class RecordError(ValueError):
    """A line that is not a valid record (sections 2.2 and 2.3)."""


class SessionExhausted(RuntimeError):
    """ID 65535 was used: the board must be reset before the next request (section 5.1)."""


@dataclass(frozen=True)
class Record:
    """One received record."""

    text: str  # The line as received
    type: str
    fields: tuple  # ((key, value), ...) in received order

    def keys(self) -> list:
        return [key for key, _ in self.fields]

    def get(self, key: str, default=None):
        return next((value for name, value in self.fields if name == key), default)


@dataclass(frozen=True)
class Response:
    """Outcome of one transaction: the RESULT record without its reserved fields."""

    id: int
    status: str  # OK or ERR
    code: str | None  # Response code when status is ERR
    fields: dict  # Result fields after the reserved ones

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def parse_record(line: str) -> Record:
    """Check a line against sections 2.2 and 2.3 and split it into fields."""
    if len(line) > LINE_MAX_LEN:
        raise RecordError(f"{len(line)} bytes, more than {LINE_MAX_LEN}")
    bad = next((char for char in line if not 0x20 <= ord(char) <= 0x7E), None)
    if bad is not None:
        raise RecordError(f"byte 0x{ord(bad):02X} outside 0x20-0x7E")
    tokens = line.split()  # One or more spaces between tokens are accepted
    if not tokens:
        raise RecordError("empty line")
    if not TYPE_RE.fullmatch(tokens[0]):
        raise RecordError(f"type {tokens[0]!r} is not uppercase letters")
    fields = []
    for token in tokens[1:]:
        key, equal, value = token.partition("=")
        if not equal or not KEY_RE.fullmatch(key) or not VALUE_RE.fullmatch(value):
            raise RecordError(f"field {token!r} is not key=value")
        if any(key == name for name, _ in fields):
            raise RecordError(f"key {key!r} appears twice")
        fields.append((key, value))
    return Record(line, tokens[0], tuple(fields))


def format_request(request_id: int, command: str, args: dict) -> str:
    """Write a CMD record (section 5.1)."""
    tokens = ["CMD", f"id={request_id}", f"command={command}"]
    tokens += [f"{key}={value}" for key, value in args.items()]
    line = " ".join(tokens)
    parse_record(line)  # A request the host cannot send is a test bug
    return line


class SerialAdapter:
    """Protocol link to the firmware, on an open pyserial port."""

    def __init__(self, port, response_timeout: float):
        self._port = port
        self.response_timeout = response_timeout
        self.next_id = ID_MIN  # ID of the next request in the session
        self._pending = b""  # Bytes received after the last complete line

    @classmethod
    def open(cls, serial_config: dict, response_timeout: float, port: str | None = None):
        """Open the port described by the serial section of bench.yaml."""
        import serial  # pyserial; imported here so the parsers need no serial port

        parities = {"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN, "odd": serial.PARITY_ODD}
        link = serial.serial_for_url(
            port or serial_config["port"],
            baudrate=serial_config["baudrate"],
            bytesize=serial_config["bytesize"],
            parity=parities[serial_config["parity"]],
            stopbits=serial_config["stopbits"],
            timeout=response_timeout,
            write_timeout=response_timeout,
            xonxoff=serial_config["flow_control"] == "xonxoff",
            rtscts=serial_config["flow_control"] == "rtscts",
            dsrdtr=False,
        )
        return cls(link, response_timeout)

    def close(self) -> None:
        self._port.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def flush_input(self) -> None:
        """Drop every received byte not read yet."""
        self._port.reset_input_buffer()
        self._pending = b""

    def send_line(self, line: str, eol: bytes = b"\r\n") -> None:
        data = line.encode("ascii") + eol
        log.info("TX  %s", line if eol == b"\r\n" else repr(data))
        self._write(data)

    def send_raw(self, data: bytes) -> None:
        """Send bytes as they are, terminator included: lines a conforming host never sends."""
        log.info("TX  %r", data)
        self._write(data)

    def send_at_baud(self, data: bytes, baudrate: int, settle: float) -> None:
        """Send data at another baud rate, then restore the link's and drop input (uart_rx_check.py T3)."""
        normal = self._port.baudrate
        time.sleep(settle)  # Let the bridge send what is queued at the normal rate
        log.info("TX  %r at %d baud", data, baudrate)
        self._port.baudrate = baudrate
        self._write(data)
        time.sleep(settle)  # flush() returns once the USB bridge holds the data, not once it is on the wire
        self._port.baudrate = normal
        time.sleep(settle)  # Let the bridge apply the restored baud rate
        self.flush_input()  # Drop switch glitches; the firmware reports errors at the next terminator

    def _write(self, data: bytes) -> None:
        self._port.write(data)
        self._port.flush()

    def read_line(self, deadline: float) -> str | None:
        """Return the next received line, or None if none ends before deadline (time.monotonic())."""
        while True:
            end = self._pending.find(b"\n")
            if end >= 0 or len(self._pending) > PENDING_MAX:
                if end < 0:
                    end = len(self._pending)  # Never terminated: let the caller reject it
                raw, self._pending = self._pending[:end], self._pending[end + 1 :]
                if raw.endswith(b"\r"):
                    raw = raw[:-1]
                log.info("RX  %s", show(raw))
                return raw.decode("latin-1")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._port.timeout = remaining
            self._pending += self._port.read_until(b"\n")

    def read_record(self, deadline: float) -> Record | None:
        """Return the next non-blank record, or None at deadline; an invalid line is a ProtocolFailure."""
        while True:
            line = self.read_line(deadline)
            if line is None:
                return None
            if not line.strip(" "):
                continue  # Blank lines are ignored (section 2.2)
            try:
                return parse_record(line)
            except RecordError as error:
                raise ProtocolFailure(f"invalid record {line!r}: {error}") from None

    def read_records(self, quiet: float) -> list:
        """Every record received until no line arrives for quiet seconds; ERROR and READY included."""
        records = []
        while (record := self.read_record(time.monotonic() + quiet)) is not None:
            records.append(record)
        return records

    def take_id(self) -> int:
        """ID of the next request, marked as used (section 5.1)."""
        if self.next_id > ID_MAX:
            raise SessionExhausted("ID 65535 already used in this session")
        request_id = self.next_id
        self.next_id += 1
        return request_id

    def transaction(self, command: str, args: dict | None = None, timeout: float | None = None,
                    eol: bytes = b"\r\n") -> Response:
        """Send one request and return its response (sections 5.1 and 5.2); eol=b"\\n" sends LF alone."""
        request_id = self.take_id()
        self.send_line(format_request(request_id, command, args or {}), eol)
        return self.read_response(request_id, command, timeout)

    def read_response(self, request_id: int, command: str, timeout: float | None = None) -> Response:
        """Wait for RESULT then END of request_id (section 5.2.3); command only names it in failures."""
        limit = self.response_timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        result = None
        while True:
            record = self.read_record(deadline)
            if record is None:
                raise ProtocolFailure(f"no END for id={request_id} ({command}) within {limit} s")
            if record.type == "READY":
                raise UnexpectedReset(f"READY during id={request_id} ({command})", record.text)
            if record.type == "ERROR":
                raise ProtocolFailure(f"{record.text!r} while id={request_id} ({command}) was outstanding")
            if record.type == "RESULT":
                if result is not None:
                    raise ProtocolFailure(f"second RESULT for id={request_id}: {record.text!r}")
                result = self._check_result(record, request_id)
            elif record.type == "END":
                if record.fields != (("id", str(request_id)),):
                    raise ProtocolFailure(f"END is not 'END id={request_id}': {record.text!r}")
                if result is None:
                    raise ProtocolFailure(f"END before RESULT for id={request_id}")
                return result
            else:
                raise ProtocolFailure(f"unexpected {record.type} record: {record.text!r}")

    @staticmethod
    def _check_result(record: Record, request_id: int) -> Response:
        """Check the reserved fields of RESULT (section 5.2.1)."""
        keys = record.keys()
        if keys[:2] != ["id", "status"]:
            raise ProtocolFailure(f"RESULT does not start with id and status: {record.text!r}")
        if record.get("id") != str(request_id):
            raise ProtocolFailure(f"RESULT id differs from {request_id}: {record.text!r}")
        status = record.get("status")
        if status == "ERR":
            if len(keys) < 3 or keys[2] != "code":
                raise ProtocolFailure(f"RESULT status=ERR without code third: {record.text!r}")
            code, extra = record.get("code"), record.fields[3:]
        elif status == "OK":
            code, extra = None, record.fields[2:]
        else:
            raise ProtocolFailure(f"RESULT status is neither OK nor ERR: {record.text!r}")
        if any(key in RESULT_RESERVED for key, _ in extra):
            raise ProtocolFailure(f"RESULT uses a reserved key as a result field: {record.text!r}")
        return Response(request_id, status, code, dict(extra))
