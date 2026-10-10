// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/fb/fb.c
\brief      Drawing into an RGB565 framebuffer.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  API documented in fb.h.

\section fb_c_version_history Version history
| Version | Date       | Author      | Description                              |
|:-------:|:----------:|:------------|:-----------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                         |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the framebuffer is a parameter. |
****************************
*/

#include "fb/fb.h"

#include <stdint.h>

void FbClear(const Framebuffer *fb, uint16_t colour)
{
  for (uint32_t i = 0; i < fb->width * fb->height; i++) {
    fb->pixels[i] = colour;
  }
}

void FbPixel(const Framebuffer *fb, uint32_t x, uint32_t y, uint16_t colour)
{
  if (x < fb->width && y < fb->height) {
    fb->pixels[y * fb->width + x] = colour;
  }
}

void FbRect(const Framebuffer *fb, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint16_t colour)
{
  for (uint32_t j = 0; j < h; j++) {
    if (y + j >= fb->height)
      break;
    for (uint32_t i = 0; i < w; i++) {
      if (x + i >= fb->width)
        break;
      fb->pixels[(y + j) * fb->width + (x + i)] = colour;
    }
  }
}

void FbCircle(const Framebuffer *fb, int32_t cx, int32_t cy, int32_t r, uint16_t colour)
{
  // Test every pixel of the bounding box against the radius
  for (int32_t y = -r; y <= r; y++) {
    for (int32_t x = -r; x <= r; x++) {
      if (x * x + y * y <= r * r) {
        FbPixel(fb, (uint32_t)(cx + x), (uint32_t)(cy + y), colour);
      }
    }
  }
}

void FbGradient(const Framebuffer *fb, uint8_t r1, uint8_t g1, uint8_t b1, uint8_t r2, uint8_t g2,
                uint8_t b2)
{
  for (uint32_t y = 0; y < fb->height; y++) {
    uint32_t t = y * 255U / (fb->height - 1U);
    uint8_t r = (uint8_t)((r1 * (255U - t) + r2 * t) / 255U);
    uint8_t g = (uint8_t)((g1 * (255U - t) + g2 * t) / 255U);
    uint8_t b = (uint8_t)((b1 * (255U - t) + b2 * t) / 255U);
    uint16_t c = Rgb565(r, g, b);
    for (uint32_t x = 0; x < fb->width; x++) {
      fb->pixels[y * fb->width + x] = c;
    }
  }
}
