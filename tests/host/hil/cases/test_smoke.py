"""Smoke tests of the hil-bench firmware: readiness banner, HELLO and CAPS.

The board fixture has already received the banner and checked HELLO and
CAPS against protocol.md sections 4.1, 6.2 and 6.3; these tests state the
expected values explicitly and run each command once more in the session.
The command list CAPS must return comes from cases/expected.py.

Version: 1.1
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
  1.1  27/10/2026  Compare the CAPS list with cases/expected.py.
"""

import pytest

from cases.expected import COMMANDS

pytestmark = pytest.mark.smoke


def test_banner_identifies_hil_bench(board):
    banner = board.banner
    assert banner.name == "hil-bench"
    assert banner.proto.split(".")[0] == "1"
    # make reset drives NRST: PIN, or POR on the first boot after a power-up
    assert banner.reset in ("PIN", "POR")


def test_hello_matches_banner(board):
    response = board.identify()
    for key in ("name", "proto", "fw", "build"):
        assert response.fields[key] == getattr(board.banner, key)


def test_caps_lists_expected_commands(board):
    names = board.capabilities()
    assert names == COMMANDS
    assert len(names) == len(set(names))


def test_unknown_command_is_rejected(board):
    response = board.request("NO_SUCH_COMMAND")
    assert not response.ok
    assert response.code == "UNKNOWN_COMMAND"
