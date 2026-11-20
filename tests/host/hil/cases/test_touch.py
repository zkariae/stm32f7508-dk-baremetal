"""TOUCH_ID and TOUCH_READ: protocol.md sections 6.20 to 6.22.

Each test starts after the two commands were found in the CAPS list (section
3.4). The chip identifier comes from cases/expected.py, not from the firmware.
TOUCH_ID right after a reset checks the start time rule of section 6.20: the
request most likely arrives before 300 ms, and the firmware waits instead of
failing. points=0 needs that nobody touches the screen during the run (section
6.20, note); it also covers a TD_STATUS count above 5 read as no touch. A
rejected request must leave the state unchanged (section 7.1).

The corner and accuracy tests need an operator and run only with
HIL_OPERATOR=1. The corner tests ask for a touch near the top-left, then the
top-right corner, and check the position, which also checks the axis swap.
The accuracy tests draw five black discs one after the other, at random
positions on a white screen (LCD_FILL, LCD_CIRCLE, section 6.23), and check
that the touched point is inside each disc. The screen is made white once;
the disc then moves: the previous one is painted white, so the screen does
not flash between two targets. Once the last disc is touched, it is painted
white too. The positions come from a seed
written in the log; HIL_TOUCH_SEED=<n> replays a series.

Not tested: DEVICE_TIMEOUT and DEVICE_ERROR, which need a missing controller
or a faulty bus, and the points after the first, which TOUCH_READ does not
report.

Version: 1.1
Date: 20/11/2026
Author: Z. BEN-AKKA
History:
  1.0  20/11/2026  Initial version.
  1.1  20/11/2026  Add the accuracy tests: touch five discs drawn at random positions.
"""

import logging
import math
import os
import random
import time

import pytest

from cases.expected import LCD_HEIGHT, LCD_WIDTH, TOUCH_CHIP_ID, TOUCH_MAX_POINTS

pytestmark = pytest.mark.touch

TOUCH_COMMANDS = ("TOUCH_ID", "TOUCH_READ")
CHIP_ID = f"0x{TOUCH_CHIP_ID:02X}"

OPERATOR = os.environ.get("HIL_OPERATOR") == "1"
TOUCH_WAIT = 10.0   # Seconds given to the operator for one touch
POLL = 0.05         # Seconds between two TOUCH_READ while waiting
CORNER_SIZE = 60    # Pixels from the edge that count as the corner

TARGETS = 5
TARGET_RADIUS = 20  # Pixels
TARGET_MARGIN = 10  # Pixels between a disc and the screen edge
WHITE, BLACK = "0xFFFF", "0x0000"
SEED = int(os.environ.get("HIL_TOUCH_SEED", time.time_ns() % 1_000_000))
_low = TARGET_RADIUS + TARGET_MARGIN
_rng = random.Random(SEED)
TARGET_CENTRES = [(_rng.randint(_low, LCD_WIDTH - 1 - _low), _rng.randint(_low, LCD_HEIGHT - 1 - _low))
                  for _ in range(TARGETS)]

log = logging.getLogger("hil.touch")  # Shown live by the TUI
_target = {"centre": None}  # Disc on the screen, kept from one accuracy test to the next


def assert_rejected(response) -> None:
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


@pytest.fixture
def touch(fresh_board):
    """The session board, touch commands supported."""
    for command in TOUCH_COMMANDS:
        fresh_board.require(command)
    return fresh_board


@pytest.fixture
def touch_reset(fresh_board):
    """The board right after a reset, touch commands supported."""
    fresh_board.start_session()
    for command in TOUCH_COMMANDS:
        fresh_board.require(command)
    return fresh_board


def test_touch_id(touch):
    response = touch.request("TOUCH_ID")
    assert response.ok
    assert response.fields == {"chip_id": CHIP_ID}


def test_touch_id_after_reset(touch_reset):
    """Sent at once after the banner: the firmware waits for the controller (section 6.20)."""
    response = touch_reset.request("TOUCH_ID")
    assert response.ok
    assert response.fields == {"chip_id": CHIP_ID}


def test_touch_read_untouched(touch):
    response = touch.request("TOUCH_READ")
    assert response.ok
    assert response.fields == {"points": "0"}


def test_touch_read_after_lcd_init(touch):
    """The touch commands do not depend on the LCD (section 6.20)."""
    touch.require("LCD_INIT")
    assert touch.request("LCD_INIT").ok
    response = touch.request("TOUCH_READ")
    assert response.ok
    assert response.fields == {"points": "0"}


