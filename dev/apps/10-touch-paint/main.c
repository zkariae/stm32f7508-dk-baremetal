// SPDX-License-Identifier: MIT
/*!
****************************
\file       10-touch-paint/main.c
\brief      Paint with a finger on the touch screen.

\author     Z. BEN-AKKA
\version    1.0
\date       19/11/2026

\details
  1) Brings up the LTDC and draws the whole screen before showing it: a bar
     of 32 px at the top (8 colour swatches of 48 px, then a grey clear area
     of 96 px; a white mark under the selected colour), and a white canvas.
  2) Configures the FT5336 bus (common/touch), waits until 300 ms after start
     (the FT5336 answers 200 ms after its reset) and prints its chip ID.
  3) Polls the touch screen every 10 ms. A touch down prints its coordinates
     and, in the bar, selects a colour or clears the canvas. On the canvas,
     circles join the previous point to the current one, so a fast stroke has
     no gaps.
  Built as 10-touch-paint-app, run in place from QSPI behind the 08 bootloader.

\section touch_paint_main_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 19/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "defines.h"
#include "delay/delay.h"
#include "fb/fb.h"
#include "ltdc/ltdc.h"
#include "rcc/rcc.h"
#include "touch/touch.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

#define BAR_H        32U  ///< Height of the bar at the top.
#define SWATCH_H     28U  ///< Height of a colour swatch; the selection mark is below.
#define SWATCH_W     48U  ///< Width of a colour swatch.
#define SWATCH_COUNT 8U   ///< Number of colours.
#define CLEAR_X      384U ///< Left edge of the clear area: SWATCH_COUNT * SWATCH_W.

#define BRUSH_R 4 ///< Brush radius, pixels.
#define STEP_PX 2 ///< Distance between two circles of a stroke, pixels.

#define TOUCH_START_MS 300U ///< FT5336 ready 200 ms after reset (FT5336GQQ Table 3-5), plus margin.
#define POLL_MS        10U  ///< Polling period; the FT5336 report rate is NOT VERIFIED.

/* RGB565 colours */
#define WHITE  0xFFFFU
#define GREY   0x8410U
#define BAR_BG 0x2104U ///< Dark grey under the swatches.

/// Colours of the swatches, from the left.
static const uint16_t palette[SWATCH_COUNT] = {
    0x0000U, // black
    0xF800U, // red
    0x07E0U, // green
    0x001FU, // blue
    0xFFE0U, // yellow
    0x07FFU, // cyan
    0xF81FU, // magenta
    0xFD20U, // orange
};

/// RGB565 framebuffer in SRAM (linker section .framebuffer): too large for the 64 KB DTCM.
static volatile uint16_t fb_pixels[LCD_WIDTH * LCD_HEIGHT]
    __attribute__((section(".framebuffer"), aligned(8)));

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {fb_pixels, LCD_WIDTH, LCD_HEIGHT};

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

/*!
\brief  Print a byte as two hexadecimal digits.
*/
static void put_hex8(uint8_t v)
{
  static const char digits[] = "0123456789ABCDEF";

  UartPutc(console, digits[v >> 4]);
  UartPutc(console, digits[v & 0x0FU]);
}

/*!
\brief  Absolute value; no C library in this build.
*/
static int32_t abs32(int32_t v)
{
  return (v < 0) ? -v : v;
}

/*!
\brief  Draw the bar: the swatches, the selection mark and the clear area.
\param  selected  Index of the selected colour.
*/
static void draw_bar(uint32_t selected)
{
  for (uint32_t i = 0; i < SWATCH_COUNT; i++) {
    FbRect(&screen, i * SWATCH_W, 0, SWATCH_W, SWATCH_H, palette[i]);
    FbRect(&screen, i * SWATCH_W, SWATCH_H, SWATCH_W, BAR_H - SWATCH_H,
           (i == selected) ? WHITE : BAR_BG);
  }
  FbRect(&screen, CLEAR_X, 0, LCD_WIDTH - CLEAR_X, BAR_H, GREY);
}

