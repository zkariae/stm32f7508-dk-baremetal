// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/uart/uart.c
\brief      USART transmit and interrupt-driven receive driver, 8N1.

\author     Z. BEN-AKKA
\version    1.4
\date       16/10/2026

\details
  API documented in uart.h.

\section uart_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the USART is a parameter.           |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Board instances defined by the applications. |
| 1.3     | 11/10/2026 | Z. BEN-AKKA | Registers from the board's mcu.h.            |
| 1.4     | 16/10/2026 | Z. BEN-AKKA | Add non-blocking interrupt-driven RX queue.  |
****************************
*/

#include "uart/uart.h"

#include <stdint.h>

#include "mcu.h"
#include "gpio/gpio.h"

#define UART_RX_BUFFER_MASK (UART_RX_BUFFER_SIZE - 1u)
#define UART_RX_IRQ_PRIORITY 5u

_Static_assert((UART_RX_BUFFER_SIZE & UART_RX_BUFFER_MASK) == 0u,
               "UART RX buffer size must be a power of two");

/* Single-producer (USART1 IRQ), single-consumer (main loop) event queue. */
static volatile UartRxEvent rx_events[UART_RX_BUFFER_SIZE];
static volatile uint16_t rx_head;
static volatile uint16_t rx_tail;
static volatile uint8_t rx_overflow_pending;
static volatile uint8_t rx_started;
static volatile UartRxStats rx_stats;

static uint16_t UartRxQueued(void)
{
  return (uint16_t)(rx_head - rx_tail);
}

/* The overflow marker is returned after older queued events are consumed. */
static void UartRxQueueEvent(UartRxEvent event)
{
  if (rx_overflow_pending || UartRxQueued() >= UART_RX_BUFFER_SIZE) {
    rx_overflow_pending = 1u;
    if (event <= UART_RX_EVENT_BYTE_MAX) {
      ++rx_stats.buffer_overflows;
    }
    return;
  }

  rx_events[rx_head & UART_RX_BUFFER_MASK] = event;
  ++rx_head;
  if (event <= UART_RX_EVENT_BYTE_MAX) {
    ++rx_stats.bytes_received;
  }
}

void UartInit(const Uart *uart, uint32_t pclk_hz, uint32_t baud)
{
  *uart->enr |= uart->enr_bit;
  (void)*uart->enr; // read back: the clock reaches the USART

  GpioEnableClock(uart->tx_port);
  GpioSetAf(uart->tx_port, uart->tx_pin, uart->tx_af);

  USART_BRR(uart->base) = (pclk_hz + baud / 2U) / baud;
  USART_CR1(uart->base) = USART_CR1_TE | USART_CR1_UE; // 8N1 is the reset configuration
}

void UartRxStart(const Uart *uart)
{
  if (uart == 0 || uart->base != USART1_BASE || uart->rx_port == 0u) {
    return;
  }

  /* Stop receive sources while the queue and peripheral state are reset. */
  rx_started = 0u;
  USART_CR1(USART1_BASE) &= ~(USART_CR1_RXNEIE | USART_CR1_RE);
  USART_CR3(USART1_BASE) &= ~USART_CR3_EIE;

  rx_head = 0u;
  rx_tail = 0u;
  rx_overflow_pending = 0u;
  rx_stats.bytes_received = 0u;
  rx_stats.framing_errors = 0u;
  rx_stats.overrun_errors = 0u;
  rx_stats.noise_errors = 0u;
  rx_stats.buffer_overflows = 0u;

  GpioEnableClock(uart->rx_port);
  GpioSetAf(uart->rx_port, uart->rx_pin, uart->rx_af);

  /* Clear stale STM32F7 error flags through ICR and discard stale data. */
  USART_ICR(USART1_BASE) = USART_ICR_FECF | USART_ICR_NCF | USART_ICR_ORECF;
  if (USART_ISR(USART1_BASE) & USART_ISR_RXNE) {
    (void)USART_RDR(USART1_BASE);
  }

  NVIC_IPR(USART1_IRQn) = (uint8_t)(UART_RX_IRQ_PRIORITY << 4);
  rx_started = 1u;
  NVIC_ISER(USART1_IRQn) = 1UL << (USART1_IRQn % 32U);

  USART_CR3(USART1_BASE) |= USART_CR3_EIE;
  USART_CR1(USART1_BASE) |= USART_CR1_RE | USART_CR1_RXNEIE;
}

