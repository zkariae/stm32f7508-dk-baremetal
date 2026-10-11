// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/uart/uart.c
\brief      Transmit-only USART driver, 8N1.

\author     Z. BEN-AKKA
\version    1.3
\date       11/10/2026

\details
  API documented in uart.h.

\section uart_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the USART is a parameter.           |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Board instances defined by the applications. |
| 1.3     | 11/10/2026 | Z. BEN-AKKA | Registers from the board's mcu.h.            |
****************************
*/

#include "uart/uart.h"

#include <stdint.h>

#include "mcu.h"
#include "gpio/gpio.h"

void UartInit(const Uart *uart, uint32_t pclk_hz, uint32_t baud)
{
  *uart->enr |= uart->enr_bit;
  (void)*uart->enr; // read back: the clock reaches the USART

  GpioEnableClock(uart->tx_port);
  GpioSetAf(uart->tx_port, uart->tx_pin, uart->tx_af);

  USART_BRR(uart->base) = (pclk_hz + baud / 2U) / baud;
  USART_CR1(uart->base) = USART_CR1_TE | USART_CR1_UE; // 8N1 is the reset configuration
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
