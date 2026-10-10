// SPDX-License-Identifier: MIT
/*!
****************************
\file       06-lcd-layer/main.c
\brief      Display an RGB565 framebuffer through LTDC layer 1.

\author     Z. BEN-AKKA
\version    1.3
\date       10/10/2026

\details
  1) Brings up the LTDC as in 05-lcd-init.
  2) Clears the RGB565 framebuffer in SRAM1 (common/fb) and enables layer 1.
  3) Draws colour bars and a grey ramp.
  4) Animates a square and reports LTDC FIFO underruns over USART1.

\section lcd_layer_main_c_version_history Version history
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
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

#define FB_ADDR  0x20010000UL                  ///< SRAM1: the LTDC cannot reach the DTCM.
#define FB_BYTES (LCD_WIDTH * LCD_HEIGHT * 2U) ///< RGB565 framebuffer size.

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {(volatile uint16_t *)FB_ADDR, LCD_WIDTH, LCD_HEIGHT};

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

/*!
\brief  Draw eight colour bars over a horizontal grey ramp.

\details
  A wrong data line shows in the bars, missing low bits as banding in the ramp.
*/
static void draw_test_pattern(void)
{
  static const uint8_t bars[8][3] = {
      {255, 255, 255}, {255, 255, 0}, {0, 255, 255}, {0, 255, 0},
      {255, 0, 255},   {255, 0, 0},   {0, 0, 255},   {0, 0, 0},
  };

  const uint32_t bar_w = LCD_WIDTH / 8U;
  for (uint32_t i = 0; i < 8U; i++) {
    FbRect(&screen, i * bar_w, 0, bar_w, LCD_HEIGHT / 2U,
           Rgb565(bars[i][0], bars[i][1], bars[i][2]));
  }

  for (uint32_t x = 0; x < LCD_WIDTH; x++) {
    uint8_t v = (uint8_t)(x * 255U / (LCD_WIDTH - 1U));
    FbRect(&screen, x, LCD_HEIGHT / 2U, 1, LCD_HEIGHT / 2U, Rgb565(v, v, v));
  }
}

/*!
\brief  Print the framebuffer address and size.
*/
static void print_framebuffer_info(void)
{
  UartPuts(console, "framebuffer at ");
  UartPutHex32(console, FB_ADDR);
  UartPuts(console, ", ");
  UartPutDec(console, FB_BYTES);
  UartPuts(console, " bytes\n");
}

/*!
\brief  Report an LTDC FIFO underrun on the console.
*/
static void check_fifo_underrun(void)
{
  if (LtdcFifoUnderrun()) {
    UartPuts(console, "FIFO underrun\n");
  }
}

/*!
\brief  Print the frame counter every 100 frames.
\param  frames  Frames drawn so far.
*/
static void report_frames(uint32_t frames)
{
  if (frames % 100U == 0U) {
    UartPuts(console, "frames ");
    UartPutDec(console, frames);
    UartPuts(console, "\n");
  }
}

/*!
\brief  Application entry point: show a test pattern and a bouncing square.
\return Never returns.
*/
int main(void)
{
  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  UartInit(console, APB2_HZ, BAUDRATE);

  UartPuts(console, "\nLTDC layer\n");
  UartPuts(console, "----------\n");
  print_framebuffer_info();

  RccInitPixelClock9MHz();
  BoardLcdPinsInit();
  BoardLcdPowerOn();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // black behind the layer

  // Clear before enabling the layer: SRAM1 is random at reset
  FbClear(&screen, Rgb565(0, 0, 0));

  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, FB_ADDR);
  UartPuts(console, "layer 1 enabled, RGB565\n\n");

  draw_test_pattern();
  UartPuts(console, "colour bars and grey ramp\n");

  // Square bouncing horizontally, redrawn every 40 ms
  int32_t x = 20;
  int32_t dx = 4;
  const int32_t size = 40;
  const uint32_t y = LCD_HEIGHT / 2U - (uint32_t)size / 2U;

  uint32_t frames = 0;
  while (1) {
    FbRect(&screen, (uint32_t)x, y, (uint32_t)size, (uint32_t)size, Rgb565(0, 0, 0));

    x += dx;
    if (x <= 0 || x + size >= (int32_t)LCD_WIDTH) {
      dx = -dx;
    }

    FbRect(&screen, (uint32_t)x, y, (uint32_t)size, (uint32_t)size, Rgb565(255, 140, 0));

    check_fifo_underrun();
    report_frames(++frames);

    DelayMs(40);
  }
}
