"""CAPS command: protocol.md section 6.3.

The hil-bench firmware supports HELLO and CAPS only, so the whole list fits
in one page: total=2, and start=1 returns the last name. start must be a
decimal integer without a leading zero and lower than total; start is the
only argument CAPS accepts (section 3.3).

Version: 1.0
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
"""

import pytest

pytestmark = pytest.mark.protocol


def test_caps_single_page(fresh_board):
    response = fresh_board.request("CAPS")
    assert response.ok
    assert response.fields == {"total": "2", "start": "0", "names": "HELLO,CAPS"}  # No next: one page


def test_caps_start_1(fresh_board):
    response = fresh_board.request("CAPS", start=1)
    assert response.ok
    assert response.fields == {"total": "2", "start": "1", "names": "CAPS"}


@pytest.mark.parametrize("start", ["2", "01", "x"], ids=["not_below_total", "leading_zero", "not_a_number"])
def test_caps_invalid_start(fresh_board, start):
    response = fresh_board.request("CAPS", start=start)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


def test_caps_unknown_argument(fresh_board):
    response = fresh_board.request("CAPS", page=0)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


def test_caps_no_duplicate(fresh_board):
    assert fresh_board.capabilities() == ["HELLO", "CAPS"]
