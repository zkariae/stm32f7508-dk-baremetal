// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/led/led.h
\brief      LED on a GPIO pin, either polarity.

\author     Z. BEN-AKKA
\version    1.2
\date       11/10/2026

\details
  Each LED is described by a Led structure (port, pin, polarity), defined by
  the application that drives it (LD1 in 01-blink, for instance).

\section led_h_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: the LED is a parameter.             |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Board instances defined by the applications. |
****************************
*/

#ifndef LED_H
#define LED_H

#include <stdint.h>

/// An LED wired to one GPIO pin.
typedef struct {
  uint32_t port;        ///< GPIO port base address.
  uint32_t pin;         ///< Pin number, 0 to 15.
  uint32_t active_high; ///< 1 if driving the pin high lights the LED.
} Led;

/*!
\brief  Enable the port clock and configure the pin as an output.
\param  led  LED to configure.
*/
void LedInit(const Led *led);

/*!
\brief  Switch an LED on.
\param  led  LED to drive.
*/
void LedOn(const Led *led);

/*!
\brief  Switch an LED off.
\param  led  LED to drive.
*/
void LedOff(const Led *led);

/*!
\brief  Invert the state of an LED.
\param  led  LED to drive.
*/
void LedToggle(const Led *led);

#endif
