// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/font/font.c
\brief      Fixed-width bitmap fonts.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  API documented in font.h.

\section font_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "font/font.h"

#include <stdint.h>

#include "font/mono_8x16_1bpp.h"
#include "font/mono_8x16_4bpp.h"

#define MONO_WIDTH  8U    ///< Pixels per row of the 8x16 fonts.
#define MONO_HEIGHT 16U   ///< Rows of the 8x16 fonts.
#define MONO_FIRST  0x20U ///< First code: space.
#define MONO_COUNT  95U   ///< Codes 0x20 to 0x7E.

// The generated data must match the descriptors
_Static_assert(sizeof(mono_8x16_1bpp) == MONO_COUNT * MONO_HEIGHT * MONO_WIDTH / 8U, "1bpp size");
_Static_assert(sizeof(mono_8x16_4bpp) == MONO_COUNT * MONO_HEIGHT * MONO_WIDTH / 2U, "4bpp size");

const Font FONT_MONO_8X16_1BPP = {
    .glyphs = mono_8x16_1bpp,
    .width = MONO_WIDTH,
    .height = MONO_HEIGHT,
    .bpp = 1U,
    .first = MONO_FIRST,
    .count = MONO_COUNT,
};

const Font FONT_MONO_8X16_4BPP = {
    .glyphs = mono_8x16_4bpp,
    .width = MONO_WIDTH,
    .height = MONO_HEIGHT,
    .bpp = 4U,
    .first = MONO_FIRST,
    .count = MONO_COUNT,
};

const uint8_t *FontGlyph(const Font *font, uint8_t code)
{
  const uint32_t glyph_bytes = (font->width * font->bpp + 7U) / 8U * font->height;
  uint32_t index = code - font->first; // Wraps below first: one comparison covers both ends

  if (index >= font->count) {
    index = '?' - font->first; // Every font of this module has it
  }
  return &font->glyphs[index * glyph_bytes];
}
