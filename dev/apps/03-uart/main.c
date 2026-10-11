// SPDX-License-Identifier: MIT
/*!
****************************
\file       03-uart/main.c
\brief      Print the clock configuration over USART1 (ST-LINK virtual COM port).

\author     Z. BEN-AKKA
\version    1.5
\date       11/10/2026

\details
  1) Runs the core at 216 MHz with a 1 ms SysTick.
  2) Configures USART1 TX on PA9, 115200 8N1, clocked from APB2 at 108 MHz.
  3) Prints the clock settings and RCC/FLASH/PWR registers read back from
     the chip, then an uptime counter every second while BOARD_LED_LD1 blinks.

\section uart_main_c_version_history Version history
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
#include "led/led.h"
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

/*!
\brief  Print the banner and the configured clock settings.
*/
static void print_banner(void)
{
  UartPuts(console, "\n");
  UartPuts(console, "STM32F750N8 — bare metal, no HAL\n");
  UartPuts(console, "--------------------------------\n");

  UartPuts(console, "SYSCLK   : ");
  UartPutDec(console, SYSCLK_HZ / 1000000U);
  UartPuts(console, " MHz\n");

  UartPuts(console, "APB2     : ");
  UartPutDec(console, APB2_HZ / 1000000U);
  UartPuts(console, " MHz\n");

  UartPuts(console, "Baudrate : ");
  UartPutDec(console, BAUDRATE);
  UartPuts(console, "\n\n");
}

/*!
\brief  Print the clock-related registers as read back from the chip.
*/
static void print_clock_registers(void)
{
  UartPuts(console, "RCC_CFGR   = ");
  UartPutHex32(console, RCC_CFGR);
  UartPuts(console, "\n");

  UartPuts(console, "RCC_PLLCFGR= ");
  UartPutHex32(console, RCC_PLLCFGR);
  UartPuts(console, "\n");

  UartPuts(console, "FLASH_ACR  = ");
  UartPutHex32(console, FLASH_ACR);
  UartPuts(console, "\n");

  UartPuts(console, "PWR_CSR1   = ");
  UartPutHex32(console, PWR_CSR1);
  UartPuts(console, "\n\n");
}

/*!
\brief  Print the uptime line.
\param  seconds  Seconds since boot.
*/
static void print_uptime(uint32_t seconds)
{
  UartPuts(console, "uptime ");
  UartPutDec(console, seconds);
  UartPuts(console, " s\n");
}

/*!
\brief  Application entry point: print the clock setup, then an uptime counter.
\return Never returns.
*/
int main(void)
{
  RccInit216MHz(HSE_HZ);
  SysTickInit(SYSCLK_HZ);
  UartInit(console, APB2_HZ, BAUDRATE);
  LedInit(&BOARD_LED_LD1);

  print_banner();
  print_clock_registers();

  uint32_t seconds = 0;
  while (1) {
    LedOn(&BOARD_LED_LD1);
    DelayMs(500);
    LedOff(&BOARD_LED_LD1);
    DelayMs(500);

    print_uptime(++seconds);
  }
}
