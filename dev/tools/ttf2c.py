#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       ttf2c.py
# \brief      Convert a monospaced TrueType font into a C header of 8 x 16 glyphs.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       25/11/2026
#
# \details
#   ASCII 0x20 to 0x7E, 1 bit or 4 bits per pixel. A font that does not fit
#   the cell is refused. The header carries the license of the font.
#
# \section ttf2c_py_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */
"""
Convert a monospaced TrueType font into a C header of 8 x 16 glyphs.

The header holds the 95 characters from 0x20 to 0x7E, one after the other.
Both formats come from the same smooth rendering:

  1 bit   16 bytes per glyph, one per row; bit 7 is the left pixel. A pixel
          is set when its coverage reaches the threshold.
  4 bits  64 bytes per glyph, four per row; the high nibble is the left
          pixel, 0 for the background and 15 for the text.

    ./ttf2c.py Font-Regular.ttf --bpp 1 --name mono_8x16_1bpp \\
        --license OFL.txt --out mono_8x16_1bpp.h --preview sheet.png

The same font, options, Pillow and FreeType give the same file: the header
has no date and no path.

Nothing is written when the font is not usable: advance other than 8 pixels,
ink outside the cell, empty or identical glyphs. Only fonts under the SIL
Open Font License 1.1 are accepted, as the header is marked OFL-1.1.

Needs Pillow:  pip install pillow
"""

import argparse
import hashlib
import io
import os
import re
import sys

# FreeType reads this variable to change its hinting: the output must not depend on it
os.environ.pop("FREETYPE_PROPERTIES", None)

try:
    import PIL
    from PIL import Image, ImageDraw, ImageFont, features
except ImportError:
    sys.exit("Pillow is missing — pip install pillow")

CELL_W = 8
CELL_H = 16
FIRST = 0x20
LAST = 0x7E
CODES = range(FIRST, LAST + 1)
MARGIN = 16  # drawn around the cell, to see the ink outside it

OFL_TITLE = "SIL OPEN FONT LICENSE Version 1.1"

PREVIEW_SCALE = 4
PREVIEW_LINES = [
    "!\"#$%&'()*+,-./0123456789:;<=>?",
    "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_",
    "`abcdefghijklmnopqrstuvwxyz{|}~",
    "The quick brown fox: {a[0] = 1;}",
    "0O oO 1lI| 5S 8B :; ., '` \"# @&%",
]


class FontError(Exception):
    """The font or its license cannot be used."""


