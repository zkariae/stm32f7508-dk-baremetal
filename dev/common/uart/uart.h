// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/uart/uart.h
\brief      Transmit-only USART driver, 8N1.

\author     Z. BEN-AKKA
\version    1.2
\date       11/10/2026

\details
  Each USART is described by a Uart structure (instance, clock enable, TX
  pin), defined by the application (VCP_UART for the ST-LINK console).
  Output functions block until the data is accepted by the transmitter.

\section uart_h_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the USART is a parameter.           |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Board instances defined by the applications. |
****************************
*/

#ifndef UART_H
#define UART_H

#include <stdint.h>

/// A USART used for transmission on one pin.
typedef struct {
  uint32_t base;          ///< USART base address (USARTx_BASE).
  volatile uint32_t *enr; ///< RCC enable register of the USART (&RCC_APBxENR).
  uint32_t enr_bit;       ///< Enable bit in that register.
  uint32_t tx_port;       ///< TX pin port base address.
  uint32_t tx_pin;        ///< TX pin number.
  uint32_t tx_af;         ///< TX pin alternate function.
} Uart;

/*!
\brief  Enable the USART and its TX pin, 8N1, transmitter only.
\param  uart     USART to configure.
\param  pclk_hz  Clock of the bus the USART is on, in Hz.
\param  baud     Baud rate; the divider is rounded to nearest.
*/
void UartInit(const Uart *uart, uint32_t pclk_hz, uint32_t baud);

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
