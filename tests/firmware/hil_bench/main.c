// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Initialize USART1 and echo received HIL test bytes.

\author     Z. BEN-AKKA
\version    1.2
\date       16/10/2026

\details
  Starts USART1 at 115200 baud and echoes received bytes for the host-side
  UART RX smoke tests. It echoes received bytes and reports framing errors
  with [FE]. This diagnostic output is temporary and is not the HIL protocol.

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 16/10/2026 | Z. BEN-AKKA | Add temporary USART1 byte echo for RX check. |
| 1.2     | 16/10/2026 | Z. BEN-AKKA | Report framing errors as [FE] for T3.        |
****************************
*/

#include "board.h"

int main(void)
{
  UartInit(&BOARD_UART_VCP, 16000000U, 115200U);
  UartRxStart(&BOARD_UART_VCP);

  for (;;) {
    UartRxEvent event;
    if (UartRxGet(&BOARD_UART_VCP, &event)) {
      if (event <= UART_RX_EVENT_BYTE_MAX) {
        UartPutc(&BOARD_UART_VCP, (char)event);
      } else if (event == UART_RX_EVENT_FRAMING_ERROR) {
        UartPuts(&BOARD_UART_VCP, "[FE]\r\n");
      }
    }
  }
}
