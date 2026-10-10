// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/led/led.c
\brief      LED on a GPIO pin, either polarity.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  API documented in led.h.

\section led_c_version_history Version history
| Version | Date       | Author      | Description                      |
|:-------:|:----------:|:------------|:---------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                 |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the LED is a parameter. |
****************************
*/

#include "led/led.h"

#include <stdint.h>

#include "gpio/gpio.h"

void LedInit(const Led *led)
{
  GpioEnableClock(led->port);
  GpioSetOutput(led->port, led->pin);
}

void LedOn(const Led *led)
{
  if (led->active_high) {
    GpioSet(led->port, led->pin);
  } else {
    GpioClear(led->port, led->pin);
  }
}

void LedOff(const Led *led)
{
  if (led->active_high) {
    GpioClear(led->port, led->pin);
  } else {
    GpioSet(led->port, led->pin);
  }
}

void LedToggle(const Led *led)
{
  GpioToggle(led->port, led->pin);
}
