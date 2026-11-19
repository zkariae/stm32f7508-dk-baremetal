"""CAPS command: protocol.md section 6.3.

The expected names come from cases/expected.py, in the order of the
firmware's command table. CAPS without start returns the first page; every
page but the last carries next, the start of the following page, and the
pages put together give the whole table (section 6.3). The number of pages
and their sizes depend on the length of the names (each page is the longest
that fits in 128 bytes whatever the request id), so they are not fixed here.
start=total-1 returns the last name. start must be a decimal integer without
a leading zero and lower than total; start is the only argument CAPS accepts
(section 3.3).

Version: 1.3
Date: 19/11/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
  1.1  27/10/2026  Derive the expected values from cases/expected.py.
  1.2  03/11/2026  Two pages for the sixteen commands of protocol 1.3.
  1.3  19/11/2026  Follow next over any number of pages.
"""

import pytest

from cases.expected import COMMANDS

pytestmark = pytest.mark.protocol


def test_caps_pages(fresh_board):
    total = str(len(COMMANDS))
    names = []
    start = None
    # At most one page per name: a firmware that loops on next cannot hang the test
    for _ in range(len(COMMANDS)):
        response = fresh_board.request("CAPS") if start is None else fresh_board.request("CAPS", start=start)
        assert response.ok
        fields = response.fields
        assert set(fields) in ({"total", "start", "names"}, {"total", "start", "names", "next"})
        assert fields["total"] == total
        assert fields["start"] == ("0" if start is None else str(start))
        page = fields["names"].split(",")
        assert page and all(page)
        names += page
        if "next" not in fields:
            break
        start = int(fields["next"])
        assert start == len(names)
    else:
        pytest.fail("CAPS still gives next after one page per command")
    assert names == COMMANDS


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
