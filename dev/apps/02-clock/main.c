// SPDX-License-Identifier: MIT
/*!
****************************
\file       02-clock/main.c
\brief      Run the core at 216 MHz and blink BOARD_LED_LD1 at 1 Hz from SysTick.

\author     Z. BEN-AKKA
\version    1.5
\date       11/10/2026

\details
  1) Starts the 216 MHz clock plan (common/rcc).
  2) Configures SysTick for a 1 ms tick.
  3) Toggles BOARD_LED_LD1 every 500 ms; a wrong clock plan shows as a wrong rate.

\section clock_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 29/08/2026 | Z. BEN-AKKA | Initial version.                                    |
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
#include "led/led.h"
#include "rcc/rcc.h"

/*!
\brief  Application entry point: 216 MHz clock, 1 Hz heartbeat on BOARD_LED_LD1.
\return Never returns.
*/
int main(void)
{
  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  LedInit(&BOARD_LED_LD1);

  while (1) {
    LedOn(&BOARD_LED_LD1);
    DelayMs(500);
    LedOff(&BOARD_LED_LD1);
    DelayMs(500);
  }
}
