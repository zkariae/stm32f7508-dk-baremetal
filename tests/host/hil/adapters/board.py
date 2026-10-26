"""Protocol sessions with the hil-bench board: startup, identity, capabilities, recovery.

Implements the host side of protocol.md sections 3.4, 4, 5.1, 6.2, 6.3 and 8.3:
- start_session(): drop stale input, reset the board, wait for a valid READY
  within the startup timeout (lines that are not a valid banner are ignored,
  for example the tail of a banner sent before the port was flushed), check
  the protocol major version and restart the IDs at 1;
- request(): one transaction, starting a new session first once ID 65535 has
  been used;
- identify(): HELLO, whose values must equal the banner's, and the build
  check against the expected build;
- capabilities(): every CAPS page, with the checks of section 6.3;
- recover(): the recovery procedure of section 8.3.

Version: 1.0
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
"""

import logging
import re
import time
from dataclasses import dataclass

from adapters.outcomes import (BuildMismatch, FunctionalError, IncompatibleProtocol, ProtocolFailure,
                               StartupFailure, UnsupportedCommand)
from adapters.serial_adapter import ID_MAX, ID_MIN, RecordError, Response, parse_record

SUPPORTED_MAJOR = 1  # Protocol major version this host implements (section 3.4)
REQUIRED_COMMANDS = ("HELLO", "CAPS")  # Every conforming firmware has them (sections 6.2 and 6.3)
HELLO_FIELDS = ("name", "proto", "fw", "build")

# Readiness banner fields, in order, with their formats (section 4.1)
BANNER_FORMATS = {
    "name": re.compile(r"[a-z0-9-]{1,16}"),
    "fw": re.compile(r"(?=.{1,16}$)\d+\.\d+\.\d+"),
    "proto": re.compile(r"(?=.{1,7}$)\d+\.\d+"),
    "build": re.compile(r"[0-9a-f]{7,12}(-dirty)?|unknown"),
    "reset": re.compile(r"LPWR|WWDG|IWDG|SW|POR|BOR|PIN|unknown"),
    "reset_flags": re.compile(r"0x[0-9A-F]{8}"),
}
COMMAND_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{0,31}")  # Section 6.1
DECIMAL_RE = re.compile(r"0|[1-9][0-9]*")

log = logging.getLogger("hil.board")


@dataclass(frozen=True)
class Banner:
    """A valid readiness banner."""

    text: str
    name: str
    fw: str
    proto: str
    build: str
    reset: str
    reset_flags: int


def parse_banner(line: str) -> Banner | None:
    """Return the banner if line is a valid READY record (section 4.1), otherwise None."""
    try:
        record = parse_record(line)
    except RecordError:
        return None
    if record.type != "READY":
        return None
    known = [key for key in record.keys() if key in BANNER_FORMATS]  # Unknown fields are ignored
    if known != list(BANNER_FORMATS):
        return None
    values = {key: record.get(key) for key in BANNER_FORMATS}
    if not all(BANNER_FORMATS[key].fullmatch(value) for key, value in values.items()):
        return None
    values["reset_flags"] = int(values["reset_flags"], 16)
    return Banner(line, **values)


def _decimal(response: Response, key: str) -> int:
    value = response.fields.get(key)
    if value is None or not DECIMAL_RE.fullmatch(value):
        raise ProtocolFailure(f"CAPS {key}={value} is not a decimal integer")
    return int(value)


