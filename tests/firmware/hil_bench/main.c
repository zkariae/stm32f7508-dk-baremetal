// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Initialize USART1 and echo received HIL test bytes.

\author     Z. BEN-AKKA
\version    1.1
\date       16/10/2026

\details
  Starts USART1 at 115200 baud and echoes received bytes for the host-side
  UART RX smoke test. This raw echo is temporary and is not the HIL protocol.

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                              |
|:-------:|:----------:|:------------|:-----------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                         |
| 1.1     | 16/10/2026 | Z. BEN-AKKA | Add temporary USART1 byte echo for RX check. |
****************************
*/

#include "board.h"

int main(void)
{
  UartInit(&BOARD_UART_VCP, 16000000U, 115200U);
  UartRxStart(&BOARD_UART_VCP);

  for (;;) {
    UartRxEvent event;
    if (UartRxGet(&BOARD_UART_VCP, &event) &&
        event <= UART_RX_EVENT_BYTE_MAX) {
      UartPutc(&BOARD_UART_VCP, (char)event);
    }
  }
}
