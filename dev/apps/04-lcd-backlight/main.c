// SPDX-License-Identifier: MIT
/*!
****************************
\file       04-lcd-backlight/main.c
\brief      Power up the LCD panel and cycle its backlight.

\author     Z. BEN-AKKA
\version    1.5
\date       11/10/2026

\details
  Checks the panel power path before any LTDC configuration:
  1) Drives PI12 (LCD_DISP) high to enable the panel.
  2) Drives PK3 (LCD_BL_CTRL) high to enable the backlight.
  3) Cycles the backlight (2 s on, 1 s off) and logs over USART1.
  Expected result: an even pale grey screen (panel lit, no image yet).

\section lcd_backlight_main_c_version_history Version history
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
#include "led/led.h"
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

/*!
\brief  Print the test header and the pins about to be driven.
*/
static void print_banner(void)
{
  UartPuts(console, "\nLCD power-up test\n");
  UartPuts(console, "-----------------\n");

  UartPuts(console, "PI12 LCD_DISP    -> high\n");
  UartPuts(console, "PK3  LCD_BL_CTRL -> high\n");
}

/*!
\brief  Print what the screen should show once powered.
*/
static void print_expected_result(void)
{
  UartPuts(console, "\nExpect an even pale grey screen.\n");
  UartPuts(console, "Black means the panel or backlight is not coming up.\n");
  UartPuts(console, "No LTDC yet, so no image — grey is the correct result.\n\n");
}

/*!
\brief  Application entry point: power the panel, then cycle the backlight.
\return Never returns.
*/
int main(void)
{
  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  UartInit(console, APB2_HZ, BAUDRATE);
  LedInit(&BOARD_LED_LD1);

  print_banner();
  BoardLcdPowerOn();
  print_expected_result();

  while (1) {
    LedOn(&BOARD_LED_LD1);
    BoardLcdBacklightOn();
    DelayMs(2000);

    LedOff(&BOARD_LED_LD1);
    BoardLcdBacklightOff();
    DelayMs(1000);

    UartPuts(console, "backlight cycle\n");
  }
}
