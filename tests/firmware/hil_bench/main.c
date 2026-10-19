// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Initialize USART1 and echo received HIL test bytes.

\author     Z. BEN-AKKA
\version    1.4
\date       19/10/2026

\details
  Starts USART1 at 115200 baud and echoes received bytes for the host-side
  UART RX smoke tests. It echoes received bytes and reports framing errors
  with [FE] and noise errors with [NE]. This diagnostic output is temporary
  and is not the HIL protocol. Markers are deferred until the next valid
  byte, so the host has restored its baud rate before they are sent.

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 16/10/2026 | Z. BEN-AKKA | Add temporary USART1 byte echo for RX check. |
| 1.2     | 16/10/2026 | Z. BEN-AKKA | Report framing errors as [FE] for T3.        |
| 1.3     | 19/10/2026 | Z. BEN-AKKA | Defer [FE] until next valid byte; fix CRLF doubling. |
| 1.4     | 19/10/2026 | Z. BEN-AKKA | Report noise errors as deferred [NE] for T4. |
****************************
*/

#include <stdint.h>

#include "board.h"

int main(void)
{
  UartInit(&BOARD_UART_VCP, 16000000U, 115200U);
  UartRxStart(&BOARD_UART_VCP);

  uint8_t fe_pending = 0u;
  uint8_t ne_pending = 0u;

  for (;;) {
    UartRxEvent event;
    if (UartRxGet(&BOARD_UART_VCP, &event)) {
      if (event <= UART_RX_EVENT_BYTE_MAX) {
        if (fe_pending) {
          UartPuts(&BOARD_UART_VCP, "[FE]\n"); // UartPuts expands \n to CRLF
          fe_pending = 0u;
        }
        if (ne_pending) {
          UartPuts(&BOARD_UART_VCP, "[NE]\n");
          ne_pending = 0u;
        }
        UartPutc(&BOARD_UART_VCP, (char)event);
      } else if (event == UART_RX_EVENT_FRAMING_ERROR) {
        fe_pending = 1u;
      } else if (event == UART_RX_EVENT_NOISE_ERROR) {
        ne_pending = 1u;
      }
    }
  }
}
