// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/uart/uart.h
\brief      USART transmit and interrupt-driven receive API, 8N1.

\author     Z. BEN-AKKA
\version    1.3
\date       16/10/2026

\details
  Each USART is described by a Uart structure (instance, clock enable, and
  TX/RX pins), defined by the application. Output functions block until the
  data is accepted by the transmitter; receive functions are non-blocking.

\section uart_h_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the USART is a parameter.           |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Board instances defined by the applications. |
| 1.3     | 16/10/2026 | Z. BEN-AKKA | Declare non-blocking interrupt-driven RX API. |
****************************
*/

#ifndef UART_H
#define UART_H

#include <stdint.h>

/// A USART with transmit and optional receive pins.
typedef struct {
  uint32_t base;          ///< USART base address (USARTx_BASE).
  volatile uint32_t *enr; ///< RCC enable register of the USART (&RCC_APBxENR).
  uint32_t enr_bit;       ///< Enable bit in that register.
  uint32_t tx_port;       ///< TX pin port base address.
  uint32_t tx_pin;        ///< TX pin number.
  uint32_t tx_af;         ///< TX pin alternate function.
  uint32_t rx_port;       ///< RX pin port base; zero disables RX.
  uint32_t rx_pin;        ///< RX pin number; used when rx_port is nonzero.
  uint32_t rx_af;         ///< RX pin alternate function; used when rx_port is nonzero.
} Uart;

/** Fixed capacity of the interrupt-to-main receive event queue. */
#define UART_RX_BUFFER_SIZE 256u

/**
 * Receive events are encoded in 16 bits. Values 0x0000..0x00FF are received
 * data bytes; values above that range identify UART or software queue errors.
 */
typedef uint16_t UartRxEvent;

#define UART_RX_EVENT_BYTE_MAX      0x00FFu
#define UART_RX_EVENT_FRAMING_ERROR 0x0100u
#define UART_RX_EVENT_OVERRUN_ERROR 0x0101u
#define UART_RX_EVENT_NOISE_ERROR   0x0102u
#define UART_RX_EVENT_BUFFER_FULL   0x0103u

/// Counters for received bytes and receive-side error events.
typedef struct {
  uint32_t bytes_received;      ///< Bytes accepted into the RX event queue.
  uint32_t framing_errors;     ///< USART framing errors (FE).
  uint32_t overrun_errors;     ///< USART overrun errors (ORE).
  uint32_t noise_errors;       ///< USART noise errors (NE).
  uint32_t buffer_overflows;   ///< Bytes dropped because the RX queue was full.
} UartRxStats;

/*!
\brief  Enable the USART and its TX pin, 8N1, transmitter only.
\param  uart     USART to configure.
\param  pclk_hz  Clock of the bus the USART is on, in Hz.
\param  baud     Baud rate; the divider is rounded to nearest.
*/
void UartInit(const Uart *uart, uint32_t pclk_hz, uint32_t baud);

/**
\brief  Enable interrupt-driven reception for a configured USART.
\param  uart  USART descriptor with a nonzero RX port.
*/
void UartRxStart(const Uart *uart);

/**
\brief  Try to read the next byte or receive error event without blocking.
\param  uart   USART to read.
\param  event  Receives a byte value (0..255) or one of UART_RX_EVENT_* errors.
\return 1 if an event was written to event; 0 if the queue is empty.
*/
int UartRxGet(const Uart *uart, UartRxEvent *event);

/**
\brief  Discard all currently queued receive events.
\param  uart  USART whose receive queue is flushed.
*/
void UartRxFlush(const Uart *uart);

/**
\brief  Copy the receive-side counters to the caller.
\param  uart   USART whose counters are requested.
\param  stats  Destination for the counter snapshot.
*/
void UartRxGetStats(const Uart *uart, UartRxStats *stats);

/*!
\brief  Send one character.
\param  uart  USART to use.
\param  c     Character to send.
*/
void UartPutc(const Uart *uart, char c);

/*!
\brief  Send a string, expanding '\\n' to CRLF.
\param  uart  USART to use.
\param  s     NUL-terminated string.
*/
void UartPuts(const Uart *uart, const char *s);

/*!
\brief  Print a value as 0x followed by eight hexadecimal digits.
\param  uart  USART to use.
\param  v     Value to print.
*/
void UartPutHex32(const Uart *uart, uint32_t v);

/*!
\brief  Print an unsigned decimal value.
\param  uart  USART to use.
\param  v     Value to print.
*/
void UartPutDec(const Uart *uart, uint32_t v);

/*!
\brief  Wait until the last character has left the shift register.
\details Call before anything that stops or reconfigures the USART clock.
\param  uart  USART to use.
*/
void UartFlush(const Uart *uart);

#endif
