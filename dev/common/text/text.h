// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/text/text.h
\brief      Text drawing into an RGB565 framebuffer.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  Draws the glyphs of a Font into a Framebuffer, at 1 bit or 4 bits per pixel.
  The colours come from a TextPalette, computed once per pair of colours: the
  framebuffer is never read. Control characters, wrap and cursor belong to the
  caller.

\section text_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef TEXT_H
#define TEXT_H

#include <stdint.h>

#include "fb/fb.h"
#include "font/font.h"

#define TEXT_LEVELS 16U ///< Colours from the background (0) to the text (15).

/// Colours of a text, from its background to its full colour.
typedef struct {
  uint16_t levels[TEXT_LEVELS]; ///< RGB565 colours; a 1-bit font uses the first and the last.
} TextPalette;

/*!
\brief   Compute the palette of a pair of colours.
\details Level l of each RGB565 component is, in integers and rounded to the
         nearest, (background * (15 - l) + colour * l + 7) / 15. Level 0 is the
         background and level 15 the colour, exactly.
\param   palette     Output: palette.
\param   colour      RGB565 colour of the text.
\param   background  RGB565 colour behind the text.
*/
void TextPaletteInit(TextPalette *palette, uint16_t colour, uint16_t background);

/*!
\brief  Draw a character, background included.
\param  fb       Framebuffer; the part of the cell outside it is not drawn.
\param  x        Left column of the cell.
\param  y        Top row of the cell.
\param  font     Font.
\param  palette  Palette set by TextPaletteInit().
\param  code     Character code; a code the font does not have is drawn as '?'.
*/
void TextChar(const Framebuffer *fb, uint32_t x, uint32_t y, const Font *font,
              const TextPalette *palette, uint8_t code);

/*!
\brief  Draw characters side by side on one line, without wrap.
\param  fb       Framebuffer; the characters outside it are not drawn.
\param  x        Left column of the first cell.
\param  y        Top row of the cells.
\param  font     Font.
\param  palette  Palette set by TextPaletteInit().
\param  codes    Character codes; a code the font does not have is drawn as '?'.
\param  count    Number of characters.
*/
void TextString(const Framebuffer *fb, uint32_t x, uint32_t y, const Font *font,
                const TextPalette *palette, const uint8_t *codes, uint32_t count);

#endif
