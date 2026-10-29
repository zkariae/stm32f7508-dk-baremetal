// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/qspi/qspi.c
\brief      QUADSPI driver for a single serial NOR flash.

\author     Z. BEN-AKKA
\version    1.7
\date       29/10/2026

\details
  API documented in qspi.h.

\section qspi_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: flash size and commands are params. |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Pins configured by the applications.         |
| 1.3     | 11/10/2026 | Z. BEN-AKKA | Registers from the board's mcu.h.            |
| 1.4     | 27/10/2026 | Z. BEN-AKKA | Bound the TCF, FTF and ABORT waits.          |
| 1.5     | 28/10/2026 | Z. BEN-AKKA | Status, read, 4 KB erase and page program.   |
| 1.6     | 28/10/2026 | Z. BEN-AKKA | NCS high 6 cycles, half-cycle sample shift.  |
| 1.7     | 29/10/2026 | Z. BEN-AKKA | Formatted with clang-format.                 |
****************************
*/

#include "qspi/qspi.h"

#include <stddef.h>
#include <stdint.h>

#include "defines.h"
#include "mcu.h"
#include "delay/delay.h"

// JEDEC standard instructions
#define CMD_RESET_ENABLE 0x66
#define CMD_RESET_MEMORY 0x99
#define CMD_READ_ID      0x9F
#define CMD_READ_STATUS  0x05
#define CMD_WRITE_ENABLE 0x06
#define CMD_READ         0x03
#define CMD_PAGE_PROGRAM 0x02
#define CMD_ERASE_4K     0x20

#define STATUS_WIP    (1U << 0) ///< Status register: write in progress.
#define PAGE_SIZE     256U      ///< Bytes of one program page.
#define ERASE_4K_SIZE 4096U     ///< Bytes of one 4 KB erase block.

#define QSPI_BUSY_TIMEOUT 1000000U ///< Polls of a status flag before giving up.

/// Instruction on one line, then a 24-bit address on one line.
#define CCR_ADDR_1LINE (QSPI_CCR_ADSIZE_24 | QSPI_CCR_ADMODE(1) | QSPI_CCR_IMODE(1))

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

/*!
\brief  Wait for a QSPI_SR flag to be set.
\param  mask  Flag to wait for, such as QSPI_SR_TCF.
\return SUCCESS, or TIMEOUT.
*/
static int qspi_wait_flag(uint32_t mask)
{
  for (uint32_t n = 0; !(QSPI_SR & mask); n++) {
    if (n > QSPI_BUSY_TIMEOUT) {
      return TIMEOUT;
    }
  }
  return SUCCESS;
}

/*!
\brief  Abort the current transfer and wait for the QUADSPI to return to idle.
\return SUCCESS, or TIMEOUT.
*/
static int qspi_abort(void)
{
  QSPI_CR |= QSPI_CR_ABORT;
  for (uint32_t n = 0; QSPI_CR & QSPI_CR_ABORT; n++) {
    if (n > QSPI_BUSY_TIMEOUT) {
      return TIMEOUT;
    }
  }
  return SUCCESS;
}

/*!
\brief  Indirect read: send the command, then read len bytes.
\details The transfer starts on the CCR write, or on the AR write when the
         command has an address phase.
\param  ccr   CCR value: FMODE_READ, the phases and the instruction.
\param  addr  Address, used only when ccr has an address phase.
\param  data  Output buffer of len bytes.
\param  len   Number of bytes, at least 1.
\return SUCCESS, or TIMEOUT.
*/
static int qspi_read_bytes(uint32_t ccr, uint32_t addr, uint8_t *data, uint32_t len)
{
  if (qspi_wait_idle() != SUCCESS) {
    return TIMEOUT;
  }
  QSPI_DLR = len - 1U;
  QSPI_CCR = ccr;
  if (ccr & QSPI_CCR_ADMODE(3)) {
    QSPI_AR = addr;
  }
  for (uint32_t i = 0; i < len; i++) {
    if (qspi_wait_flag(QSPI_SR_FTF) != SUCCESS) {
      qspi_abort();
      return TIMEOUT;
    }
    data[i] = QSPI_DR8;
  }
  if (qspi_wait_flag(QSPI_SR_TCF) != SUCCESS) {
    qspi_abort();
    return TIMEOUT;
  }
  QSPI_FCR = QSPI_FCR_CTCF;

  // ES0290 errata: an indirect read may leave BUSY set; abort returns to idle
  return qspi_abort();
}

