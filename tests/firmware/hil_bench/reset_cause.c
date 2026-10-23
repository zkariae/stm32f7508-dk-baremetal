// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/reset_cause.c
\brief      Capture and decode the board reset cause from RCC_CSR.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md section 4.2. The reset flags stay set across resets
  until RMVF clears them, so they are saved and cleared once per boot. The
  token is the first flag set in the protocol priority order: an internal
  reset also sets PINRSTF and a POR also sets BORRSTF, so PIN and BOR come
  after the flags of the actual cause.

\section reset_cause_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "reset_cause.h"

#include "hil_protocol.h"
#include "mcu.h"

typedef struct {
  uint32_t flag;     ///< RCC_CSR reset flag.
  const char *token; ///< reset field value.
} ResetCause;

/// protocol.md section 4.2 priority order.
static const ResetCause causes[] = {
  {RCC_CSR_LPWRRSTF, "LPWR"},
  {RCC_CSR_WWDGRSTF, "WWDG"},
  {RCC_CSR_IWDGRSTF, "IWDG"},
  {RCC_CSR_SFTRSTF, "SW"},
  {RCC_CSR_PORRSTF, "POR"},
  {RCC_CSR_BORRSTF, "BOR"},
  {RCC_CSR_PINRSTF, "PIN"},
};

static uint32_t reset_flags; ///< Snapshot taken by ResetCauseCapture().

void ResetCauseCapture(void)
{
  reset_flags = RCC_CSR & RCC_CSR_RSTF_MASK;
  RCC_CSR |= RCC_CSR_RMVF; // The next boot then reports its own cause only
}

const char *ResetCauseToken(void)
{
  for (uint32_t i = 0u; i < sizeof causes / sizeof causes[0]; ++i) {
    if (reset_flags & causes[i].flag) {
      return causes[i].token;
    }
  }
  return HIL_RESET_UNKNOWN;
}

uint32_t ResetCauseFlags(void)
{
  return reset_flags;
}
