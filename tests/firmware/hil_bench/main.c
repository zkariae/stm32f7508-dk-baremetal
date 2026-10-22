// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Entry point of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.0
\date       22/10/2026

\details
  Firmware of the hil-bench image, which implements tests/protocol.md.
  Only records defined by the protocol may be sent on the link (section 2.3),
  so this entry point sends nothing yet: it starts USART1 at 115200 baud,
  which keeps the TX line idle, and waits. The readiness banner and the
  request handling come with the protocol firmware. UART driver diagnostics
  live in the separate uart-diag image (tests/firmware/uart_diag/).

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 22/10/2026 | Z. BEN-AKKA | Initial version: silent protocol entry point. |
****************************
*/

#include "board.h"

int main(void)
{
  UartInit(&BOARD_UART_VCP, HSI_HZ, 115200U); // No clock setup: the core runs from HSI at reset.

  for (;;) {}
}
