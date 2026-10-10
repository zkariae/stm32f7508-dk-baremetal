// SPDX-License-Identifier: MIT
/*!
****************************
\file       07-lcd-logo/main.c
\brief      Fade a palette-indexed logo in over a gradient splash screen.

\author     Z. BEN-AKKA
\version    1.3
\date       10/10/2026

\details
  1) Brings up the LTDC and layer 1 (common/lcd, common/fb).
  2) Draws a vertical gradient background.
  3) Fades the logo in, then draws it opaque.
  The logo (logo.h, from tools/png2c.py) is 8-bit indexed with an RGB565
  palette, half the flash of RGB565; index 0 is transparent.

\section lcd_logo_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 30/08/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md.        |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Shared functions moved to common/.                  |
| 1.3     | 10/10/2026 | Z. BEN-AKKA | Generic drivers, board specifics from common/board. |
****************************
*/

#include <stdint.h>

#include "defines.h"
#include "board/board.h"
#include "delay/delay.h"
#include "fb/fb.h"
#include "ltdc/ltdc.h"
#include "logo.h"
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

#define FB_ADDR  0x20010000UL                  ///< SRAM1: the LTDC cannot reach the DTCM.
#define FB_BYTES (LCD_WIDTH * LCD_HEIGHT * 2U) ///< RGB565 framebuffer size.

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {(volatile uint16_t *)FB_ADDR, LCD_WIDTH, LCD_HEIGHT};

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

/*!
\brief  Draw the logo opaque at (x0, y0); index 0 pixels are skipped.
*/
static void draw_logo(uint32_t x0, uint32_t y0)
{
  for (uint32_t y = 0; y < LOGO_HEIGHT; y++) {
    if (y0 + y >= LCD_HEIGHT)
      break;

    const uint8_t *row = &logo_data[y * LOGO_WIDTH];
    volatile uint16_t *dst = &screen.pixels[(y0 + y) * LCD_WIDTH + x0];

    for (uint32_t x = 0; x < LOGO_WIDTH; x++) {
      if (x0 + x >= LCD_WIDTH)
        break;
      uint8_t idx = row[x];
      if (idx != 0U) {
        dst[x] = logo_palette[idx];
      }
    }
  }
}

/*!
\brief  Blend the logo over the framebuffer with a global alpha.

\details
  The blend is done per RGB565 channel, without unpacking to 8-8-8.

\param  x0     Left edge.
\param  y0     Top edge.
\param  alpha  0 = invisible, 255 = opaque.
*/
static void draw_logo_alpha(uint32_t x0, uint32_t y0, uint8_t alpha)
{
  for (uint32_t y = 0; y < LOGO_HEIGHT; y++) {
    if (y0 + y >= LCD_HEIGHT)
      break;

    const uint8_t *row = &logo_data[y * LOGO_WIDTH];
    volatile uint16_t *dst = &screen.pixels[(y0 + y) * LCD_WIDTH + x0];

    for (uint32_t x = 0; x < LOGO_WIDTH; x++) {
      if (x0 + x >= LCD_WIDTH)
        break;
      uint8_t idx = row[x];
      if (idx == 0U)
        continue;

      uint16_t src = logo_palette[idx];
      uint16_t bg = dst[x];

      uint32_t sr = (src >> 11) & 0x1FU, sg = (src >> 5) & 0x3FU, sb = src & 0x1FU;
      uint32_t br = (bg >> 11) & 0x1FU, bg2 = (bg >> 5) & 0x3FU, bb = bg & 0x1FU;

      uint32_t r = (sr * alpha + br * (255U - alpha)) / 255U;
      uint32_t g = (sg * alpha + bg2 * (255U - alpha)) / 255U;
      uint32_t b = (sb * alpha + bb * (255U - alpha)) / 255U;

      dst[x] = (uint16_t)((r << 11) | (g << 5) | b);
    }
  }
}

/*!
\brief  Print the logo size and its flash footprint.
*/
static void print_logo_info(void)
{
  UartPuts(console, "\nsplash screen\n");
  UartPuts(console, "-------------\n");
  UartPuts(console, "logo ");
  UartPutDec(console, LOGO_WIDTH);
  UartPuts(console, " x ");
  UartPutDec(console, LOGO_HEIGHT);
  UartPuts(console, ", ");
  UartPutDec(console, LOGO_WIDTH * LOGO_HEIGHT + 512U);
  UartPuts(console, " bytes of flash\n");
}

/*!
\brief  Fade the logo in over the gradient in about one second.

\details
  The background is redrawn at each step so that partial blends do not
  accumulate.

\param  x  Left edge of the logo.
\param  y  Top edge of the logo.
*/
static void fade_in_logo(uint32_t x, uint32_t y)
{
  for (uint32_t a = 0; a <= 255U; a += 5U) {
    FbGradient(&screen, 10, 22, 46, 4, 8, 18);
    draw_logo_alpha(x, y, (uint8_t)a);
    DelayMs(16);
  }
}

/*!
\brief  Application entry point: splash screen with a fading logo.
\return Never returns.
*/
int main(void)
{
  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  UartInit(console, APB2_HZ, BAUDRATE);

  print_logo_info();

  RccInitPixelClock9MHz();
  BoardLcdPinsInit();
  BoardLcdPowerOn();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U);

  FbClear(&screen, Rgb565(0, 0, 0));
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, FB_ADDR);

  FbGradient(&screen, 10, 22, 46, 4, 8, 18); // dark blue to near-black

  const uint32_t x = (LCD_WIDTH - LOGO_WIDTH) / 2U;
  const uint32_t y = (LCD_HEIGHT - LOGO_HEIGHT) / 2U;

  fade_in_logo(x, y);
  draw_logo(x, y);
  UartPuts(console, "logo drawn\n");

  if (LtdcFifoUnderrun()) {
    UartPuts(console, "FIFO underrun\n");
  }

  while (1) {
    DelayMs(1000);
  }
}
