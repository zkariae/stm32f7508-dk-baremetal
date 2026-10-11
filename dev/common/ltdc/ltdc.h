// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/ltdc/ltdc.h
\brief      LTDC display controller: timings, background colour, layer 1.

\author     Z. BEN-AKKA
\version    1.1
\date       11/10/2026

\details
  Panel independent: the panel is described by an LtdcTiming structure
  defined by the application. The pixel clock and the LTDC pins must be set
  up first (RccInitPixelClock9MHz(), then GpioSetAf() on each signal).

\section ltdc_h_version_history Version history
| Version | Date       | Author      | Description                        |
|:-------:|:----------:|:------------|:-----------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                   |
| 1.1     | 11/10/2026 | Z. BEN-AKKA | Panel defined by the applications. |
****************************
*/

#ifndef LTDC_H
#define LTDC_H

#include <stdint.h>

/// Panel resolution and sync timings, in pixel clocks and lines.
typedef struct {
  uint32_t width;  ///< Active pixels per line.
  uint32_t height; ///< Active lines.
  uint32_t hsw;    ///< Horizontal sync width.
  uint32_t hbp;    ///< Horizontal back porch.
  uint32_t hfp;    ///< Horizontal front porch.
  uint32_t vsw;    ///< Vertical sync width.
  uint32_t vbp;    ///< Vertical back porch.
  uint32_t vfp;    ///< Vertical front porch.
} LtdcTiming;

/*!
\brief  Program the panel timings and enable the LTDC.
\param  timing      Panel timings.
\param  background  Background colour, 0x00RRGGBB, shown where no layer is.
*/
void LtdcInit(const LtdcTiming *timing, uint32_t background);

/*!
\brief  Change the background colour.
\param  colour  0x00RRGGBB.
*/
void LtdcSetBackground(uint32_t colour);

/*!
\brief  Enable layer 1 as a full-screen, opaque RGB565 framebuffer.
\param  timing   Panel timings, as given to LtdcInit().
\param  fb_addr  Framebuffer address; must be reachable by the LTDC (not DTCM).
*/
void LtdcLayer1InitRgb565(const LtdcTiming *timing, uint32_t fb_addr);

/*!
\brief  Report and clear an LTDC FIFO underrun.

\details
  An underrun means the memory did not feed the LTDC fast enough, usually a
  wrong framebuffer address or pitch.

\return Non-zero if an underrun occurred since the last call.
*/
int LtdcFifoUnderrun(void);

#endif
