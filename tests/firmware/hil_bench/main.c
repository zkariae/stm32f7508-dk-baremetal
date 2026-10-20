// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Initialize USART1 and echo received HIL test bytes.

\author     Z. BEN-AKKA
\version    1.5
\date       21/10/2026

\details
  Starts USART1 at 115200 baud and echoes received bytes for the host-side
  UART RX smoke tests. It echoes received bytes and reports framing errors
  with [FE], noise errors with [NE] and overrun errors with [ORE]. This
  diagnostic output is temporary and is not the HIL protocol. Markers are
  deferred until the next valid byte, so the host has restored its baud rate
  before they are sent. After echoing the line OVR_TEST, interrupts are masked
  for 2 ms so that the bytes that follow cause a hardware overrun (T5).

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 16/10/2026 | Z. BEN-AKKA | Add temporary USART1 byte echo for RX check. |
| 1.2     | 16/10/2026 | Z. BEN-AKKA | Report framing errors as [FE] for T3.        |
| 1.3     | 19/10/2026 | Z. BEN-AKKA | Defer [FE] until next valid byte; fix CRLF doubling. |
| 1.4     | 19/10/2026 | Z. BEN-AKKA | Report noise errors as deferred [NE] for T4. |
| 1.5     | 21/10/2026 | Z. BEN-AKKA | Report deferred [ORE]; mask IRQs 2 ms on OVR_TEST for T5. |
****************************
*/

#include <stdint.h>

#include "board.h"

#define CPU_HZ      HSI_HZ ///< No clock setup: the core runs from HSI at reset.
#define OVR_MASK_MS 2u

static const char ovr_trigger[] = "OVR_TEST\r\n";

/*!
\brief  Start the DWT cycle counter used to time the interrupt mask.
*/
static void CycleCounterInit(void)
{
  DEMCR |= DEMCR_TRCENA;
  DWT_LAR = DWT_LAR_UNLOCK;
  DWT_CYCCNT = 0u;
  DWT_CTRL |= DWT_CTRL_CYCCNTENA;
}

/*!
\brief  Mask interrupts for OVR_MASK_MS so USART1 RDR is not read.
\details The next received byte stays in RDR and the following one sets ORE.
*/
static void MaskIrqForOverrun(void)
{
  uint32_t start = DWT_CYCCNT;
  uint32_t cycles = (CPU_HZ / 1000u) * OVR_MASK_MS;

  IrqDisable();
  while ((uint32_t)(DWT_CYCCNT - start) < cycles) {}
  IrqEnable();
}

int main(void)
{
  UartInit(&BOARD_UART_VCP, 16000000U, 115200U);
  UartRxStart(&BOARD_UART_VCP);
  CycleCounterInit();

  uint8_t fe_pending = 0u;
  uint8_t ne_pending = 0u;
  uint8_t ore_pending = 0u;
  uint32_t trigger_index = 0u;

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
        if (ore_pending) {
          UartPuts(&BOARD_UART_VCP, "[ORE]\n");
          ore_pending = 0u;
        }
        UartPutc(&BOARD_UART_VCP, (char)event);

        /* Track OVR_TEST\r\n; restart on a mismatch or any receive error. */
        if ((char)event == ovr_trigger[trigger_index]) {
          ++trigger_index;
        } else {
          trigger_index = ((char)event == ovr_trigger[0]) ? 1u : 0u;
        }
        if (ovr_trigger[trigger_index] == '\0') {
          trigger_index = 0u;
          MaskIrqForOverrun();
        }
      } else {
        trigger_index = 0u;
        if (event == UART_RX_EVENT_FRAMING_ERROR) {
          fe_pending = 1u;
        } else if (event == UART_RX_EVENT_NOISE_ERROR) {
          ne_pending = 1u;
        } else if (event == UART_RX_EVENT_OVERRUN_ERROR) {
          ore_pending = 1u;
        }
      }
    }
  }
}