/*!
\brief  Paint the canvas white.
*/
static void clear_canvas(void)
{
  FbRect(&screen, 0, BAR_H, LCD_WIDTH, LCD_HEIGHT - BAR_H, WHITE);
}

/*!
\brief  Draw one brush circle, kept below the bar.
*/
static void brush(int32_t x, int32_t y, uint16_t colour)
{
  if (y < (int32_t)BAR_H + BRUSH_R) {
    y = (int32_t)BAR_H + BRUSH_R;
  }
  FbCircle(&screen, x, y, BRUSH_R, colour);
}

/*!
\brief  Join two points with circles every STEP_PX pixels, so a fast stroke has no gaps.
*/
static void stroke(int32_t x0, int32_t y0, int32_t x1, int32_t y1, uint16_t colour)
{
  int32_t dx = x1 - x0;
  int32_t dy = y1 - y0;
  int32_t len = (abs32(dx) > abs32(dy)) ? abs32(dx) : abs32(dy);
  int32_t steps = len / STEP_PX;

  for (int32_t i = 1; i <= steps; i++) {
    brush(x0 + dx * i / steps, y0 + dy * i / steps, colour);
  }
  brush(x1, y1, colour);
}

/*!
\brief  Print a message and stop.
*/
static void halt(const char *msg)
{
  UartPuts(console, msg);
  while (1) {
    DelayMs(1000);
  }
}

/*!
\brief  Application entry point: paint on the touch screen.
\return Never returns.
*/
int main(void)
{
  uint32_t selected = 0;   // black
  uint32_t was_down = 0;   // a finger was on the screen at the previous poll
  uint32_t on_canvas = 0;  // the previous point was on the canvas
  uint32_t read_error = 0; // the previous read failed
  int32_t px = 0;
  int32_t py = 0;
  uint8_t id;

  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  UartInit(console, APB2_HZ, BAUDRATE);
  UartPuts(console, "\ntouch paint\n");

  RccInitPixelClock9MHz();
  BoardLcdPinsInit();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // Black background until layer 1 is on

  // The whole screen is drawn before layer 1 shows it: the first image is complete
  draw_bar(selected);
  clear_canvas();
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, (uint32_t)fb_pixels);
  BoardLcdPowerOn();

  if (TouchInit(&BOARD_I2C_TOUCH) != SUCCESS) {
    halt("touch: I2C init error\n");
  }
  while (SysTickMs() < TOUCH_START_MS) {}
  if (TouchReadId(&BOARD_I2C_TOUCH, FT5336_ADDR, &id) != SUCCESS) {
    halt("touch: chip_id error\n");
  }
  UartPuts(console, "touch: chip_id=0x");
  put_hex8(id);
  UartPuts(console, "\n");

  while (1) {
    uint32_t points;
    TouchPoint p;

    if (TouchRead(&BOARD_I2C_TOUCH, FT5336_ADDR, &points, &p) != SUCCESS) {
      if (!read_error) {
        UartPuts(console, "touch: read error\n");
      }
      read_error = 1;
      was_down = 0;
      DelayMs(POLL_MS);
      continue;
    }
    read_error = 0;

    if (points == 0U) {
      was_down = 0;
    } else {
      int32_t x = p.x;
      int32_t y = p.y;

      if (!was_down) {
        // Touch down: coordinates on the console (C5), then the bar actions
        UartPuts(console, "touch: x=");
        UartPutDec(console, p.x);
        UartPuts(console, " y=");
        UartPutDec(console, p.y);
        UartPuts(console, "\n");
        if (p.y < BAR_H) {
          if (p.x < CLEAR_X) {
            selected = p.x / SWATCH_W;
            draw_bar(selected);
          } else {
            clear_canvas();
          }
        }
      }
      if (p.y >= BAR_H) {
        if (was_down && on_canvas) {
          stroke(px, py, x, y, palette[selected]);
        } else {
          brush(x, y, palette[selected]);
        }
        on_canvas = 1;
      } else {
        on_canvas = 0;
      }
      px = x;
      py = y;
      was_down = 1;
    }
    DelayMs(POLL_MS);
  }
}