/*!
\brief  Indirect write: send the command and its address, then len bytes.
\details The transfer starts on the AR write, or on the first data byte when
         the command has a data phase.
\param  ccr   CCR value: FMODE_WRITE, the phases and the instruction.
\param  addr  Address of the command.
\param  data  Bytes to send; unused when len is 0.
\param  len   Number of bytes, 0 for a command with an address only.
\return SUCCESS, or TIMEOUT.
*/
static int qspi_write_bytes(uint32_t ccr, uint32_t addr, const uint8_t *data, uint32_t len)
{
  if (qspi_wait_idle() != SUCCESS) {
    return TIMEOUT;
  }
  if (len > 0U) {
    QSPI_DLR = len - 1U;
    ccr |= QSPI_CCR_DMODE(1);
  }
  QSPI_CCR = ccr;
  QSPI_AR = addr;
  for (uint32_t i = 0; i < len; i++) {
    if (qspi_wait_flag(QSPI_SR_FTF) != SUCCESS) {
      qspi_abort();
      return TIMEOUT;
    }
    QSPI_DR8 = data[i];
  }
  if (qspi_wait_flag(QSPI_SR_TCF) != SUCCESS) {
    qspi_abort();
    return TIMEOUT;
  }
  QSPI_FCR = QSPI_FCR_CTCF;
  return SUCCESS;
}

void QspiInit(uint32_t size_log2, uint32_t prescaler)
{
  RCC_AHB3ENR |= RCC_AHB3ENR_QSPIEN;
  (void)RCC_AHB3ENR;

  // NCS high 6 cycles: 55 ns at 108 MHz, tSHSL 50 ns
  QSPI_DCR = QSPI_DCR_FSIZE(size_log2 - 1U) | QSPI_DCR_CSHT(5);
  QSPI_CR = QSPI_CR_PRESCALER(prescaler) | QSPI_CR_SSHIFT | QSPI_CR_EN; // Sample half a cycle later
}

int QspiCommand(uint8_t cmd)
{
  if (qspi_wait_idle() != SUCCESS) {
    return TIMEOUT;
  }
  QSPI_CCR = QSPI_CCR_FMODE_WRITE | QSPI_CCR_IMODE(1) | cmd; // starts on the CCR write
  if (qspi_wait_flag(QSPI_SR_TCF) != SUCCESS) {
    qspi_abort();
    return TIMEOUT;
  }
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
  uint8_t bytes[3];

  if (qspi_read_bytes(QSPI_CCR_FMODE_READ | QSPI_CCR_DMODE(1) | QSPI_CCR_IMODE(1) | CMD_READ_ID, 0,
                      bytes, sizeof bytes) != SUCCESS) {
    return TIMEOUT;
  }
  *id = (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16);
  return SUCCESS;
}

int QspiReadStatus(uint8_t *status)
{
  return qspi_read_bytes(
      QSPI_CCR_FMODE_READ | QSPI_CCR_DMODE(1) | QSPI_CCR_IMODE(1) | CMD_READ_STATUS, 0, status, 1);
}

int QspiWaitReady(uint32_t timeout_ms)
{
  for (uint32_t ms = 0;; ms++) {
    uint8_t status;

    if (QspiReadStatus(&status) != SUCCESS) {
      return TIMEOUT;
    }
    if (!(status & STATUS_WIP)) {
      return SUCCESS;
    }
    if (ms >= timeout_ms) {
      return TIMEOUT;
    }
    DelayMs(1);
  }
}

int QspiRead(uint32_t addr, uint8_t *data, uint32_t len)
{
  if (len == 0U) {
    return FAILURE;
  }
  return qspi_read_bytes(QSPI_CCR_FMODE_READ | QSPI_CCR_DMODE(1) | CCR_ADDR_1LINE | CMD_READ, addr,
                         data, len);
}

int QspiErase4K(uint32_t addr, uint32_t timeout_ms)
{
  if (addr % ERASE_4K_SIZE != 0U) {
    return FAILURE;
  }
  if (QspiCommand(CMD_WRITE_ENABLE) != SUCCESS ||
      qspi_write_bytes(QSPI_CCR_FMODE_WRITE | CCR_ADDR_1LINE | CMD_ERASE_4K, addr, NULL, 0) !=
          SUCCESS) {
    return TIMEOUT;
  }
  return QspiWaitReady(timeout_ms);
}

int QspiProgram(uint32_t addr, const uint8_t *data, uint32_t len, uint32_t timeout_ms)
{
  if (len == 0U || (addr % PAGE_SIZE) + len > PAGE_SIZE) {
    return FAILURE;
  }
  if (QspiCommand(CMD_WRITE_ENABLE) != SUCCESS ||
      qspi_write_bytes(QSPI_CCR_FMODE_WRITE | CCR_ADDR_1LINE | CMD_PAGE_PROGRAM, addr, data, len) !=
          SUCCESS) {
    return TIMEOUT;
  }
  return QspiWaitReady(timeout_ms);
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
