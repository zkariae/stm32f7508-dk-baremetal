"""Fake serial port and fake firmware for the host tests of adapters/, without a board.

FakePort has the pyserial methods SerialAdapter uses. Each write() is kept
(with the baud rate it was sent at) and handed, without its terminator, to a
responder: a function that plays the firmware and returns the bytes of its
answer, which read_until() then gives back. firmware() is the responder of a
conforming hil-bench firmware; a test passes its own responder to make the
firmware misbehave.

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import time

READ_WAIT_MAX = 0.05  # Seconds read_until() waits, like a timeout, when no line is complete


class FakePort:
    """pyserial-like port: write() hands each line to a responder, which queues reply bytes."""

    def __init__(self, responder=None):
        self.responder = responder or (lambda line: b"")
        self.incoming = bytearray()  # Bytes the firmware sent, not read yet
        self.written = []  # Each write, decoded, without its terminator
        self.writes = []  # (baudrate, bytes) of each write
        self.timeout = 1.0
        self.baudrate = 115200

    def write(self, data: bytes) -> int:
        self.writes.append((self.baudrate, bytes(data)))
        line = bytes(data).decode("latin-1").rstrip("\r\n")
        self.written.append(line)
        self.incoming += self.responder(line)
        return len(data)

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self.incoming.clear()

    def read_until(self, expected: bytes = b"\n") -> bytes:
        end = self.incoming.find(expected)
        if end < 0:
            time.sleep(min(self.timeout or 0, READ_WAIT_MAX))  # Nothing complete yet: wait like a timeout
            data, self.incoming[:] = bytes(self.incoming), b""
            return data
        data = bytes(self.incoming[: end + 1])
        del self.incoming[: end + 1]
        return data

    def close(self) -> None:
        pass


def firmware(build: str = "abc1234"):
    """Responder of a conforming hil-bench firmware for HELLO and CAPS."""

    def respond(line: str) -> bytes:
        tokens = line.split()
        request_id = tokens[1].split("=")[1]
        command = tokens[2].split("=")[1]
        if command == "HELLO":
            body = f"RESULT id={request_id} status=OK name=hil-bench proto=1.0 fw=1.0.0 build={build}"
        elif command == "CAPS":
            body = f"RESULT id={request_id} status=OK total=2 start=0 names=HELLO,CAPS"
        else:
            body = f"RESULT id={request_id} status=ERR code=UNKNOWN_COMMAND"
        return f"{body}\r\nEND id={request_id}\r\n".encode()

    return respond
