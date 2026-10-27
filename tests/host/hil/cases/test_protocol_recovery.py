"""Unexpected reset, startup failure and ID rollover: protocol.md sections 4.3, 5.1 and 8.3.

A reset behind the session's back must fail the next transaction with
UNEXPECTED_RESET; a reset without a banner must give STARTUP_FAILURE. In both
cases the recovery procedure starts a new session, whose first request has
ID 1. After ID 65535, the host resets the board before the next request.

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import pytest

from adapters.board import parse_banner
from adapters.outcomes import StartupFailure, UnexpectedReset
from adapters.serial_adapter import ID_MAX, ID_MIN

pytestmark = pytest.mark.protocol

NO_BANNER_TIMEOUT = 1.0  # Seconds; no banner comes, so the 5 s of section 8.1 add nothing


def test_reset_during_session(fresh_board):
    assert fresh_board.request("HELLO").ok
    fresh_board.programmer.reset()  # Behind the session's back
    with pytest.raises(UnexpectedReset) as reset:
        fresh_board.request("HELLO")
    assert parse_banner(reset.value.banner_line).reset == "PIN"
    fresh_board.recover()
    response = fresh_board.request("HELLO")
    assert response.ok
    assert response.id == ID_MIN


def test_no_banner_is_startup_failure(fresh_board, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(fresh_board.programmer, "reset", lambda: None)  # A reset that does nothing
        patch.setattr(fresh_board, "startup_timeout", NO_BANNER_TIMEOUT)
        with pytest.raises(StartupFailure):
            fresh_board.start_session()
    fresh_board.recover()
    response = fresh_board.request("HELLO")
    assert response.ok
    assert response.id == ID_MIN


def test_new_session_after_id_65535(fresh_board):
    fresh_board.adapter.next_id = ID_MAX
    assert fresh_board.request("HELLO").id == ID_MAX
    banner = fresh_board.banner
    response = fresh_board.request("HELLO")
    assert response.ok
    assert response.id == ID_MIN
    assert fresh_board.banner is not banner  # A new session started
