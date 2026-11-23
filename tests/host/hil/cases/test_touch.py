"""TOUCH_ID and TOUCH_READ: protocol.md sections 6.20 to 6.22.

Each test starts after the two commands were found in the CAPS list (section
3.4). The chip identifier comes from cases/expected.py, not from the firmware.
TOUCH_ID right after a reset checks the start time rule of section 6.20: the
request most likely arrives before 300 ms, and the firmware waits instead of
failing. points=0 needs that nobody touches the screen during the run (section
6.20, note); it also covers a TD_STATUS count above 5 read as no touch. A
rejected request must leave the state unchanged (section 7.1).

The corner, accuracy and drawing tests need an operator and run only with
HIL_OPERATOR=1. Their instructions go to the terminal and to the logger
hil.operator, which the TUI shows on its progress line. The corner tests ask
for a touch near the top-left, then the top-right corner, and check the
position, which also checks the axis swap.
The accuracy tests draw five black discs one after the other, at random
positions on a white screen (LCD_FILL, LCD_CIRCLE, section 6.23), and check
that the touched point is inside each disc. The screen is made white once;
the disc then moves: the previous one is painted white, so the screen does
not flash between two targets. Once the last disc is touched, it is painted
white too. The positions come from a seed written in the log;
HIL_TOUCH_SEED=<n> replays a series. The drawing test works like the
10-touch-paint application, in one colour (the protocol has no rectangle for
a colour bar): HIL_DRAW_COLOR=<name or 0x...> chooses it, black by default;
the names and their French aliases come from tests/host/config/colors.yaml,
and white, invisible on the white screen, is refused. It draws a disc of
radius 4 at each touched point, and one LCD_LINE
between two points of a stroke, which the firmware fills with discs every
2 pixels as the application does (section 6.24): one serial exchange per
point, whatever the length. The drawing ends when the screen is released for
3 s; drawn points are read back with LCD_PIXEL.

Not tested: DEVICE_TIMEOUT and DEVICE_ERROR, which need a missing controller
or a faulty bus, and the points after the first, which TOUCH_READ does not
report.

Version: 1.5
Date: 23/11/2026
Author: Z. BEN-AKKA
History:
  1.0  20/11/2026  Initial version.
  1.1  20/11/2026  Add the accuracy tests: touch five discs drawn at random positions.
  1.2  20/11/2026  Add the drawing test, as in the 10-touch-paint application.
  1.3  20/11/2026  Drawing test: one LCD_LINE per point instead of one LCD_CIRCLE per disc.
  1.4  20/11/2026  Drawing test: colour chosen with HIL_DRAW_COLOR, names from colors.yaml.
  1.5  23/11/2026  Operator instructions, corner tests included, on the logger hil.operator for the TUI.
"""

import logging
import math
import os
import random
import re
import time
from pathlib import Path

import pytest
import yaml

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

BRUSH_RADIUS = 4      # Pixels, BRUSH_R of 10-touch-paint
DRAW_END = 3.0        # Seconds released that end the drawing
DRAW_MAX = 60.0       # Longest drawing, in seconds
DRAW_MIN_POINTS = 10  # Touched points needed for a drawing
DRAW_CHECKED = 20     # Drawn points read back with LCD_PIXEL, at most
COLORS_FILE = Path(__file__).resolve().parents[2] / "config" / "colors.yaml"
HEX_COLOR = re.compile(r"0x[0-9A-Fa-f]{1,4}")  # RGB565 argument, section 6.12

log = logging.getLogger("hil.operator")  # Instructions: the TUI shows them on its progress line
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
    tell(capsys, f"Touch the {corner} corner of the screen within {TOUCH_WAIT:.0f} s")
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


def load_colors(path: Path = COLORS_FILE) -> dict:
    """{name or alias, lower case: (name, value as 0x and 4 uppercase digits)} from colors.yaml."""
    table = {}
    for name, entry in yaml.safe_load(path.read_text(encoding="utf-8"))["colors"].items():
        value = f"0x{int(entry['rgb565'], 16):04X}"
        for key in [name, *entry["aliases"]]:
            if key.lower() in table:
                raise ValueError(f"{path.name}: {key} defined twice")
            table[key.lower()] = (name, value)
    return table