int UartRxGet(const Uart *uart, UartRxEvent *event)
{
  if (uart == 0 || event == 0 || uart->base != USART1_BASE || !rx_started) {
    return 0;
  }

  uint16_t tail = rx_tail;
  if (tail != rx_head) {
    *event = rx_events[tail & UART_RX_BUFFER_MASK];
    rx_tail = (uint16_t)(tail + 1u);
    return 1;
  }

  if (rx_overflow_pending) {
    rx_overflow_pending = 0u;
    *event = UART_RX_EVENT_BUFFER_FULL;
    return 1;
  }

  return 0;
}

void UartRxFlush(const Uart *uart)
{
  if (uart == 0 || uart->base != USART1_BASE || !rx_started) {
    return;
  }

  rx_tail = rx_head;
  rx_overflow_pending = 0u;
}

void UartRxGetStats(const Uart *uart, UartRxStats *stats)
{
  if (uart == 0 || stats == 0 || uart->base != USART1_BASE || !rx_started) {
    return;
  }

  stats->bytes_received = rx_stats.bytes_received;
  stats->framing_errors = rx_stats.framing_errors;
  stats->overrun_errors = rx_stats.overrun_errors;
  stats->noise_errors = rx_stats.noise_errors;
  stats->buffer_overflows = rx_stats.buffer_overflows;
}

void USART1_IRQHandler(void)
{
  uint32_t status = USART_ISR(USART1_BASE);
  uint32_t errors = status & (USART_ISR_FE | USART_ISR_NE | USART_ISR_ORE);
  uint8_t has_byte = (status & USART_ISR_RXNE) != 0u;
  uint8_t byte = 0u;

  if (has_byte) {
    byte = (uint8_t)USART_RDR(USART1_BASE);
  }

  uint32_t clear = 0u;
  if (status & USART_ISR_FE) {
    clear |= USART_ICR_FECF;
  }
  if (status & USART_ISR_NE) {
    clear |= USART_ICR_NCF;
  }
  if (status & USART_ISR_ORE) {
    clear |= USART_ICR_ORECF;
  }
  if (clear != 0u) {
    USART_ICR(USART1_BASE) = clear;
  }

  if (!rx_started) {
    return;
  }

  /* FE/NE describe the current RDR byte; ORE reports a later lost byte. */
  if (status & USART_ISR_FE) {
    ++rx_stats.framing_errors;
    UartRxQueueEvent(UART_RX_EVENT_FRAMING_ERROR);
  }
  if (status & USART_ISR_NE) {
    ++rx_stats.noise_errors;
    UartRxQueueEvent(UART_RX_EVENT_NOISE_ERROR);
  }
  if (has_byte && !(errors & (USART_ISR_FE | USART_ISR_NE))) {
    UartRxQueueEvent(byte);
  }
  if (status & USART_ISR_ORE) {
    ++rx_stats.overrun_errors;
    UartRxQueueEvent(UART_RX_EVENT_OVERRUN_ERROR);
  }
}

void UartPutc(const Uart *uart, char c)
{
  while (!(USART_ISR(uart->base) & USART_ISR_TXE)) {}
  USART_TDR(uart->base) = (uint8_t)c;
}

void UartPuts(const Uart *uart, const char *s)
{
  while (*s) {
    if (*s == '\n') {
      UartPutc(uart, '\r');
    }
    UartPutc(uart, *s++);
  }
}

void UartPutHex32(const Uart *uart, uint32_t v)
{
  static const char digits[] = "0123456789ABCDEF";

  UartPuts(uart, "0x");
  for (int shift = 28; shift >= 0; shift -= 4) {
    UartPutc(uart, digits[(v >> shift) & 0xFU]);
  }
}

void UartPutDec(const Uart *uart, uint32_t v)
{
  char buf[10]; // 4294967295 has 10 digits
  int i = 0;

  if (v == 0) {
    UartPutc(uart, '0');
    return;
  }
  while (v > 0) {
    buf[i++] = (char)('0' + (v % 10U));
    v /= 10U;
  }
  while (i > 0) {
    UartPutc(uart, buf[--i]);
  }
}

void UartFlush(const Uart *uart)
{
  while (!(USART_ISR(uart->base) & USART_ISR_TC)) {}
}