@pytest.mark.parametrize("command, unchanged", [
    ("TOUCH_ID", {"chip_id": CHIP_ID}),
    ("TOUCH_READ", {"points": "0"}),
], ids=["TOUCH_ID", "TOUCH_READ"])
def test_touch_extra_argument(touch, command, unchanged):
    assert_rejected(touch.request(command, x=1))
    response = touch.request(command)
    assert response.ok
    assert response.fields == unchanged


def wait_for_points(board, touched: bool) -> dict:
    """Fields of the first TOUCH_READ with a point (touched) or without (released), within TOUCH_WAIT."""
    deadline = time.monotonic() + TOUCH_WAIT
    while time.monotonic() < deadline:
        response = board.request("TOUCH_READ")
        assert response.ok
        if (response.fields["points"] != "0") == touched:
            return response.fields
        time.sleep(POLL)
    pytest.fail(f"no {'touch' if touched else 'release'} within {TOUCH_WAIT} s")


@pytest.mark.skipif(not OPERATOR, reason="needs an operator: set HIL_OPERATOR=1")
@pytest.mark.parametrize("corner, in_corner", [
    ("top-left", lambda x, y: x < CORNER_SIZE and y < CORNER_SIZE),
    ("top-right", lambda x, y: x > LCD_WIDTH - CORNER_SIZE and y < CORNER_SIZE),
], ids=["top_left", "top_right"])
def test_touch_corner(touch, capsys, corner, in_corner):
    """Screen x is the controller Y register (section 6.20): a wrong swap fails top-right."""
    wait_for_points(touch, touched=False)  # The previous touch must not count
    with capsys.disabled():
        print(f"\n>>> Touch the {corner} corner of the screen within {TOUCH_WAIT:.0f} s")
    fields = wait_for_points(touch, touched=True)
    points, x, y = int(fields["points"]), int(fields["x"]), int(fields["y"])
    assert 1 <= points <= TOUCH_MAX_POINTS
    assert x < LCD_WIDTH and y < LCD_HEIGHT
    assert in_corner(x, y), f"x={x} y={y} is not in the {corner} corner"


def tell(capsys, text: str) -> None:
    """Show text to the operator: in the terminal and, through the log, in the TUI."""
    log.info(text)
    with capsys.disabled():
        print(f"\n>>> {text}")


def move_target(board, centre) -> None:
    """Draw the black disc at centre; only the previous disc is erased, not the whole screen."""
    previous = _target["centre"]
    erased = None
    if previous is not None:
        px, py = previous
        erased = board.request("LCD_CIRCLE", x=px, y=py, radius=TARGET_RADIUS, color=WHITE)
    if erased is None or erased.code == "BUSY":  # First target, or a new session since: white screen once
        assert board.request("LCD_INIT").ok
        assert board.request("LCD_FILL", color=WHITE).ok
    else:
        assert erased.ok
    cx, cy = centre
    assert board.request("LCD_CIRCLE", x=cx, y=cy, radius=TARGET_RADIUS, color=BLACK).ok
    _target["centre"] = centre


@pytest.mark.skipif(not OPERATOR, reason="needs an operator: set HIL_OPERATOR=1")
@pytest.mark.parametrize("number, centre", list(enumerate(TARGET_CENTRES, 1)),
                         ids=[f"target{number}" for number in range(1, TARGETS + 1)])
def test_touch_accuracy(touch, capsys, number, centre):
    """The touched point is inside the black disc drawn on a white screen."""
    for command in ("LCD_INIT", "LCD_FILL", "LCD_CIRCLE"):
        touch.require(command)
    cx, cy = centre
    move_target(touch, centre)
    wait_for_points(touch, touched=False)
    tell(capsys, f"Target {number}/{TARGETS} (seed {SEED}): touch the black circle within {TOUCH_WAIT:.0f} s")
    fields = wait_for_points(touch, touched=True)
    if number == TARGETS:  # Last target touched: leave a white screen
        assert touch.request("LCD_CIRCLE", x=cx, y=cy, radius=TARGET_RADIUS, color=WHITE).ok
        _target["centre"] = None
    x, y = int(fields["x"]), int(fields["y"])
    distance = math.hypot(x - cx, y - cy)
    verdict = "inside" if distance <= TARGET_RADIUS else "outside"
    tell(capsys, f"Target {number}: centre ({cx}, {cy}), touched ({x}, {y}), {distance:.1f} px: {verdict}")
    assert distance <= TARGET_RADIUS, \
        f"touched ({x}, {y}) is {distance:.1f} px from ({cx}, {cy}), radius {TARGET_RADIUS}"