def draw_color(text: str, colors: dict) -> tuple:
    """(name, value) of a HIL_DRAW_COLOR text; ValueError if unknown, malformed or white."""
    text = text.strip()
    if HEX_COLOR.fullmatch(text):
        value = f"0x{int(text, 16):04X}"
        name = next((known for known, known_value in colors.values() if known_value == value), value)
    elif text.lower() in colors:
        name, value = colors[text.lower()]
    else:
        names = ", ".join(sorted({known for known, _ in colors.values()}))
        raise ValueError(f"HIL_DRAW_COLOR={text!r}: not a colour of {COLORS_FILE.name} ({names}) nor 0x and 1 to 4 "
                         f"hexadecimal digits")
    if value == WHITE:
        raise ValueError(f"HIL_DRAW_COLOR={text!r}: white is invisible on the white screen")
    return name, value


def brush(board, point, color: str) -> None:
    """One disc of the brush at point."""
    x, y = point
    assert board.request("LCD_CIRCLE", x=x, y=y, radius=BRUSH_RADIUS, color=color).ok


def stroke(board, start, end, color: str) -> None:
    """One LCD_LINE from start to end: the firmware fills it with discs every 2 pixels (section 6.24)."""
    (x0, y0), (x1, y1) = start, end
    assert board.request("LCD_LINE", x0=x0, y0=y0, x1=x1, y1=y1, radius=BRUSH_RADIUS, color=color).ok


def draw(board, color: str) -> tuple:
    """Follow the finger until the screen is released for DRAW_END; (points, strokes)."""
    points, strokes = [], 0
    previous, released_since = None, None
    start = time.monotonic()
    while time.monotonic() - start < DRAW_MAX:
        response = board.request("TOUCH_READ")
        assert response.ok
        now = time.monotonic()
        if response.fields["points"] != "0":
            point = (int(response.fields["x"]), int(response.fields["y"]))
            points.append(point)
            if previous is None:
                strokes += 1
                brush(board, point, color)  # Touch down
            elif point != previous:
                stroke(board, previous, point, color)
            previous, released_since = point, None
        else:
            previous = None  # The next touch starts a new stroke
            released_since = released_since or now
            if now - released_since >= DRAW_END:
                break
        # No pause: one TOUCH_READ exchange already lasts about as long as the 10 ms poll of 10-touch-paint
    return points, strokes


@pytest.mark.skipif(not OPERATOR, reason="needs an operator: set HIL_OPERATOR=1")
def test_touch_draw(touch, capsys):
    """Free drawing as in 10-touch-paint: the strokes follow the finger and are in the framebuffer."""
    try:
        name, color = draw_color(os.environ.get("HIL_DRAW_COLOR", "black"), load_colors())
    except ValueError as error:
        pytest.fail(str(error))  # Before anything is drawn
    for command in ("LCD_INIT", "LCD_FILL", "LCD_CIRCLE", "LCD_LINE", "LCD_PIXEL"):
        touch.require(command)
    assert touch.request("LCD_INIT").ok
    assert touch.request("LCD_FILL", color=WHITE).ok
    _target["centre"] = None  # The accuracy disc, if any, is gone
    wait_for_points(touch, touched=False)
    tell(capsys, f"Draw on the screen with one finger in {name} ({color}); lift it for {DRAW_END:.0f} s to finish")
    wait_for_points(touch, touched=True)  # First touch within TOUCH_WAIT
    points, strokes = draw(touch, color)
    try:
        tell(capsys, f"Drawing done: {len(points)} points, {strokes} strokes")
        assert len(points) >= DRAW_MIN_POINTS, f"{len(points)} points, at least {DRAW_MIN_POINTS} needed"
        assert all(x < LCD_WIDTH and y < LCD_HEIGHT for x, y in points)
        for x, y in points[::max(1, len(points) // DRAW_CHECKED)][:DRAW_CHECKED]:
            response = touch.request("LCD_PIXEL", x=x, y=y)
            assert response.ok
            assert response.fields["color"] == color, f"({x}, {y}) touched but not drawn in {name}"
    finally:
        touch.request("LCD_FILL", color=WHITE)  # Leave a white screen; never hides the failure above
