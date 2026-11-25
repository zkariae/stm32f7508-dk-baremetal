// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/font/font.h
\brief      Fixed-width bitmap fonts.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  Each font is described by a Font structure (glyphs, cell, format, range).
  The glyphs come from JetBrains Mono, converted by dev/tools/ttf2c.py; these
  data are under the OFL 1.1 (OFL.txt), this interface is not.

\section font_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef FONT_H
#define FONT_H

#include <stdint.h>

/// A fixed-width font: glyphs packed one after the other, rows on whole bytes.
typedef struct {
  const uint8_t *glyphs; ///< First byte of the first glyph.
  uint32_t width;        ///< Pixels per row.
  uint32_t height;       ///< Rows.
  uint32_t bpp;          ///< Bits per pixel: 1 (bit 7 on the left) or 4 (high nibble on the left).
  uint32_t first;        ///< Code of the first glyph.
  uint32_t count;        ///< Number of glyphs.
} Font;

extern const Font FONT_MONO_8X16_1BPP; ///< 1 bit per pixel, ASCII 0x20 to 0x7E, 1520 bytes.
extern const Font FONT_MONO_8X16_4BPP; ///< 4 bits per pixel, ASCII 0x20 to 0x7E, 6080 bytes.

/*!
\brief  Find the glyph of a character.
\param  font  Font.
\param  code  Character code; a code the font does not have gives the glyph of '?'.
\return First byte of the glyph: height rows of (width * bpp + 7) / 8 bytes.
*/
const uint8_t *FontGlyph(const Font *font, uint8_t code);

#endif
