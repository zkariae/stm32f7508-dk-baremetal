"""GPIO_CONFIG and LCD commands: protocol.md sections 6.11 to 6.19 and 6.23.

Each test starts after the nine commands were found in the CAPS list
(section 3.4); the lcd fixture also sends LCD_INIT. The BUSY tests start from
a reset, since LCD_INIT may have succeeded earlier in the session (section
6.12). The expected values come from cases/expected.py: the pin table of the
datasheet, the panel timings, the framebuffer address and the LCD_CIRCLE
radius limits. A rejected LCD_FILL or LCD_CIRCLE must leave the framebuffer
unchanged (section 7.1). LCD_CIRCLE is checked with LCD_PIXEL on and around
the edge of the disc, and clipped at two corners. The tests check the
registers, the scan and the framebuffer memory, not the light of the panel
(section 6.12, note). DEVICE_ERROR needs a failed HSE and DEVICE_TIMEOUT a
PLLSAI that does not lock: neither is tested here.

Version: 1.1
Date: 20/11/2026
Author: Z. BEN-AKKA
History:
  1.0  03/11/2026  Initial version.
  1.1  20/11/2026  Add the LCD_CIRCLE tests (protocol 1.4).
"""

import pytest

from cases.expected import (LCD_FB_ADDR, LCD_HEIGHT, LCD_PINS, LCD_PIXEL_HZ, LCD_POWER_PINS, LCD_RADIUS_MAX,
                            LCD_RADIUS_MIN, LCD_TIMING, LCD_WIDTH)

pytestmark = pytest.mark.lcd

LCD_COMMANDS = ("GPIO_CONFIG", "LCD_INIT", "LCD_CLOCK", "LCD_TIMING", "LCD_LAYER", "LCD_SCAN", "LCD_FILL",
                "LCD_PIXEL", "LCD_CIRCLE")
