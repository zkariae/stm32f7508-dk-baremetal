// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/fb/fb.h
\brief      Drawing into an RGB565 framebuffer.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  Each framebuffer is described by a Framebuffer structure (pixels, size).
  Drawing is clipped to the framebuffer.

\section fb_h_version_history Version history
| Version | Date       | Author      | Description                              |
|:-------:|:----------:|:------------|:-----------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                         |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the framebuffer is a parameter. |
****************************
*/

#ifndef FB_H
#define FB_H

#include <stdint.h>

/// An RGB565 framebuffer, one 16-bit word per pixel, rows contiguous.
typedef struct {
  volatile uint16_t *pixels; ///< First pixel (top left).
  uint32_t width;            ///< Pixels per row.
  uint32_t height;           ///< Rows.
} Framebuffer;

/*!
\brief  Pack 8-bit components into RGB565.
\return 16-bit colour: 5 bits red, 6 green, 5 blue.
*/
static inline uint16_t Rgb565(uint8_t r, uint8_t g, uint8_t b)
{
  return (uint16_t)(((r & 0xF8U) << 8) | ((g & 0xFCU) << 3) | (b >> 3));
}

/*!
\brief  Fill the whole framebuffer with one colour.
\param  fb      Framebuffer.
\param  colour  RGB565 colour.
*/
void FbClear(const Framebuffer *fb, uint16_t colour);

/*!
\brief  Set one pixel; coordinates outside the framebuffer are ignored.
\param  fb      Framebuffer.
\param  x       Column.
\param  y       Row.
\param  colour  RGB565 colour.
*/
void FbPixel(const Framebuffer *fb, uint32_t x, uint32_t y, uint16_t colour);

/*!
\brief  Fill a rectangle.
\param  fb      Framebuffer.
\param  x       Left edge.
\param  y       Top edge.
\param  w       Width in pixels.
\param  h       Height in pixels.
\param  colour  RGB565 colour.
*/
void FbRect(const Framebuffer *fb, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint16_t colour);

/*!
\brief  Fill a circle.
\param  fb      Framebuffer.
\param  cx      Centre column.
\param  cy      Centre row.
\param  r       Radius in pixels.
\param  colour  RGB565 colour.
*/
void FbCircle(const Framebuffer *fb, int32_t cx, int32_t cy, int32_t r, uint16_t colour);

/*!
\brief  Fill the framebuffer with a vertical gradient.
\param  fb  Framebuffer.
\param  r1  Red of the top row, 0 to 255.
\param  g1  Green of the top row.
\param  b1  Blue of the top row.
\param  r2  Red of the bottom row.
\param  g2  Green of the bottom row.
\param  b2  Blue of the bottom row.
*/
void FbGradient(const Framebuffer *fb, uint8_t r1, uint8_t g1, uint8_t b1, uint8_t r2, uint8_t g2,
                uint8_t b2);

#endif
