"""CAPS command: protocol.md section 6.3.

The expected names come from cases/expected.py, in the order of the
firmware's command table. The sixteen names of protocol 1.3 take two pages:
CAPS without start returns the first eight with next=8, the longest page
that fits in 128 bytes whatever the request id, and start=8 returns the other
eight with no next (section 6.3). start=total-1 returns the last name.
start must be a decimal integer without a leading zero and lower than total;
start is the only argument CAPS accepts (section 3.3).

Version: 1.2
Date: 03/11/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
  1.1  27/10/2026  Derive the expected values from cases/expected.py.
  1.2  03/11/2026  Two pages for the sixteen commands of protocol 1.3.
"""

import pytest

from cases.expected import COMMANDS

pytestmark = pytest.mark.protocol

FIRST_PAGE = 8  # Names in the first page (section 6.3, example with two pages)


def test_caps_two_pages(fresh_board):
    total = str(len(COMMANDS))
    first = fresh_board.request("CAPS")
    assert first.ok
    assert first.fields == {"total": total, "start": "0", "names": ",".join(COMMANDS[:FIRST_PAGE]),
                            "next": str(FIRST_PAGE)}
    second = fresh_board.request("CAPS", start=FIRST_PAGE)
    assert second.ok
    # No next: last page
    assert second.fields == {"total": total, "start": str(FIRST_PAGE), "names": ",".join(COMMANDS[FIRST_PAGE:])}


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
