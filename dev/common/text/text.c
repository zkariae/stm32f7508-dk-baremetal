// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/text/text.c
\brief      Text drawing into an RGB565 framebuffer.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  API documented in text.h.

\section text_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "text/text.h"

#include <stdint.h>

#define LEVEL_MAX (TEXT_LEVELS - 1U) ///< Level of the full text colour.

/*!
\brief  Smaller of two values.
*/
static uint32_t min_u32(uint32_t a, uint32_t b)
{
  return (a < b) ? a : b;
}

/*!
\brief  Blend one colour component, rounded to the nearest.
*/
static uint32_t blend(uint32_t background, uint32_t colour, uint32_t level)
{
  return (background * (LEVEL_MAX - level) + colour * level + LEVEL_MAX / 2U) / LEVEL_MAX;
}

void TextPaletteInit(TextPalette *palette, uint16_t colour, uint16_t background)
{
  for (uint32_t level = 0; level < TEXT_LEVELS; level++) {
    const uint32_t r = blend(background >> 11, colour >> 11, level);
    const uint32_t g = blend((background >> 5) & 0x3FU, (colour >> 5) & 0x3FU, level);
    const uint32_t b = blend(background & 0x1FU, colour & 0x1FU, level);

    palette->levels[level] = (uint16_t)((r << 11) | (g << 5) | b);
  }
}

void TextChar(const Framebuffer *fb, uint32_t x, uint32_t y, const Font *font,
              const TextPalette *palette, uint8_t code)
{
  if (x >= fb->width || y >= fb->height) {
    return;
  }

  // Clipped once for the cell, against what is left of the framebuffer: no overflow
  const uint32_t cols = min_u32(font->width, fb->width - x);
  const uint32_t rows = min_u32(font->height, fb->height - y);
  const uint32_t row_bytes = (font->width * font->bpp + 7U) / 8U;
  const uint32_t mask = (1U << font->bpp) - 1U;
  const uint32_t scale = LEVEL_MAX / mask; // 1 bit: 0 or 15; 4 bits: unchanged
  const uint8_t *row = FontGlyph(font, code);
  volatile uint16_t *pixel = &fb->pixels[y * fb->width + x];

  for (uint32_t j = 0; j < rows; j++) {
    for (uint32_t i = 0; i < cols; i++) {
      const uint32_t bit = i * font->bpp; // From the left: the high bits come first
      const uint32_t value = ((uint32_t)row[bit / 8U] >> (8U - font->bpp - bit % 8U)) & mask;

      pixel[i] = palette->levels[value * scale];
    }
    row += row_bytes;
    pixel += fb->width;
  }
}

void TextString(const Framebuffer *fb, uint32_t x, uint32_t y, const Font *font,
                const TextPalette *palette, const uint8_t *codes, uint32_t count)
{
  for (uint32_t i = 0; i < count && x < fb->width; i++) {
    TextChar(fb, x, y, font, palette, codes[i]);
    x += font->width; // x was inside the framebuffer: no overflow
  }
}
