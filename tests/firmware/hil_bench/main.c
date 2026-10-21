// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Initialize USART1 and echo received HIL test bytes.

\author     Z. BEN-AKKA
\version    1.8
\date       21/10/2026

\details
  Starts USART1 at 115200 baud and echoes received bytes for the host-side
  UART RX smoke tests. It echoes received bytes and reports framing errors
  with [FE], noise errors with [NE], overrun errors with [ORE] and RX queue
  overflows with [FULL]. This diagnostic output is temporary and is not the
  HIL protocol. Markers are deferred until the next valid byte, so the host has
  restored its baud rate before they are sent.
  - After echoing the line OVR_TEST, interrupts are masked for 2 ms so that
    the bytes that follow cause a hardware overrun (T5).
  - After echoing the line FULL_TEST, the queue is not read for 100 ms, with
    interrupts enabled, so that the bytes that follow overflow it (T6).
  - The main loop toggles LD1 every 250 ms without blocking, so LD1 blinks at
    2 Hz while the loop runs and stops if an interrupt storm starves it (T7).
  - After echoing the line FLUSH_TEST, the queue is not read for 50 ms, then
    UartRxFlush() empties it. The bench sends [EMPTY n=<count>] with the
    number of bytes flushed, or [NOT_EMPTY] if a byte is still queued (T8).

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 16/10/2026 | Z. BEN-AKKA | Add temporary USART1 byte echo for RX check. |
| 1.2     | 16/10/2026 | Z. BEN-AKKA | Report framing errors as [FE] for T3.        |
| 1.3     | 19/10/2026 | Z. BEN-AKKA | Defer [FE] until next valid byte; fix CRLF doubling. |
| 1.4     | 19/10/2026 | Z. BEN-AKKA | Report noise errors as deferred [NE] for T4. |
| 1.5     | 21/10/2026 | Z. BEN-AKKA | Report deferred [ORE]; mask IRQs 2 ms on OVR_TEST for T5. |
| 1.6     | 21/10/2026 | Z. BEN-AKKA | Report deferred [FULL]; stop reading 100 ms on FULL_TEST for T6. |
| 1.7     | 21/10/2026 | Z. BEN-AKKA | Blink LD1 at 2 Hz from the main loop for T7. |
| 1.8     | 21/10/2026 | Z. BEN-AKKA | Flush the RX queue on FLUSH_TEST and report [EMPTY n=] for T8. |
****************************
*/

#include <stdint.h>

#include "board.h"

#define CPU_HZ        HSI_HZ ///< No clock setup: the core runs from HSI at reset.
#define OVR_MASK_MS   2u
#define FULL_PAUSE_MS 100u
#define LED_TOGGLE_MS 250u ///< Half period: LD1 blinks at 2 Hz.
#define FLUSH_PAUSE_MS 50u

static const char ovr_trigger[] = "OVR_TEST\r\n";
static const char full_trigger[] = "FULL_TEST\r\n";
static const char flush_trigger[] = "FLUSH_TEST\r\n";

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
\brief  Busy-wait for a number of milliseconds on the DWT cycle counter.
\param  ms  Delay in milliseconds.
*/
static void WaitMs(uint32_t ms)
{
  uint32_t start = DWT_CYCCNT;
  uint32_t cycles = (CPU_HZ / 1000u) * ms;

  while ((uint32_t)(DWT_CYCCNT - start) < cycles) {}
}

/*!
\brief  Mask interrupts for OVR_MASK_MS so USART1 RDR is not read.
\details The next received byte stays in RDR and the following one sets ORE.
*/
static void MaskIrqForOverrun(void)
{
  IrqDisable();
  WaitMs(OVR_MASK_MS);
  IrqEnable();
}

/*!
\brief  Advance a trigger-line match by one received character.
\param  trigger  NUL-terminated trigger line.
\param  index    Number of trigger characters matched so far; updated.
\param  c        Received character.
\return 1 when the whole trigger has just been matched, otherwise 0.
*/
static int TriggerMatch(const char *trigger, uint32_t *index, char c)
{
  if (c == trigger[*index]) {
    ++*index;
  } else {
    *index = (c == trigger[0]) ? 1u : 0u;
  }
  if (trigger[*index] == '\0') {
    *index = 0u;
    return 1;
  }
  return 0;
}

/*!
\brief  Let bytes queue for FLUSH_PAUSE_MS, flush the queue and report it.
\details Nothing is read during the pause, so the bytes received meanwhile
         are exactly the bytes flushed.
*/
static void FlushAndReport(void)
{
  UartRxStats before;
  UartRxStats after;
  UartRxEvent event;

  UartRxGetStats(&BOARD_UART_VCP, &before);
  WaitMs(FLUSH_PAUSE_MS); // IRQs stay enabled: the bytes that follow are queued
  UartRxGetStats(&BOARD_UART_VCP, &after);
  UartRxFlush(&BOARD_UART_VCP);

  if (UartRxGet(&BOARD_UART_VCP, &event)) {
    UartPuts(&BOARD_UART_VCP, "[NOT_EMPTY]\n");
    return;
  }
  UartPuts(&BOARD_UART_VCP, "[EMPTY n=");
  UartPutDec(&BOARD_UART_VCP, after.bytes_received - before.bytes_received);
  UartPuts(&BOARD_UART_VCP, "]\n");
}

int main(void)
{
  UartInit(&BOARD_UART_VCP, 16000000U, 115200U);
  UartRxStart(&BOARD_UART_VCP);
  CycleCounterInit();
  LedInit(&BOARD_LED_LD1);

  const uint32_t led_cycles = (CPU_HZ / 1000u) * LED_TOGGLE_MS;
  uint32_t led_last = DWT_CYCCNT;
  uint8_t fe_pending = 0u;
  uint8_t ne_pending = 0u;
  uint8_t ore_pending = 0u;
  uint8_t full_pending = 0u;
  uint32_t ovr_index = 0u;
  uint32_t full_index = 0u;
  uint32_t flush_index = 0u;

  for (;;) {
    /* Heartbeat: never blocks, so the RX queue is still read between toggles. */
    if ((uint32_t)(DWT_CYCCNT - led_last) >= led_cycles) {
      led_last = DWT_CYCCNT;
      LedToggle(&BOARD_LED_LD1);
    }

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
        if (full_pending) {
          UartPuts(&BOARD_UART_VCP, "[FULL]\n");
          full_pending = 0u;
        }
        UartPutc(&BOARD_UART_VCP, (char)event);

        /* Trigger lines restart on a mismatch or any receive error. */
        if (TriggerMatch(ovr_trigger, &ovr_index, (char)event)) {
          MaskIrqForOverrun();
        }
        if (TriggerMatch(full_trigger, &full_index, (char)event)) {
          WaitMs(FULL_PAUSE_MS); // IRQs stay enabled: the queue fills up
        }
        if (TriggerMatch(flush_trigger, &flush_index, (char)event)) {
          FlushAndReport();
        }
      } else {
        ovr_index = 0u;
        full_index = 0u;
        flush_index = 0u;
        if (event == UART_RX_EVENT_FRAMING_ERROR) {
          fe_pending = 1u;
        } else if (event == UART_RX_EVENT_NOISE_ERROR) {
          ne_pending = 1u;
        } else if (event == UART_RX_EVENT_OVERRUN_ERROR) {
          ore_pending = 1u;
        } else if (event == UART_RX_EVENT_BUFFER_FULL) {
          full_pending = 1u;
        }
      }
    }
  }
}