def read_copyright(path):
    """First line of the license, after a check that it is the OFL 1.1."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    first = text.partition("\n")[0].strip()
    if not first.startswith("Copyright"):
        raise FontError(f"{path}: the first line is not a copyright notice")
    if first.endswith("\\"):
        raise FontError(f"{path}: the copyright notice would continue on the next C line")
    if OFL_TITLE not in text:
        raise FontError(f"{path}: not the {OFL_TITLE}")
    return first


def render(font, code, baseline):
    """Smooth rendering of a character, as the 128 coverages of its cell."""
    char = chr(code)
    advance = font.getlength(char)
    if advance != CELL_W:
        raise FontError(f"0x{code:02X}: advance {advance:g} px instead of {CELL_W}")

    img = Image.new("L", (CELL_W + 2 * MARGIN, CELL_H + 2 * MARGIN), 0)
    ImageDraw.Draw(img).text((MARGIN, MARGIN + baseline), char, font=font, fill=255, anchor="ls")

    box = img.getbbox()
    if box is not None:
        left, top, right, bottom = (v - MARGIN for v in box)
        if left < 0 or top < 0 or right > CELL_W or bottom > CELL_H:
            raise FontError(f"0x{code:02X}: ink outside the cell, "
                            f"x {left}..{right - 1} y {top}..{bottom - 1}")
    return img.crop((MARGIN, MARGIN, MARGIN + CELL_W, MARGIN + CELL_H)).tobytes()


def pack1(coverage, threshold):
    """1 bit per pixel: one byte per row, bit 7 on the left."""
    out = bytearray()
    for start in range(0, len(coverage), 8):
        byte = 0
        for value in coverage[start:start + 8]:
            byte = byte << 1 | (value >= threshold)
        out.append(byte)
    return bytes(out)


def pack4(coverage):
    """4 bits per pixel: two pixels per byte, the high nibble on the left."""
    levels = [(value * 15 + 127) // 255 for value in coverage]
    return bytes(levels[i] << 4 | levels[i + 1] for i in range(0, len(levels), 2))


def convert(font, bpp, baseline, threshold):
    """Packed glyphs by character code, after the checks on the result."""
    glyphs = {}
    seen = {}
    for code in CODES:
        coverage = render(font, code, baseline)
        data = pack1(coverage, threshold) if bpp == 1 else pack4(coverage)
        if code != 0x20 and not any(data):
            raise FontError(f"0x{code:02X}: empty glyph")
        if data in seen:
            raise FontError(f"0x{code:02X}: same glyph as 0x{seen[data]:02X}")
        seen[data] = code
        glyphs[code] = data
    return glyphs


def emit(name, bpp, glyphs, copyright_line, source, options):
    """Text of the C header."""
    glyph_bytes = CELL_W * CELL_H * bpp // 8
    total = glyph_bytes * len(glyphs)
    guard = f"{name.upper()}_H"
    if bpp == 1:
        layout = "one byte per row, bit 7 on the left."
    else:
        layout = "four bytes per row, high nibble on the left."

    lines = []
    a = lines.append

    a("// SPDX-License-Identifier: OFL-1.1")
    a(f"// {copyright_line}")
    a("/*!")
    a("****************************")
    a(f"\\file       {name}.h")
    a("\\brief      Generated by ttf2c.py, do not edit.")
    a("")
    a("\\details")
    a(f"  {len(glyphs)} glyphs of {CELL_W} x {CELL_H} px, 0x{FIRST:02X} to 0x{LAST:02X}, "
      f"{glyph_bytes} bytes each: {layout}")
    for line in source:
        a(f"  - {line}")
    a(f"  - Options: {options}")
    a("****************************")
    a("*/")
    a("")
    a(f"#ifndef {guard}")
    a(f"#define {guard}")
    a("")
    a("#include <stdint.h>")
    a("")
    a(f"static const uint8_t {name}[{total}] = {{")
    for code, data in glyphs.items():
        # The code only: the character itself could be a backslash, which continues the line
        a(f"    // 0x{code:02X}")
        for i in range(0, len(data), 16):
            a("    " + ", ".join(f"0x{b:02X}" for b in data[i:i + 16]) + ",")
    a("};")
    a("")
    a(f"#endif /* {guard} */")
    return "\n".join(lines) + "\n"


def glyph_image(data, bpp):
    """Cell decoded from the packed bytes, as the target will read them."""
    if bpp == 1:
        pixels = bytes(255 * (byte >> bit & 1) for byte in data for bit in range(7, -1, -1))
    else:
        pixels = bytes(17 * level for byte in data for level in (byte >> 4, byte & 15))
    return Image.frombytes("L", (CELL_W, CELL_H), pixels)


def preview(glyphs, bpp):
    """Sheet of all the characters and two sample lines, enlarged."""
    columns = max(len(line) for line in PREVIEW_LINES)
    sheet = Image.new("L", (columns * CELL_W, len(PREVIEW_LINES) * CELL_H), 0)
    for row, line in enumerate(PREVIEW_LINES):
        for column, char in enumerate(line):
            sheet.paste(glyph_image(glyphs[ord(char)], bpp), (column * CELL_W, row * CELL_H))
    return sheet.resize((sheet.width * PREVIEW_SCALE, sheet.height * PREVIEW_SCALE),
                        Image.NEAREST)


def integer(low, high):
    """Type of an option: an integer within bounds."""
    def check(text):
        value = int(text)
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"{value} is not within {low}..{high}")
        return value
    check.__name__ = "integer"
    return check


def identifier(text):
    """Type of an option: a C identifier in lower case."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a lower case C identifier")
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ttf")
    p.add_argument("--bpp", type=int, choices=(1, 4), required=True,
                   help="bits per pixel")
    p.add_argument("--name", type=identifier, required=True,
                   help="C array, and header name without its extension")
    p.add_argument("--license", required=True,
                   help="license of the font; its first line is the copyright notice")
    p.add_argument("--size", type=integer(1, 32), default=13,
                   help="font size in pixels (default 13)")
    p.add_argument("--baseline", type=integer(0, CELL_H), default=13,
                   help="baseline, in rows from the top of the cell (default 13)")
    p.add_argument("--threshold", type=integer(1, 255), default=128,
                   help="coverage that sets a pixel, 1 bit only (default 128)")
    p.add_argument("--out", default="-",
                   help="output file, or - for stdout (default)")
    p.add_argument("--preview", metavar="PNG",
                   help="also write a picture of the glyphs")
    args = p.parse_args()

    try:
        with open(args.ttf, "rb") as f:
            ttf = f.read()
        copyright_line = read_copyright(args.license)
        font = ImageFont.truetype(io.BytesIO(ttf), args.size,
                                  layout_engine=ImageFont.Layout.BASIC)
        glyphs = convert(font, args.bpp, args.baseline, args.threshold)
    except (OSError, UnicodeDecodeError, FontError) as e:
        sys.exit(f"ttf2c.py: {e}")

    source = [
        "Font: " + " ".join(font.getname()),
        f"SHA-256: {hashlib.sha256(ttf).hexdigest()}",
        f"Pillow {PIL.__version__}, FreeType {features.version('freetype2')}",
    ]
    options = f"--bpp {args.bpp} --size {args.size} --baseline {args.baseline}"
    if args.bpp == 1:
        options += f" --threshold {args.threshold}"

    text = emit(args.name, args.bpp, glyphs, copyright_line, source, options)
    if args.out == "-":
        sys.stdout.write(text)
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    if args.preview:
        preview(glyphs, args.bpp).save(args.preview)

    total = sum(len(data) for data in glyphs.values())
    print(f"{args.ttf} -> {args.out}", file=sys.stderr)
    print(f"  {len(glyphs)} glyphs, {args.bpp} bit(s) per pixel, {total} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
