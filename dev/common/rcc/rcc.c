// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/rcc/rcc.c
\brief      Clock configuration: 216 MHz system clock, LTDC pixel clock.

\author     Z. BEN-AKKA
\version    1.2
\date       11/10/2026

\details
  API documented in rcc.h.

\section rcc_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | HSE frequency as a parameter; frequencies in names. |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Registers from the board's mcu.h.                   |
****************************
*/

#include "rcc/rcc.h"

#include <stdint.h>

#include "mcu.h"

#define PLL_N 432U
#define PLL_P 0U ///< 00 = divide by 2.
#define PLL_Q 9U ///< 432 / 9 = 48 MHz for USB.

#define PLLSAI_N    288U ///< VCO = 288 MHz.
#define PLLSAI_R    4U   ///< PLLSAI_R output = 72 MHz.
#define PLLSAI_DIVR 2U   ///< Code 10 = /8 -> 9 MHz.

void RccInit216MHz(uint32_t hse_hz)
{
  const uint32_t pll_m = hse_hz / 1000000U; // 1 MHz VCO input

  RCC_CR |= RCC_CR_HSEON;
  while (!(RCC_CR & RCC_CR_HSERDY)) {}

  // PWR is on APB1 and must be clocked before it is written
  RCC_APB1ENR |= RCC_APB1ENR_PWREN;
  (void)RCC_APB1ENR;

  // Scale 1 alone caps HCLK at 180 MHz; over-drive below lifts it to 216
  PWR_CR1 |= PWR_CR1_VOS;

  // PLLCFGR is only writable while the PLL is off; bit 22 selects HSE
  RCC_PLLCFGR = (pll_m << 0) | (PLL_N << 6) | (PLL_P << 16) | (1U << 22) | (PLL_Q << 24);

  RCC_CR |= RCC_CR_PLLON;

  // Over-drive: ODSWEN only once ODRDY is set
  PWR_CR1 |= PWR_CR1_ODEN;
  while (!(PWR_CSR1 & PWR_CSR1_ODRDY)) {}

  PWR_CR1 |= PWR_CR1_ODSWEN;
  while (!(PWR_CSR1 & PWR_CSR1_ODSWRDY)) {}

  // Wait states and prescalers before the switch, never after
  FLASH_ACR = FLASH_ACR_LATENCY(7) | FLASH_ACR_PRFTEN | FLASH_ACR_ARTEN;
  while ((FLASH_ACR & FLASH_ACR_LATENCY_MASK) != FLASH_ACR_LATENCY(7)) {}

  RCC_CFGR = (0U << 4)     // HPRE  /1 -> 216 MHz
             | (5U << 10)  // PPRE1 /4 ->  54 MHz
             | (4U << 13); // PPRE2 /2 -> 108 MHz

  while (!(RCC_CR & RCC_CR_PLLRDY)) {}

  RCC_CFGR |= (2U << 0);                  // SW = PLL
  while (((RCC_CFGR >> 2) & 3U) != 2U) {} // SWS confirms
}

void RccInitPixelClock9MHz(void)
{
  // PLLSAICFGR is only writable while the PLLSAI is off
  RCC_CR &= ~RCC_CR_PLLSAION;
  while (RCC_CR & RCC_CR_PLLSAIRDY) {}

  RCC_PLLSAICFGR = (PLLSAI_N << 6) | (PLLSAI_R << 28);

  // PLLSAIDIVR, bits [17:16]: 00 = /2, 01 = /4, 10 = /8, 11 = /16
  RCC_DCKCFGR1 = (RCC_DCKCFGR1 & ~(3U << 16)) | (PLLSAI_DIVR << 16);

  RCC_CR |= RCC_CR_PLLSAION;
  while (!(RCC_CR & RCC_CR_PLLSAIRDY)) {}
}
