"""CAPS command: protocol.md section 6.3.

The expected names come from cases/expected.py, in the order of the
firmware's command table. They fit in one page, so CAPS without start
returns them all with no next, and start=total-1 returns the last name.
start must be a decimal integer without a leading zero and lower than total;
start is the only argument CAPS accepts (section 3.3).

Version: 1.1
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
  1.1  27/10/2026  Derive the expected values from cases/expected.py.
"""

import pytest

from cases.expected import COMMANDS

pytestmark = pytest.mark.protocol


def test_caps_single_page(fresh_board):
    response = fresh_board.request("CAPS")
    assert response.ok
    # No next: one page
    assert response.fields == {"total": str(len(COMMANDS)), "start": "0", "names": ",".join(COMMANDS)}


def test_caps_last_start(fresh_board):
    last = len(COMMANDS) - 1
    response = fresh_board.request("CAPS", start=last)
    assert response.ok
    assert response.fields == {"total": str(len(COMMANDS)), "start": str(last), "names": COMMANDS[-1]}


@pytest.mark.parametrize("start", [str(len(COMMANDS)), "01", "x"],
                         ids=["not_below_total", "leading_zero", "not_a_number"])
def test_caps_invalid_start(fresh_board, start):
    response = fresh_board.request("CAPS", start=start)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


def test_caps_unknown_argument(fresh_board):
    response = fresh_board.request("CAPS", page=0)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


def test_caps_no_duplicate(fresh_board):
    assert fresh_board.capabilities() == COMMANDS
