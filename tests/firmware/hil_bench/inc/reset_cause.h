// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/reset_cause.h
\brief      Capture and decode the board reset cause from RCC_CSR.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md section 4.2. ResetCauseCapture() saves the RCC_CSR
  reset flags and clears them with RMVF; it must run first in main(). The
  saved snapshot then gives the reset and reset_flags banner fields.

\section reset_cause_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef RESET_CAUSE_H
#define RESET_CAUSE_H

#include <stdint.h>

/*!
\brief  Save the RCC_CSR reset flags, then clear them with RMVF.
*/
void ResetCauseCapture(void);

/*!
\brief  Reset cause token of the saved snapshot.
\return LPWR, WWDG, IWDG, SW, POR, BOR or PIN, by priority, or unknown.
*/
const char *ResetCauseToken(void);

/*!
\brief  Saved RCC_CSR reset flags.
\return RCC_CSR masked with RCC_CSR_RSTF_MASK (bits 31:25).
*/
uint32_t ResetCauseFlags(void);

#endif /* RESET_CAUSE_H */
