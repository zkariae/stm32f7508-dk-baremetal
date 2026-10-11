// SPDX-License-Identifier: MIT
/*!
****************************
\file       08-custombootloader/main.c
\brief      Bootloader: map the QSPI flash and start the application in place.

\author     Z. BEN-AKKA
\version    1.5
\date       11/10/2026

\details
  Runs from the internal flash and:
  1) Resets the N25Q128A and checks its JEDEC ID (common/qspi).
  2) Switches the QUADSPI to memory-mapped mode (0x90000000, 1-1-4 reads).
  3) Checks the application's initial SP and PC.
  4) Enables the I-cache, sets VTOR and jumps to the application (common/boot).
  The core stays on HSI: common/startup.c resets on any other clock source.
  Progress is logged on USART1 (115200 8N1). On failure BOARD_LED_LD1 is steady on
  (QSPI error) or blinks fast (no valid application).

\section custombootloader_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 08/10/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md.        |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Shared functions moved to common/.                  |
| 1.3     | 10/10/2026 | Z. BEN-AKKA | Generic drivers, board specifics from common/board. |
| 1.4     | 11/10/2026 | Z. BEN-AKKA | Board wiring defined in the application.            |
| 1.5     | 11/10/2026 | Z. BEN-AKKA | Board wiring from stm32f7508-dk/.                   |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "defines.h"
#include "boot/boot.h"
#include "delay/delay.h"
#include "led/led.h"
#include "qspi/qspi.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.
#define APP_BASE QSPI_MEM_BASE
#define APP_SIZE (16UL * 1024 * 1024) ///< Whole N25Q128A.

/*!
\brief  Report an error and halt, showing it on BOARD_LED_LD1.
\param  why    Message printed on the console.
\param  blink  0: BOARD_LED_LD1 steady on; non-zero: BOARD_LED_LD1 blinks fast.
*/
static void __attribute__((noreturn)) fail(const char *why, int blink)
{
  UartPuts(console, "boot: ");
  UartPuts(console, why);
  UartPuts(console, ", halted\n");

  LedInit(&BOARD_LED_LD1);
  LedOn(&BOARD_LED_LD1);

  while (1) {
    if (blink) {
      LedToggle(&BOARD_LED_LD1);
    }
    DelayCycles(400000);
  }
}

/*!
\brief  Read and print the flash ID; halt unless it is an N25Q128A.
*/
static void check_flash_id(void)
{
  uint32_t id;

  if (QspiReadJedecId(&id) != SUCCESS) {
    fail("QSPI stuck busy", 0);
  }
  UartPuts(console, "boot: QSPI id ");
  UartPutHex32(console, id);
  UartPuts(console, "\n");
  if (id != N25Q128A_ID) {
    fail("unexpected QSPI flash", 0);
  }
}

/*!
\brief  Read the application's initial SP and PC; halt unless they look valid.
\param  sp  Output: initial stack pointer (vector table word 0).
\param  pc  Output: reset handler address (vector table word 1).
*/
static void read_app_vector(uint32_t *sp, uint32_t *pc)
{
  *sp = REG(APP_BASE);
  *pc = REG(APP_BASE + 4);
  UartPuts(console, "boot: app SP ");
  UartPutHex32(console, *sp);
  UartPuts(console, ", PC ");
  UartPutHex32(console, *pc);
  UartPuts(console, "\n");
  if (!BootAppLooksValid(*sp, *pc, APP_BASE, APP_SIZE)) {
    fail("no application at 0x90000000", 1);
  }
}

/*!
\brief  Enable the I-cache and hand over to the application.

\details
  The application inherits the memory-mapped QUADSPI and its pins (it must
  not reconfigure them), USART1 on PA9, the I-cache, and VTOR on its table.

\param  sp  Initial stack pointer.
\param  pc  Reset handler address.
*/
static void __attribute__((noreturn)) start_app(uint32_t sp, uint32_t pc)
{
  BootICacheEnable();
  UartPuts(console, "boot: jumping\n");
  UartFlush(console);
  BootJump(APP_BASE, sp, pc);
}

/*!
\brief  Bootloader entry point: map the QSPI flash, check the application, start it.
\return Never returns.
*/
int main(void)
{
  UartInit(console, HSI_HZ, BAUDRATE);
  UartPuts(console, "\nboot: 08-custombootloader\n");

  BoardQspiPinsInit();
  QspiInit(N25Q128A_SIZE_LOG2, 0); // HCLK / 1
  if (QspiSoftwareReset() != SUCCESS) {
    fail("QSPI stuck busy", 0);
  }
  check_flash_id();
  if (QspiMemoryMappedQuadOut(N25Q_CMD_QUAD_OUT_READ, N25Q_QUAD_OUT_DUMMY) != SUCCESS) {
    fail("QSPI stuck busy", 0);
  }

  uint32_t sp, pc;
  read_app_vector(&sp, &pc);
  start_app(sp, pc);
}