class Board:
    """The board seen through the protocol: one session at a time."""

    def __init__(self, adapter, programmer, startup_timeout: float, settle: float,
                 expected_build: str | None = None, accept_build_mismatch: bool = False):
        self.adapter = adapter
        self.programmer = programmer
        self.startup_timeout = startup_timeout
        self.settle = settle  # Time given to stale input to arrive before the reset
        self.expected_build = expected_build  # None: no build check
        self.accept_build_mismatch = accept_build_mismatch
        self.banner = None  # Banner of the current session
        self._names = None  # CAPS list of the current session

    def start_session(self) -> Banner:
        """Reset the board and wait for its readiness banner (sections 4.1 and 3.4)."""
        self.banner = None
        self._names = None
        self._drain()
        self.programmer.reset()

        deadline = time.monotonic() + self.startup_timeout
        while True:
            line = self.adapter.read_line(deadline)
            if line is None:
                raise StartupFailure(f"no valid READY within {self.startup_timeout} s after the reset")
            banner = parse_banner(line)
            if banner is not None:
                break
            log.info("ignored during startup: %r", line)

        major = int(banner.proto.split(".")[0])
        if major != SUPPORTED_MAJOR:
            raise IncompatibleProtocol(f"firmware proto={banner.proto}, host supports {SUPPORTED_MAJOR}.x")
        self.adapter.next_id = ID_MIN
        self.banner = banner
        log.info("session started: %s", banner.text)
        return banner

    def recover(self) -> Banner:
        """Recovery procedure of section 8.3; StartupFailure means the run must stop."""
        log.warning("recovery: flush, reset and wait for a new banner")
        return self.start_session()

    def request(self, command: str, **args) -> Response:
        """Send one request in the current session."""
        if self.banner is None:
            raise RuntimeError("no session: call start_session() first")
        if self.adapter.next_id > ID_MAX:
            log.info("ID %d used: new session (section 5.1)", ID_MAX)
            self.start_session()
        return self.adapter.transaction(command, args)

    def identify(self) -> Response:
        """HELLO: same values as the banner, and the expected build (section 6.2)."""
        response = self.request("HELLO")
        if not response.ok:
            raise FunctionalError(f"HELLO answered status=ERR code={response.code}")
        for key in HELLO_FIELDS:
            if response.fields.get(key) != getattr(self.banner, key):
                raise ProtocolFailure(
                    f"HELLO {key}={response.fields.get(key)} differs from the banner {key}={getattr(self.banner, key)}"
                )
        build = response.fields["build"]
        if self.expected_build is not None and build != self.expected_build:
            mismatch = BuildMismatch(f"firmware build={build}, expected {self.expected_build}")
            if not self.accept_build_mismatch:
                raise mismatch
            log.warning("%s (accepted by bench.yaml)", mismatch)
        return response

    def capabilities(self) -> list:
        """Every CAPS page, checked against section 6.3."""
        names = []
        total = None
        start = 0
        while True:
            response = self.request("CAPS", start=start)
            if not response.ok:
                raise FunctionalError(f"CAPS start={start} answered status=ERR code={response.code}")
            page_total = _decimal(response, "total")
            if total is None:
                if not 2 <= page_total <= 255:
                    raise ProtocolFailure(f"CAPS total={page_total} outside 2 to 255")
                total = page_total
            elif page_total != total:
                raise ProtocolFailure(f"CAPS total changed from {total} to {page_total}")
            if _decimal(response, "start") != start:
                raise ProtocolFailure(f"CAPS start={response.fields.get('start')} for a request with start={start}")
            page = response.fields.get("names", "").split(",")
            for name in page:
                if not COMMAND_NAME_RE.fullmatch(name):
                    raise ProtocolFailure(f"CAPS name {name!r} is not a command name")
                if name in names:
                    raise ProtocolFailure(f"CAPS lists {name} twice")
                names.append(name)
            if "next" not in response.fields:
                break
            next_start = _decimal(response, "next")
            if next_start != start + len(page):
                raise ProtocolFailure(f"CAPS next={next_start} after {len(page)} names from start={start}")
            start = next_start

        if len(names) != total:
            raise ProtocolFailure(f"CAPS gave {len(names)} names for total={total}")
        missing = [name for name in REQUIRED_COMMANDS if name not in names]
        if missing:
            raise ProtocolFailure(f"CAPS list lacks {', '.join(missing)}")
        self._names = names
        return names

    def require(self, command: str) -> None:
        """Raise UnsupportedCommand if the firmware does not list command in CAPS."""
        if self._names is None:
            self.capabilities()
        if command not in self._names:
            raise UnsupportedCommand(f"{command} is not in the CAPS list {self._names}")

    def _drain(self) -> None:
        """Drop input, then whatever stale bytes arrive within settle (old banners, partial lines)."""
        self.adapter.flush_input()
        deadline = time.monotonic() + self.settle
        while (line := self.adapter.read_line(deadline)) is not None:
            log.info("dropped before the reset: %r", line)
        self.adapter.flush_input()
