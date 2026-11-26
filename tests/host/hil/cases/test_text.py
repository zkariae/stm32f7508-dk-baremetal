"""LCD_TEXT: protocol.md section 6.25.

Each test starts after LCD_INIT, LCD_FILL, LCD_PIXEL and LCD_TEXT were found
in the CAPS list (section 3.4); the text fixture also sends LCD_INIT and
fills the screen with green. The text and its background use two other
colours, whose components all differ: a pixel left unwritten, or a component
taken from the wrong colour, is seen. The expected pixels are computed here:
the glyphs are read from the generated font headers of dev/common/font, in
the layout of section 6.25, and each level is blended with the formula of
that section. The firmware's drawing code is never used.

A cell is read back with LCD_PIXEL, with the pixels around it: a glyph in
both fonts (space, the densest @, W, g which goes down to the last row, and
~, the last code), the 16 levels of W, three characters side by side, the
longest text, and the clipping at the right edge, at the bottom and in the
corner. A rejected request must leave the framebuffer unchanged (section
7.1): every pixel of a drawn cell changes, so one pixel per cell is enough.
Three rejected requests have six arguments, data, font or bg replaced by an
unknown key: a missing argument is then not caught by the count.

Not tested: the light of the panel (section 6.12, note), each of the 95
glyphs (the headers are checked when they are generated), and memory past
the framebuffer, which LCD_PIXEL cannot read.

Version: 1.0
Date: 26/11/2026
Author: Z. BEN-AKKA
History:
  1.0  26/11/2026  Initial version.
"""

import re
from pathlib import Path

import pytest

from cases.expected import LCD_CELL_HEIGHT, LCD_CELL_WIDTH, LCD_HEIGHT, LCD_TEXT_DATA_MAX, LCD_WIDTH

pytestmark = pytest.mark.lcd

TEXT_COMMANDS = ("LCD_INIT", "LCD_FILL", "LCD_PIXEL", "LCD_TEXT")
FONT_DIR = Path(__file__).resolve().parents[4] / "dev" / "common" / "font"
FIRST_CODE, LAST_CODE = 0x20, 0x7E
LEVEL_MAX = 15

SCREEN = 0x07E0      # Green, under the text
COLOR = 0xFD20       # Orange: red 31, green 41, blue 0
BG = 0x0411          # Dark blue: red 0, green 32, blue 17
X0, Y0 = 101, 57     # Odd position, away from the edges


def load_glyphs(font: str) -> bytes:
    """Glyph bytes of a generated header, in file order, after a check of their number."""
    text = (FONT_DIR / f"mono_8x16_{font}.h").read_text(encoding="utf-8")
    table = re.sub(r"//.*", "", text[text.index("static const"):])
    data = bytes(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})\b", table))
    per_glyph = LCD_CELL_HEIGHT * LCD_CELL_WIDTH * (1 if font == "1bpp" else 4) // 8
    assert len(data) == (LAST_CODE - FIRST_CODE + 1) * per_glyph, f"{font}: unexpected header size"
    return data


GLYPHS = {font: load_glyphs(font) for font in ("1bpp", "4bpp")}


