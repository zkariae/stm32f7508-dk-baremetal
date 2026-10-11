// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/rcc/rcc.h
\brief      Clock configuration: 216 MHz system clock, LTDC pixel clock.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  System: HSE / M (1 MHz VCO input) * N=432 / P=2 = 216 MHz; AHB /1, APB1 /4,
  APB2 /2. Pixel: same 1 MHz input * 288 / R=4 / 8 = 9 MHz for the LTDC.

\section rcc_h_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | HSE frequency as a parameter; frequencies in names. |
****************************
*/

#ifndef RCC_H
#define RCC_H

#include <stdint.h>

#define SYSCLK_HZ      216000000UL ///< SYSCLK and HCLK after RccInit216MHz().
#define APB1_HZ        54000000UL  ///< APB1 clock after RccInit216MHz().
#define APB2_HZ        108000000UL ///< APB2 clock after RccInit216MHz().
#define PIXEL_CLOCK_HZ 9000000UL   ///< LTDC clock after RccInitPixelClock9MHz().

/*!
\brief  Switch SYSCLK from HSI to the main PLL at 216 MHz.

\details
  Starts the HSE, enables voltage scale 1 and over-drive, sets 7 flash wait
  states and the bus prescalers, then switches to the PLL.

\param  hse_hz  HSE frequency, a multiple of 1 MHz (crystal: 4 to 26 MHz).
*/
void RccInit216MHz(uint32_t hse_hz);

/*!
\brief  Start the PLLSAI and divide it to the 9 MHz LTDC pixel clock.
\details Requires RccInit216MHz() (shares the PLLM input divider).
*/
void RccInitPixelClock9MHz(void);

#endif