CIRCLE = {"x": LCD_WIDTH // 2, "y": LCD_HEIGHT // 2, "radius": 20, "color": "0x0000"}  # A valid LCD_CIRCLE
CORNERS = [(0, 0), (LCD_WIDTH - 1, 0), (0, LCD_HEIGHT - 1), (LCD_WIDTH - 1, LCD_HEIGHT - 1),
           (LCD_WIDTH // 2, LCD_HEIGHT // 2)]  # Four corners and the centre


def pixel(board, x: int, y: int) -> str:
    """Colour of pixel (x, y) reported by LCD_PIXEL."""
    response = board.request("LCD_PIXEL", x=x, y=y)
    assert response.ok
    return response.fields["color"]


def fill(board, color: int) -> None:
    """Fill the framebuffer, colour written as 0x and four uppercase digits."""
    assert board.request("LCD_FILL", color=f"0x{color:04X}").ok


def assert_rejected(response) -> None:
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")


@pytest.fixture
def lcd_reset(fresh_board):
    """The board after a reset, LCD commands supported, LCD_INIT not sent."""
    fresh_board.start_session()
    for command in LCD_COMMANDS:
        fresh_board.require(command)
    return fresh_board


@pytest.fixture
def lcd(fresh_board):
    """The session board, LCD commands supported, LCD_INIT done."""
    for command in LCD_COMMANDS:
        fresh_board.require(command)
    assert fresh_board.request("LCD_INIT").ok
    return fresh_board


@pytest.mark.parametrize("command, args", [
    ("LCD_CLOCK", {}),
    ("LCD_TIMING", {}),
    ("LCD_LAYER", {}),
    ("LCD_SCAN", {"ms": 100}),
    ("LCD_FILL", {"color": "0xF800"}),
    ("LCD_PIXEL", {"x": 0, "y": 0}),
    ("LCD_CIRCLE", CIRCLE),
])
def test_lcd_busy_before_init(lcd_reset, command, args):
    response = lcd_reset.request(command, **args)
    assert (response.status, response.code) == ("ERR", "BUSY")


def test_gpio_config_without_init(lcd_reset):
    """Allowed at any time (section 6.11): LD1 on PI1 is an output, off after the reset."""
    response = lcd_reset.request("GPIO_CONFIG", port="I", pin=1)
    assert response.ok
    assert response.fields == {"mode": "output", "af": "0", "level": "0"}


def test_lcd_init(lcd_reset):
    response = lcd_reset.request("LCD_INIT")
    assert response.ok
    assert response.fields == {}


@pytest.mark.parametrize("port, pin, af", LCD_PINS, ids=[f"P{port}{pin}" for port, pin, _ in LCD_PINS])
def test_lcd_pins(lcd, port, pin, af):
    response = lcd.request("GPIO_CONFIG", port=port, pin=pin)
    assert response.ok
    # The level of a data pin follows the scan: not checked
    assert (response.fields["mode"], response.fields["af"]) == ("af", str(af))


@pytest.mark.parametrize("port, pin", LCD_POWER_PINS, ids=[f"P{port}{pin}" for port, pin in LCD_POWER_PINS])
def test_lcd_power_pins(lcd, port, pin):
    response = lcd.request("GPIO_CONFIG", port=port, pin=pin)
    assert response.ok
    assert (response.fields["mode"], response.fields["level"]) == ("output", "1")


def test_lcd_clock(lcd):
    response = lcd.request("LCD_CLOCK")
    assert response.ok
    assert response.fields == {"pllsai": "locked", "pixel_hz": str(LCD_PIXEL_HZ)}


def test_lcd_timing(lcd):
    response = lcd.request("LCD_TIMING")
    assert response.ok
    assert response.fields == LCD_TIMING


def test_lcd_layer(lcd):
    response = lcd.request("LCD_LAYER")
    assert response.ok
    assert response.fields == {"enabled": "1", "format": "rgb565", "fb_addr": f"0x{LCD_FB_ADDR:08X}",
                               "x": "0", "y": "0", "width": str(LCD_WIDTH), "height": str(LCD_HEIGHT)}


def expected_frames(board, ms: int) -> float:
    """Frames in ms milliseconds, from LCD_CLOCK and LCD_TIMING (section 6.17)."""
    pixel_hz = int(board.request("LCD_CLOCK").fields["pixel_hz"])
    timing = {key: int(value) for key, value in board.request("LCD_TIMING").fields.items()}
    total_width = timing["hsw"] + timing["hbp"] + timing["width"] + timing["hfp"]
    total_height = timing["vsw"] + timing["vbp"] + timing["height"] + timing["vfp"]
    return pixel_hz * ms / (1000 * total_width * total_height)


@pytest.mark.parametrize("ms", [100, 1000])
def test_lcd_scan(lcd, ms):
    expected = expected_frames(lcd, ms)
    response = lcd.request("LCD_SCAN", ms=ms)
    assert response.ok
    assert abs(int(response.fields["frames"]) - expected) <= 1
    assert response.fields["underrun"] == "0"


@pytest.mark.parametrize("color", [0xF800, 0x07E0, 0x001F, 0xFFFF], ids=["red", "green", "blue", "white"])
def test_lcd_fill_pixel(lcd, color):
    fill(lcd, color)
    for x, y in CORNERS:
        assert pixel(lcd, x, y) == f"0x{color:04X}"


def test_lcd_init_clears(lcd):
    assert pixel(lcd, LCD_WIDTH - 1, LCD_HEIGHT - 1) == "0x0000"
    fill(lcd, 0xF800)
    assert lcd.request("LCD_INIT").ok  # Sent again in the same session (section 6.13)
    for x, y in CORNERS:
        assert pixel(lcd, x, y) == "0x0000"
    assert lcd.request("LCD_CLOCK").fields["pllsai"] == "locked"


def test_lcd_fill_short_lowercase(lcd):
    assert lcd.request("LCD_FILL", color="0xabc").ok
    assert pixel(lcd, 0, 0) == "0x0ABC"


def test_lcd_scan_after_fill(lcd):
    fill(lcd, 0xFFFF)
    response = lcd.request("LCD_SCAN", ms=100)
    assert response.ok
    assert response.fields["underrun"] == "0"


@pytest.mark.parametrize("args", [
    {"pin": 0},
    {"port": "I"},
    {"port": "L", "pin": 0},
    {"port": "a", "pin": 0},
    {"port": "AB", "pin": 0},
    {"port": "A", "pin": 16},
    {"port": "A", "pin": "01"},
    {"port": "A", "pin": 0, "x": 1},
], ids=["missing_port", "missing_pin", "port_after_k", "lowercase_port", "two_letters", "pin_too_big",
        "leading_zero", "extra_argument"])
def test_gpio_config_invalid(lcd, args):
    assert_rejected(lcd.request("GPIO_CONFIG", **args))


@pytest.mark.parametrize("command", ["LCD_INIT", "LCD_CLOCK", "LCD_TIMING", "LCD_LAYER"])
def test_lcd_no_argument(lcd, command):
    assert_rejected(lcd.request(command, x=1))


@pytest.mark.parametrize("args", [{}, {"ms": 99}, {"ms": 1001}, {"ms": "0100"}, {"ms": 100, "x": 1}],
                         ids=["missing_ms", "too_short", "too_long", "leading_zero", "extra_argument"])
def test_lcd_scan_invalid(lcd, args):
    assert_rejected(lcd.request("LCD_SCAN", **args))


@pytest.mark.parametrize("args", [
    {},
    {"color": "F800"},
    {"color": "0x"},
    {"color": "0xG0"},
    {"color": "0x10000"},
    {"color": "0x00000"},
    {"color": "0xF800", "x": 1},
], ids=["missing_color", "no_prefix", "no_digit", "bad_digit", "too_big", "five_digits", "extra_argument"])
def test_lcd_fill_invalid(lcd, args):
    fill(lcd, 0x07E0)
    assert_rejected(lcd.request("LCD_FILL", **args))
    assert pixel(lcd, 0, 0) == "0x07E0"  # Not executed: framebuffer unchanged


@pytest.mark.parametrize("args", [
    {"y": 0},
    {"x": 0},
    {"x": LCD_WIDTH, "y": 0},
    {"x": 0, "y": LCD_HEIGHT},
    {"x": "01", "y": 0},
    {"x": 0, "y": 0, "z": 1},
], ids=["missing_x", "missing_y", "x_too_big", "y_too_big", "leading_zero", "extra_argument"])
def test_lcd_pixel_invalid(lcd, args):
    assert_rejected(lcd.request("LCD_PIXEL", **args))


def test_lcd_circle(lcd):
    """Pixels with dx² + dy² ≤ radius² take the colour, the others keep theirs (section 6.23)."""
    fill(lcd, 0xFFFF)
    assert lcd.request("LCD_CIRCLE", **CIRCLE).ok
    cx, cy, r = CIRCLE["x"], CIRCLE["y"], CIRCLE["radius"]
    inside = [(cx, cy), (cx + r, cy), (cx, cy - r), (cx + 14, cy + 14)]   # 14² + 14² = 392 ≤ 400
    outside = [(cx + r + 1, cy), (cx, cy + r + 1), (cx + 15, cy - 15)]  # 15² + 15² = 450 > 400
    for x, y in inside:
        assert pixel(lcd, x, y) == "0x0000", f"({x}, {y}) inside the disc"
    for x, y in outside:
        assert pixel(lcd, x, y) == "0xFFFF", f"({x}, {y}) outside the disc"


def test_lcd_circle_clipped(lcd):
    """A disc across the edges is drawn on the screen part only (section 6.23)."""
    fill(lcd, 0xFFFF)
    for x, y in [(0, 0), (LCD_WIDTH - 1, LCD_HEIGHT - 1)]:
        assert lcd.request("LCD_CIRCLE", x=x, y=y, radius=LCD_RADIUS_MAX, color="0xF800").ok
        assert pixel(lcd, x, y) == "0xF800"
    assert pixel(lcd, LCD_WIDTH // 2, LCD_HEIGHT // 2) == "0xFFFF"


@pytest.mark.parametrize("change", [
    {"radius": None},
    {"color": None},
    {"radius": LCD_RADIUS_MIN - 1},
    {"radius": LCD_RADIUS_MAX + 1},
    {"radius": "020"},
    {"x": LCD_WIDTH},
    {"y": LCD_HEIGHT},
    {"color": "0x10000"},
    {"z": 1},
], ids=["missing_radius", "missing_color", "radius_zero", "radius_too_big", "leading_zero", "x_too_big",
        "y_too_big", "color_too_big", "extra_argument"])
def test_lcd_circle_invalid(lcd, change):
    fill(lcd, 0x07E0)
    args = {key: value for key, value in {**CIRCLE, **change}.items() if value is not None}
    assert_rejected(lcd.request("LCD_CIRCLE", **args))
    assert pixel(lcd, CIRCLE["x"], CIRCLE["y"]) == "0x07E0"  # Not executed: framebuffer unchanged
