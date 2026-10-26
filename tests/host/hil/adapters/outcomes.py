"""Host outcomes of protocol.md section 7.3, raised as exceptions.

Each failure outcome is an exception whose message starts with the outcome
name, so a pytest failure report shows it first. PASS is the absence of an
exception. FUNCTIONAL_ERROR is raised by the test cases themselves when a
command answers status=ERR or unexpected values.

Version: 1.0
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
"""


class HilOutcome(Exception):
    """A session or test case outcome other than PASS."""

    outcome = "PROTOCOL_FAILURE"

    def __str__(self) -> str:
        detail = super().__str__()
        return f"{self.outcome}: {detail}" if detail else self.outcome


class ProgrammingFailure(HilOutcome):
    """Building, programming or resetting the board failed."""

    outcome = "PROGRAMMING_FAILURE"


class StartupFailure(HilOutcome):
    """No valid readiness banner before the startup timeout."""

    outcome = "STARTUP_FAILURE"


class IncompatibleProtocol(HilOutcome):
    """The banner's protocol major version is not the host's (section 3.4)."""

    outcome = "INCOMPATIBLE_PROTOCOL"


class BuildMismatch(HilOutcome):
    """The build value differs from the expected build identifier (section 6.2)."""

    outcome = "BUILD_MISMATCH"


class UnsupportedCommand(HilOutcome):
    """A required command is not in the list returned by CAPS."""

    outcome = "UNSUPPORTED_COMMAND"


class UnexpectedReset(HilOutcome):
    """A readiness banner arrived during an active session (section 4.3)."""

    outcome = "UNEXPECTED_RESET"

    def __init__(self, message: str, banner_line: str = ""):
        super().__init__(message)
        self.banner_line = banner_line  # Its reset fields go into the report


class ProtocolFailure(HilOutcome):
    """A record violated the protocol, an ERROR record arrived, or a response timed out."""

    outcome = "PROTOCOL_FAILURE"


class FunctionalError(HilOutcome):
    """status=ERR, or status=OK with values other than the test case expects."""

    outcome = "FUNCTIONAL_ERROR"
