// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/qspi/qspi.c
\brief      QUADSPI driver for a single serial NOR flash.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  API documented in qspi.h.

\section qspi_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: flash size and commands are params. |
****************************
*/

#include "qspi/qspi.h"

#include <stdint.h>

#include "defines.h"
#include "delay/delay.h"

// JEDEC standard instructions
#define CMD_RESET_ENABLE 0x66
#define CMD_RESET_MEMORY 0x99
#define CMD_READ_ID      0x9F

#define QSPI_BUSY_TIMEOUT 1000000U ///< Polls of BUSY before giving up.

/*!
\brief  Wait for the QUADSPI to be idle.
\return SUCCESS, or TIMEOUT.
*/
static int qspi_wait_idle(void)
{
  for (uint32_t n = 0; QSPI_SR & QSPI_SR_BUSY; n++) {
    if (n > QSPI_BUSY_TIMEOUT) {
      return TIMEOUT;
    }
  }
  return SUCCESS;
}

void QspiInit(uint32_t size_log2, uint32_t prescaler)
{
  RCC_AHB3ENR |= RCC_AHB3ENR_QSPIEN;
  (void)RCC_AHB3ENR;

  QSPI_DCR = QSPI_DCR_FSIZE(size_log2 - 1U) | QSPI_DCR_CSHT(1);
  QSPI_CR = QSPI_CR_PRESCALER(prescaler) | QSPI_CR_EN;
}

int QspiCommand(uint8_t cmd)
{
  if (qspi_wait_idle() != SUCCESS) {
    return TIMEOUT;
  }
  QSPI_CCR = QSPI_CCR_FMODE_WRITE | QSPI_CCR_IMODE(1) | cmd; // starts on the CCR write
  while (!(QSPI_SR & QSPI_SR_TCF)) {}
  QSPI_FCR = QSPI_FCR_CTCF;
  return SUCCESS;
}

int QspiSoftwareReset(void)
{
  if (QspiCommand(CMD_RESET_ENABLE) != SUCCESS || QspiCommand(CMD_RESET_MEMORY) != SUCCESS) {
    return TIMEOUT;
  }
  DelayCycles(1000); // reset recovery
  return SUCCESS;
}

int QspiReadJedecId(uint32_t *id)
{
  if (qspi_wait_idle() != SUCCESS) {
    return TIMEOUT;
  }

  *id = 0;
  QSPI_DLR = 3 - 1; // length - 1
  QSPI_CCR = QSPI_CCR_FMODE_READ | QSPI_CCR_DMODE(1) | QSPI_CCR_IMODE(1) | CMD_READ_ID;
  for (int i = 0; i < 3; i++) {
    while (!(QSPI_SR & QSPI_SR_FTF)) {}
    *id |= (uint32_t)QSPI_DR8 << (8 * i);
  }
  while (!(QSPI_SR & QSPI_SR_TCF)) {}
  QSPI_FCR = QSPI_FCR_CTCF;

  // ES0290 errata: an indirect read may leave BUSY set; abort returns to idle
  QSPI_CR |= QSPI_CR_ABORT;
  while (QSPI_CR & QSPI_CR_ABORT) {}
  return SUCCESS;
}

int QspiMemoryMappedQuadOut(uint8_t read_cmd, uint32_t dummy_cycles)
{
  if (qspi_wait_idle() != SUCCESS) {
    return TIMEOUT;
  }
  QSPI_CCR = QSPI_CCR_FMODE_MMAP | QSPI_CCR_DMODE(4 - 1) | QSPI_CCR_DCYC(dummy_cycles) |
             QSPI_CCR_ADSIZE_24 | QSPI_CCR_ADMODE(1) | QSPI_CCR_IMODE(1) | read_cmd;

  // CCR is Device memory, the mapped region Normal memory: without the barrier
  // the first read can overtake this write and bus-fault
  __asm volatile("dsb" ::: "memory");
  return SUCCESS;
}
