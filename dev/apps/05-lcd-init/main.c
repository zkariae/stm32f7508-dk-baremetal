// SPDX-License-Identifier: MIT
/*!
****************************
\file       05-lcd-init/main.c
\brief      Drive the LCD panel from the LTDC with a solid background colour.

\author     Z. BEN-AKKA
\version    1.5
\date       11/10/2026

\details
  1) Runs the core at 216 MHz and the PLLSAI at a 9 MHz pixel clock.
  2) Sets the 28 LTDC pins to AF14 and powers the panel.
  3) Programs the RK043FN48H timings; no layer, no framebuffer.
  4) Cycles the background colour (red, green, blue, white) and logs the
     LTDC registers over USART1.

\section lcd_init_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 30/08/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md.        |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Shared functions moved to common/.                  |
| 1.3     | 10/10/2026 | Z. BEN-AKKA | Generic drivers, board specifics from common/board. |
| 1.4     | 11/10/2026 | Z. BEN-AKKA | Board wiring defined in the application.            |
| 1.5     | 11/10/2026 | Z. BEN-AKKA | Board wiring from boards/stm32f7508-dk.             |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "delay/delay.h"
#include "ltdc/ltdc.h"
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

/*!
\brief  Print the LTDC timing and control registers.
*/
static void print_ltdc_registers(void)
{
  UartPuts(console, "LTDC_SSCR = ");
  UartPutHex32(console, LTDC_SSCR);
  UartPuts(console, "\n");
  UartPuts(console, "LTDC_BPCR = ");
  UartPutHex32(console, LTDC_BPCR);
  UartPuts(console, "\n");
  UartPuts(console, "LTDC_AWCR = ");
  UartPutHex32(console, LTDC_AWCR);
  UartPuts(console, "\n");
  UartPuts(console, "LTDC_TWCR = ");
  UartPutHex32(console, LTDC_TWCR);
  UartPuts(console, "\n");
  UartPuts(console, "LTDC_GCR  = ");
  UartPutHex32(console, LTDC_GCR);
  UartPuts(console, "\n");
}

/*!
\brief  Print the frame size and refresh rate computed from the panel timings.
*/
static void print_frame_rate(void)
{
  uint32_t total_w = LCD_HSW + LCD_HBP + LCD_WIDTH + LCD_HFP;
  uint32_t total_h = LCD_VSW + LCD_VBP + LCD_HEIGHT + LCD_VFP;
  UartPuts(console, "\nframe = ");
  UartPutDec(console, total_w);
  UartPuts(console, " x ");
  UartPutDec(console, total_h);
  UartPuts(console, " -> ");
  UartPutDec(console, PIXEL_CLOCK_HZ / (total_w * total_h));
  UartPuts(console, " Hz\n\n");
}

/*!
\brief  Print the current colour name and the LTDC current display status.
\param  name  Colour name.
*/
static void print_colour_status(const char *name)
{
  UartPuts(console, name);
  UartPuts(console, "  CDSR = ");
  UartPutHex32(console, LTDC_CDSR);
  UartPuts(console, "\n");
}

/*!
\brief  Application entry point: bring up the LTDC, then cycle the background colour.
\return Never returns.
*/
int main(void)
{
  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  UartInit(console, APB2_HZ, BAUDRATE);

  UartPuts(console, "\nLTDC bring-up\n");
  UartPuts(console, "-------------\n");

  RccInitPixelClock9MHz();
  UartPuts(console, "PLLSAI locked, pixel clock 9 MHz\n");

  BoardLcdPinsInit();
  UartPuts(console, "28 pins set to AF14\n");

  BoardLcdPowerOn();
  UartPuts(console, "panel and backlight on\n");

  LtdcInit(&BOARD_LCD_TIMING, 0x000000FFU); // blue
  UartPuts(console, "LTDC enabled\n\n");

  print_ltdc_registers();
  print_frame_rate();

  // Cycling colours shows a live frame rather than a stuck data line
  static const uint32_t colours[] = {
      0x00FF0000U, // red
      0x0000FF00U, // green
      0x000000FFU, // blue
      0x00FFFFFFU, // white
  };
  static const char *names[] = {"red", "green", "blue", "white"};

  uint32_t i = 0;
  while (1) {
    LtdcSetBackground(colours[i]);
    print_colour_status(names[i]);

    i = (i + 1U) % 4U;
    DelayMs(1500);
  }
}
