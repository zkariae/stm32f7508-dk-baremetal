// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/delay/delay.c
\brief      Busy-wait and SysTick-based delays.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  API documented in delay.h.

\section delay_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "delay/delay.h"

#include <stdint.h>

#include "defines.h"

static volatile uint32_t g_ticks; ///< Milliseconds since SysTickInit().

/*!
\brief  SysTick interrupt: advance the millisecond counter.
*/
void SysTick_Handler(void)
{
  g_ticks++;
}

// volatile keeps the loop from being optimised away
void DelayCycles(volatile uint32_t n)
{
  while (n--) {
    __asm__("nop");
  }
}

void SysTickInit(uint32_t hclk_hz)
{
  SYST_RVR = (hclk_hz / 1000U) - 1U;
  SYST_CVR = 0;
  SYST_CSR = SYST_CSR_CLKSOURCE | SYST_CSR_TICKINT | SYST_CSR_ENABLE;
}

void DelayMs(uint32_t ms)
{
  uint32_t start = g_ticks;
  while ((g_ticks - start) < ms) {
    __asm__("nop");
  }
}