def level(font: str, code: int, col: int, row: int) -> int:
    """Level of one pixel of a glyph: rows from the top, pixels from the left, high bits first."""
    glyphs = GLYPHS[font]
    if font == "1bpp":
        byte = glyphs[(code - FIRST_CODE) * LCD_CELL_HEIGHT + row]
        return LEVEL_MAX * (byte >> (7 - col) & 1)
    byte = glyphs[(code - FIRST_CODE) * LCD_CELL_HEIGHT * 4 + row * 4 + col // 2]
    return byte >> 4 if col % 2 == 0 else byte & 0xF


def blend(bg: int, color: int, lvl: int) -> int:
    """Colour of a level, on each RGB565 component, rounded as section 6.25 says."""
    out = 0
    for shift, mask in ((11, 0x1F), (5, 0x3F), (0, 0x1F)):
        b, c = bg >> shift & mask, color >> shift & mask
        out |= (b * (LEVEL_MAX - lvl) + c * lvl + 7) // LEVEL_MAX << shift
    return out


def expected_text(x0: int, y0: int, font: str, text: str, color: int = COLOR, bg: int = BG) -> dict:
    """(x, y): colour of every pixel the text draws on the screen."""
    pixels = {}
    for i, char in enumerate(text):
        for row in range(LCD_CELL_HEIGHT):
            for col in range(LCD_CELL_WIDTH):
                x, y = x0 + LCD_CELL_WIDTH * i + col, y0 + row
                if x < LCD_WIDTH and y < LCD_HEIGHT:
                    pixels[(x, y)] = blend(bg, color, level(font, ord(char), col, row))
    return pixels


def around(x0: int, y0: int, width: int, height: int) -> list:
    """Pixels of the one-pixel frame around a rectangle, inside the screen."""
    frame = [(x, y) for x in range(x0 - 1, x0 + width + 1) for y in (y0 - 1, y0 + height)]
    frame += [(x, y) for x in (x0 - 1, x0 + width) for y in range(y0, y0 + height)]
    return [(x, y) for x, y in frame if 0 <= x < LCD_WIDTH and 0 <= y < LCD_HEIGHT]


def pixel(board, x: int, y: int) -> int:
    response = board.request("LCD_PIXEL", x=x, y=y)
    assert response.ok
    return int(response.fields["color"], 16)


def check_pixels(board, expected: dict) -> None:
    """Read every pixel back; the message names the first wrong ones."""
    wrong = []
    for (x, y), colour in expected.items():
        got = pixel(board, x, y)
        if got != colour:
            wrong.append(f"({x}, {y}) 0x{got:04X} instead of 0x{colour:04X}")
    assert not wrong, f"{len(wrong)} wrong pixels: {', '.join(wrong[:5])}"


def draw(board, x: int, y: int, font: str, text: str, color: int = COLOR, bg: int = BG) -> None:
    response = board.request("LCD_TEXT", x=x, y=y, font=font, color=f"0x{color:04X}", bg=f"0x{bg:04X}",
                             data=text.encode("ascii").hex().upper())
    assert response.ok, f"LCD_TEXT answered {response.status} {response.code}"


@pytest.fixture
def text(fresh_board):
    """The session board, the commands supported, LCD_INIT done, the screen green."""
    for command in TEXT_COMMANDS:
        fresh_board.require(command)
    assert fresh_board.request("LCD_INIT").ok
    assert fresh_board.request("LCD_FILL", color=f"0x{SCREEN:04X}").ok
    return fresh_board


def test_text_busy_before_init(fresh_board):
    """From a reset: LCD_INIT may have succeeded earlier in the session (section 6.12)."""
    fresh_board.start_session()
    fresh_board.require("LCD_TEXT")
    response = fresh_board.request("LCD_TEXT", x=0, y=0, font="4bpp", color="0xFFFF", bg="0x0000", data="41")
    assert (response.status, response.code) == ("ERR", "BUSY")


GLYPH_CASES = [(font, char) for font in ("1bpp", "4bpp") for char in (" ", "@", "W", "g", "~")]
GLYPH_IDS = [f"{font}-{name}" for font in ("1bpp", "4bpp") for name in ("space", "at", "W", "g", "tilde")]


@pytest.mark.parametrize("font, char", GLYPH_CASES, ids=GLYPH_IDS)
def test_text_glyph(text, font, char):
    """The 128 pixels of the cell, background included, and the 52 pixels around it."""
    draw(text, X0, Y0, font, char)
    expected = expected_text(X0, Y0, font, char)
    expected.update({point: SCREEN for point in around(X0, Y0, LCD_CELL_WIDTH, LCD_CELL_HEIGHT)})
    check_pixels(text, expected)


@pytest.mark.parametrize("color, bg", [(0xEF5D, 0x10A2), (0x10A2, 0xEF5D)], ids=["light_on_dark", "dark_on_light"])
def test_text_blend(text, color, bg):
    """W of the 4-bit font holds the 16 levels: each is blended and rounded as section 6.25 says."""
    levels = {level("4bpp", ord("W"), col, row) for col in range(LCD_CELL_WIDTH) for row in range(LCD_CELL_HEIGHT)}
    assert levels == set(range(LEVEL_MAX + 1)), "the test needs a glyph with every level"
    draw(text, X0, Y0, "4bpp", "W", color, bg)
    check_pixels(text, expected_text(X0, Y0, "4bpp", "W", color, bg))


@pytest.mark.parametrize("font", ["1bpp", "4bpp"])
def test_text_string(text, font):
    """Three cells side by side, 8 pixels apart, in order, and nothing around them."""
    draw(text, X0, Y0, font, "HIL")
    expected = expected_text(X0, Y0, font, "HIL")
    expected.update({point: SCREEN for point in around(X0, Y0, 3 * LCD_CELL_WIDTH, LCD_CELL_HEIGHT)})
    check_pixels(text, expected)


def test_text_longest(text):
    """The most characters: the first and last cells, and nothing after the last."""
    chars = "0123456789ABCDEFGHIJ"
    assert len(chars) == LCD_TEXT_DATA_MAX
    draw(text, 0, Y0, "4bpp", chars)
    full = expected_text(0, Y0, "4bpp", chars)
    last = (LCD_TEXT_DATA_MAX - 1) * LCD_CELL_WIDTH
    expected = {(x, y): colour for (x, y), colour in full.items() if x < LCD_CELL_WIDTH or x >= last}
    expected.update({(last + LCD_CELL_WIDTH, y): SCREEN for y in range(Y0, Y0 + LCD_CELL_HEIGHT)})
    check_pixels(text, expected)


def clipped_right():
    """4 columns at the right edge; a drawing that wrapped would reach the start of the next rows."""
    x = LCD_WIDTH - 4
    expected = expected_text(x, Y0, "4bpp", "W")
    expected.update({(col, y): SCREEN for col in range(4) for y in range(Y0, Y0 + LCD_CELL_HEIGHT + 1)})
    return x, Y0, expected


def clipped_bottom():
    """The first 8 rows of the cell, and nothing above it."""
    y = LCD_HEIGHT - 8
    expected = expected_text(X0, y, "4bpp", "W")
    expected.update({(x, y - 1): SCREEN for x in range(X0, X0 + LCD_CELL_WIDTH)})
    return X0, y, expected


def clipped_corner():
    """One pixel in the bottom right corner, and nothing beside it."""
    x, y = LCD_WIDTH - 1, LCD_HEIGHT - 1
    expected = expected_text(x, y, "4bpp", "W")
    expected.update({(x - 1, y): SCREEN, (x, y - 1): SCREEN})
    return x, y, expected


@pytest.mark.parametrize("case", [clipped_right, clipped_bottom, clipped_corner], ids=["right", "bottom", "corner"])
def test_text_clipped(text, case):
    x, y, expected = case()
    draw(text, x, y, "4bpp", "W")
    check_pixels(text, expected)


def test_text_lowercase(text):
    """Hexadecimal digits in either case (section 6.6), and a colour of two digits (section 6.12)."""
    response = text.request("LCD_TEXT", x=X0, y=Y0, font="4bpp", color="0xfd20", bg="0x1f", data="6a6b")
    assert response.ok
    check_pixels(text, expected_text(X0, Y0, "4bpp", "jk", COLOR, 0x001F))


VALID = {"x": X0, "y": Y0, "font": "4bpp", "color": f"0x{COLOR:04X}", "bg": f"0x{BG:04X}", "data": "4142"}


@pytest.mark.parametrize("change", [
    {"x": None},
    {"y": None},
    {"font": None},
    {"color": None},
    {"bg": None},
    {"data": None},
    {"x": LCD_WIDTH},
    {"y": LCD_HEIGHT},
    {"x": "01"},
    {"font": "2bpp"},
    {"font": "4BPP"},
    {"color": "0x10000"},
    {"bg": "0x10000"},
    {"bg": "0411"},
    {"data": "414"},
    {"data": "4G"},
    {"data": "41" * (LCD_TEXT_DATA_MAX + 1)},
    {"data": "410A"},
    {"data": "417F"},
    {"data": "4180"},
    {"z": 1},
    {"data": None, "text": "41"},
    {"font": None, "z": "4bpp"},
    {"bg": None, "z": f"0x{BG:04X}"},
], ids=["missing_x", "missing_y", "missing_font", "missing_color", "missing_bg", "missing_data", "x_too_big",
        "y_too_big", "leading_zero", "unknown_font", "uppercase_font", "color_too_big", "bg_too_big",
        "bg_no_prefix", "odd_digits", "bad_digit", "too_long", "line_feed", "delete", "not_ascii",
        "extra_argument", "data_renamed", "font_renamed", "bg_renamed"])
def test_text_invalid(text, change):
    args = {key: value for key, value in {**VALID, **change}.items() if value is not None}
    response = text.request("LCD_TEXT", **args)
    assert (response.status, response.code) == ("ERR", "INVALID_ARGUMENT")
    # Not executed: both cells keep the screen colour, the valid first character included
    assert pixel(text, X0, Y0) == SCREEN
    assert pixel(text, X0 + LCD_CELL_WIDTH, Y0) == SCREEN
