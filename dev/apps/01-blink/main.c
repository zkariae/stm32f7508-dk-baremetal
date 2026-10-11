// SPDX-License-Identifier: MIT
/*!
****************************
\file       01-blink/main.c
\brief      Blink BOARD_LED_LD1 with a busy-wait loop.

\author     Z. BEN-AKKA
\version    1.5
\date       11/10/2026

\details
  Bare-metal loop that:
  1) Enables the GPIOI clock.
  2) Configures PI1 (BOARD_LED_LD1) as a push-pull output.
  3) Toggles it forever with a software delay.
  Runs on the 16 MHz HSI reset clock; no PLL, no interrupts.

\section blink_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 29/08/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md.        |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Shared functions moved to common/.                  |
| 1.3     | 10/10/2026 | Z. BEN-AKKA | Generic drivers, board specifics from common/board. |
| 1.4     | 11/10/2026 | Z. BEN-AKKA | Board wiring defined in the application.            |
| 1.5     | 11/10/2026 | Z. BEN-AKKA | Board wiring from stm32f7508-dk/.                   |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "delay/delay.h"
#include "led/led.h"

/*!
\brief  Application entry point: blink BOARD_LED_LD1 forever.
\return Never returns.
*/
int main(void)
{
  LedInit(&BOARD_LED_LD1);

  while (1) {
    LedToggle(&BOARD_LED_LD1);
    DelayCycles(1000000);
  }
}
