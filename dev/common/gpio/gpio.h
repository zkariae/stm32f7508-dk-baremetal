// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/gpio/gpio.h
\brief      GPIO pin configuration and output control.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  Ports are given by base address (GPIOx_BASE, or GPIO_PORT(PORT_x)). Enable
  the port clock with GpioEnableClock() before any other call.

\section gpio_h_version_history Version history
| Version | Date       | Author      | Description            |
|:-------:|:----------:|:------------|:-----------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.       |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Add GpioEnableClock(). |
****************************
*/

#ifndef GPIO_H
#define GPIO_H

#include <stdint.h>

/*!
\brief  Enable the clock of a GPIO port and wait until it is effective.
\param  port  Port base address.
*/
void GpioEnableClock(uint32_t port);

/*!
\brief  Configure a pin as alternate function, very high speed.
\param  port  Port base address.
\param  pin   Pin number, 0 to 15.
\param  af    Alternate function number, 0 to 15.
*/
void GpioSetAf(uint32_t port, uint32_t pin, uint32_t af);

/*!
\brief  Configure a pin as a push-pull output.
\param  port  Port base address.
\param  pin   Pin number, 0 to 15.
*/
void GpioSetOutput(uint32_t port, uint32_t pin);

/*!
\brief  Drive an output pin high (atomic, through BSRR).
\param  port  Port base address.
\param  pin   Pin number, 0 to 15.
*/
void GpioSet(uint32_t port, uint32_t pin);

/*!
\brief  Drive an output pin low (atomic, through BSRR).
\param  port  Port base address.
\param  pin   Pin number, 0 to 15.
*/
void GpioClear(uint32_t port, uint32_t pin);

/*!
\brief  Invert an output pin.
\param  port  Port base address.
\param  pin   Pin number, 0 to 15.
*/
void GpioToggle(uint32_t port, uint32_t pin);

#endif
