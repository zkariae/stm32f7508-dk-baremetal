// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/ltdc/ltdc.c
\brief      LTDC display controller: timings, background colour, layer 1.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  API documented in ltdc.h.

\section ltdc_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "ltdc/ltdc.h"

#include <stdint.h>

#include "defines.h"

void LtdcInit(const LtdcTiming *t, uint32_t background)
{
  RCC_APB2ENR |= RCC_APB2ENR_LTDCEN;
  (void)RCC_APB2ENR;

  // Each timing register holds an accumulated total minus one
  LTDC_SSCR = ((t->hsw - 1U) << 16) | (t->vsw - 1U);
  LTDC_BPCR = ((t->hsw + t->hbp - 1U) << 16) | (t->vsw + t->vbp - 1U);
  LTDC_AWCR = ((t->hsw + t->hbp + t->width - 1U) << 16) | (t->vsw + t->vbp + t->height - 1U);
  LTDC_TWCR = ((t->hsw + t->hbp + t->width + t->hfp - 1U) << 16) |
              (t->vsw + t->vbp + t->height + t->vfp - 1U);

  // Polarities: HSYNC, VSYNC and DE active low, clock not inverted (reset values)

  LTDC_BCCR = background;
  LTDC_SRCR = LTDC_SRCR_IMR; // commit the shadow registers
  LTDC_GCR |= LTDC_GCR_LTDCEN;
}

void LtdcSetBackground(uint32_t colour)
{
  LTDC_BCCR = colour;
  LTDC_SRCR = LTDC_SRCR_IMR;
}

void LtdcLayer1InitRgb565(const LtdcTiming *t, uint32_t fb_addr)
{
  // Window in timing-generator coordinates: AHBP + 1 .. AAW, AVBP + 1 .. AAH
  const uint32_t h_start = t->hsw + t->hbp;
  const uint32_t h_stop = t->hsw + t->hbp + t->width - 1U;
  const uint32_t v_start = t->vsw + t->vbp;
  const uint32_t v_stop = t->vsw + t->vbp + t->height - 1U;

  LTDC_L1WHPCR = (h_stop << 16) | h_start;
  LTDC_L1WVPCR = (v_stop << 16) | v_start;

  LTDC_L1PFCR = LTDC_PF_RGB565;
  LTDC_L1CACR = 0xFFU;          // fully opaque
  LTDC_L1BFCR = (4U << 8) | 5U; // constant alpha, 1 - constant

  LTDC_L1CFBAR = fb_addr;

  // Line length = bytes per line + 3 (RM0385), pitch = bytes per line
  LTDC_L1CFBLR = ((t->width * 2U) << 16) | ((t->width * 2U) + 3U);
  LTDC_L1CFBLNR = t->height;

  LTDC_L1CR = LTDC_L1CR_LEN;
  LTDC_SRCR = LTDC_SRCR_IMR;
}

int LtdcFifoUnderrun(void)
{
  if (LTDC_ISR & LTDC_ISR_FUIF) {
    LTDC_ICR = LTDC_ISR_FUIF;
    return 1;
  }
  return 0;
}
