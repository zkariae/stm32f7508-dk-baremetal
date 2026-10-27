"""HELLO command: protocol.md section 6.2.

HELLO takes no argument and returns name, proto, fw and build, equal to the
readiness banner. The build check against the expected build is a host rule:
the tests force a wrong expected value to see BUILD_MISMATCH, raised or only
logged when the bench configuration accepts it.

Version: 1.0
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
"""

import pytest

from adapters.board import HELLO_FIELDS
from adapters.outcomes import BuildMismatch

pytestmark = pytest.mark.protocol

WRONG_BUILD = "0000000"  # Valid build format, never the flashed image's


def test_hello_ok(fresh_board):
    response = fresh_board.request("HELLO")
    assert response.ok
    assert sorted(response.fields) == sorted(HELLO_FIELDS)


def test_hello_values_equal_banner(fresh_board):
    response = fresh_board.request("HELLO")
    for key in HELLO_FIELDS:
        assert response.fields[key] == getattr(fresh_board.banner, key)


def test_hello_rejects_argument(fresh_board):
    response = fresh_board.request("HELLO", verbose=1)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


def test_build_mismatch(fresh_board, monkeypatch):
    monkeypatch.setattr(fresh_board, "expected_build", WRONG_BUILD)
    monkeypatch.setattr(fresh_board, "accept_build_mismatch", False)
    with pytest.raises(BuildMismatch, match=f"expected {WRONG_BUILD}"):
        fresh_board.identify()


def test_build_mismatch_accepted(fresh_board, monkeypatch, caplog):
    monkeypatch.setattr(fresh_board, "expected_build", WRONG_BUILD)
    monkeypatch.setattr(fresh_board, "accept_build_mismatch", True)
    assert fresh_board.identify().ok
    assert "BUILD_MISMATCH" in caplog.text
