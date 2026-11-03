// SPDX-License-Identifier: MIT
/*!
****************************
\file       07-lcd-logo/main.c
\brief      Show a palette-indexed logo over a gradient splash screen.

\author     Z. BEN-AKKA
\version    1.7
\date       29/10/2026

\details
  1) Brings up the LTDC (common/lcd), with a black background.
  2) Draws the vertical gradient and the logo in the framebuffer (common/fb).
  3) Only then enables layer 1, and last powers the panel and its backlight:
     the undriven panel is white, so the first image shown is complete.
  The logo (logo.h, from tools/png2c.py) is 8-bit indexed with an RGB565
  palette, half the flash of RGB565; index 0 is transparent.

\section lcd_logo_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 30/08/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md.        |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Shared functions moved to common/.                  |
| 1.3     | 10/10/2026 | Z. BEN-AKKA | Generic drivers, board specifics from common/board. |
| 1.4     | 11/10/2026 | Z. BEN-AKKA | Board wiring defined in the application.            |
| 1.5     | 11/10/2026 | Z. BEN-AKKA | Board wiring from stm32f7508-dk/.                   |
| 1.6     | 28/10/2026 | Z. BEN-AKKA | Logo shown at once: frame drawn before the layer.   |
| 1.7     | 29/10/2026 | Z. BEN-AKKA | Framebuffer placed by the linker in .framebuffer.   |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "delay/delay.h"
#include "fb/fb.h"
#include "ltdc/ltdc.h"
#include "logo.h"
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

/// RGB565 framebuffer in SRAM (linker section .framebuffer): too large for the 64 KB DTCM.
static volatile uint16_t fb_pixels[LCD_WIDTH * LCD_HEIGHT]
    __attribute__((section(".framebuffer"), aligned(8)));

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {fb_pixels, LCD_WIDTH, LCD_HEIGHT};

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
\brief  Application entry point: splash screen with the logo.
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
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // Black background until layer 1 is on

  // The whole frame is drawn before layer 1 shows it: the first image is complete
  FbGradient(&screen, 10, 22, 46, 4, 8, 18); // dark blue to near-black, every pixel
  draw_logo((LCD_WIDTH - LOGO_WIDTH) / 2U, (LCD_HEIGHT - LOGO_HEIGHT) / 2U);
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, (uint32_t)fb_pixels);

  // Panel and backlight last: the undriven panel is white, it must get the frame at once
  BoardLcdPowerOn();
  UartPuts(console, "logo drawn\n");

  if (LtdcFifoUnderrun()) {
    UartPuts(console, "FIFO underrun\n");
  }

  while (1) {
    DelayMs(1000);
  }
}
