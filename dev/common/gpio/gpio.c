// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/gpio/gpio.c
\brief      GPIO pin configuration and output control.

\author     Z. BEN-AKKA
\version    1.2
\date       11/10/2026

\details
  API documented in gpio.h.

\section gpio_c_version_history Version history
| Version | Date       | Author      | Description                       |
|:-------:|:----------:|:------------|:----------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                  |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Add GpioEnableClock().            |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Registers from the board's mcu.h. |
****************************
*/

#include "gpio/gpio.h"

#include <stdint.h>

#include "mcu.h"

void GpioEnableClock(uint32_t port)
{
  // Ports are 0x400 apart from GPIOA, and their enable bits follow the same order
  RCC_AHB1ENR |= 1U << ((port - GPIOA_BASE) / 0x400U);
  (void)RCC_AHB1ENR; // read back: the clock reaches the port
}

void GpioSetAf(uint32_t port, uint32_t pin, uint32_t af)
{
  uint32_t shift = (pin % 8) * 4; // AFRL for pins 0-7, AFRH for 8-15

  GPIO_AFR(port, pin) = (GPIO_AFR(port, pin) & ~(0xFU << shift)) | (af << shift);
  GPIO_OSPEEDR(port) |= 3U << (pin * 2);
  GPIO_MODER(port) = (GPIO_MODER(port) & ~(3U << (pin * 2))) | (GPIO_MODE_AF << (pin * 2));
}

void GpioSetOutput(uint32_t port, uint32_t pin)
{
  GPIO_MODER(port) = (GPIO_MODER(port) & ~(3U << (pin * 2))) | (GPIO_MODE_OUTPUT << (pin * 2));
}

void GpioSet(uint32_t port, uint32_t pin)
{
  GPIO_BSRR(port) = 1U << pin;
}

void GpioClear(uint32_t port, uint32_t pin)
{
  GPIO_BSRR(port) = 1U << (pin + 16);
}

void GpioToggle(uint32_t port, uint32_t pin)
{
  GPIO_ODR(port) ^= 1U << pin;
}
