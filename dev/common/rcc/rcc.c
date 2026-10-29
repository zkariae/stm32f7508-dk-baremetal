// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/rcc/rcc.c
\brief      Clock configuration: 216 MHz system clock, LTDC pixel clock.

\author     Z. BEN-AKKA
\version    1.3
\date       29/10/2026

\details
  API documented in rcc.h.

\section rcc_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | HSE frequency as a parameter; frequencies in names. |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Registers from the board's mcu.h.                   |
| 1.3     | 29/10/2026 | Z. BEN-AKKA | Bounded waits; PLLSAI kept if already at 9 MHz.     |
****************************
*/

#include "rcc/rcc.h"

#include <stdint.h>

#include "defines.h"
#include "mcu.h"

#define PLL_N 432U
#define PLL_P 0U ///< 00 = divide by 2.
#define PLL_Q 9U ///< 432 / 9 = 48 MHz for USB.

#define PLLSAI_N    288U ///< VCO = 288 MHz.
#define PLLSAI_R    4U   ///< PLLSAI_R output = 72 MHz.
#define PLLSAI_DIVR 2U   ///< Code 10 = /8 -> 9 MHz.

#define PLLSAICFGR_N_MASK  (0x1FFU << 6) ///< PLLSAIN, bits [14:6].
#define PLLSAICFGR_R_MASK  (7U << 28)    ///< PLLSAIR, bits [30:28].
#define DCKCFGR1_DIVR_MASK (3U << 16)    ///< PLLSAIDIVR, bits [17:16].

#define RCC_TIMEOUT_LOOPS 1000000U ///< >= 60 ms at 16 MHz, >= 4 ms at 216 MHz (HSE: 2 ms).

/*!
\brief  Wait until (*reg & mask) == value.
\return SUCCESS, or TIMEOUT after RCC_TIMEOUT_LOOPS polls.
*/
static int wait_bits(volatile uint32_t *reg, uint32_t mask, uint32_t value)
{
  for (uint32_t i = 0; i < RCC_TIMEOUT_LOOPS; i++) {
    if ((*reg & mask) == value) {
      return SUCCESS;
    }
  }
  return TIMEOUT;
}

int RccInit216MHz(uint32_t hse_hz)
{
  const uint32_t pll_m = hse_hz / 1000000U; // 1 MHz VCO input

  RCC_CR |= RCC_CR_HSEON;
  if (wait_bits(&RCC_CR, RCC_CR_HSERDY, RCC_CR_HSERDY) != SUCCESS)
    return TIMEOUT;

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
  if (wait_bits(&PWR_CSR1, PWR_CSR1_ODRDY, PWR_CSR1_ODRDY) != SUCCESS)
    return TIMEOUT;

  PWR_CR1 |= PWR_CR1_ODSWEN;
  if (wait_bits(&PWR_CSR1, PWR_CSR1_ODSWRDY, PWR_CSR1_ODSWRDY) != SUCCESS)
    return TIMEOUT;

  // Wait states and prescalers before the switch, never after
  FLASH_ACR = FLASH_ACR_LATENCY(7) | FLASH_ACR_PRFTEN | FLASH_ACR_ARTEN;
  if (wait_bits(&FLASH_ACR, FLASH_ACR_LATENCY_MASK, FLASH_ACR_LATENCY(7)) != SUCCESS)
    return TIMEOUT;

  RCC_CFGR = (0U << 4)     // HPRE  /1 -> 216 MHz
             | (5U << 10)  // PPRE1 /4 ->  54 MHz
             | (4U << 13); // PPRE2 /2 -> 108 MHz

  if (wait_bits(&RCC_CR, RCC_CR_PLLRDY, RCC_CR_PLLRDY) != SUCCESS)
    return TIMEOUT;

  RCC_CFGR |= (2U << 0);                         // SW = PLL
  return wait_bits(&RCC_CFGR, 3U << 2, 2U << 2); // SWS confirms
}

int RccInitPixelClock9MHz(void)
{
  const uint32_t cfg = (PLLSAI_N << 6) | (PLLSAI_R << 28);

  // Already running at 9 MHz: stopping it would stall a running LTDC
  if ((RCC_CR & RCC_CR_PLLSAIRDY) &&
      (RCC_PLLSAICFGR & (PLLSAICFGR_N_MASK | PLLSAICFGR_R_MASK)) == cfg &&
      (RCC_DCKCFGR1 & DCKCFGR1_DIVR_MASK) == (PLLSAI_DIVR << 16))
    return SUCCESS;

  // PLLSAICFGR is only writable while the PLLSAI is off
  RCC_CR &= ~RCC_CR_PLLSAION;
  if (wait_bits(&RCC_CR, RCC_CR_PLLSAIRDY, 0U) != SUCCESS)
    return TIMEOUT;

  // N and R only: P and Q keep their reset values (Q = 0 is invalid)
  RCC_PLLSAICFGR = (RCC_PLLSAICFGR & ~(PLLSAICFGR_N_MASK | PLLSAICFGR_R_MASK)) | cfg;

  // PLLSAIDIVR, bits [17:16]: 00 = /2, 01 = /4, 10 = /8, 11 = /16
  RCC_DCKCFGR1 = (RCC_DCKCFGR1 & ~DCKCFGR1_DIVR_MASK) | (PLLSAI_DIVR << 16);

  RCC_CR |= RCC_CR_PLLSAION;
  return wait_bits(&RCC_CR, RCC_CR_PLLSAIRDY, RCC_CR_PLLSAIRDY);
}
