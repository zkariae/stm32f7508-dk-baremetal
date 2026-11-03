// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/delay/delay.h
\brief      Busy-wait and SysTick-based delays.

\author     Z. BEN-AKKA
\version    1.1
\date       29/10/2026

\details
  DelayCycles() works at any clock without setup. DelayMs() and SysTickMs()
  need SysTickInit(), which starts a 1 ms interrupt (SysTick_Handler is
  defined here and replaces the weak default of startup.c).

\section delay_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 29/10/2026 | Z. BEN-AKKA | Add SysTickMs(). |
****************************
*/

#ifndef DELAY_H
#define DELAY_H

#include <stdint.h>

/*!
\brief  Busy-wait for a number of loop iterations.

\details
  Duration depends on the clock, the optimisation level and the compiler.

\param  n  Number of iterations.
*/
void DelayCycles(uint32_t n);

/*!
\brief  Start SysTick with a 1 ms period and its interrupt.
\param  hclk_hz  Processor clock frequency, in Hz.
*/
void SysTickInit(uint32_t hclk_hz);

/*!
\brief  Wait for a number of milliseconds.
\param  ms  Delay in milliseconds; requires SysTickInit().
*/
void DelayMs(uint32_t ms);

/*!
\brief  Milliseconds since SysTickInit(); wraps after 2^32 ms.
\details Compare two values by subtraction, as DelayMs() does, to survive the wrap.
\return Millisecond counter; requires SysTickInit().
*/
uint32_t SysTickMs(void);

#endif
