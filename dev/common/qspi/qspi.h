// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/qspi/qspi.h
\brief      QUADSPI driver for a single serial NOR flash.

\author     Z. BEN-AKKA
\version    1.2
\date       11/10/2026

\details
  Chip independent: the flash size, read command and dummy cycles are
  parameters; reset and ID use the JEDEC standard commands (0x66/0x99, 0x9F).
  The pins must be configured first, by the application (GpioSetAf()).

\section qspi_h_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: flash size and commands are params. |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Pins configured by the applications.         |
****************************
*/

#ifndef QSPI_H
#define QSPI_H

#include <stdint.h>

/*!
\brief  Enable the QUADSPI clock and configure it for one flash.
\param  size_log2  Flash size as a power of two (24 for 16 MB).
\param  prescaler  QUADSPI clock = HCLK / (prescaler + 1).
*/
void QspiInit(uint32_t size_log2, uint32_t prescaler);

/*!
\brief  Send an instruction-only command (no address, no data).
\param  cmd  Flash instruction.
\return SUCCESS, or TIMEOUT if the QUADSPI stays busy.
*/
int QspiCommand(uint8_t cmd);

/*!
\brief  Reset the flash with the JEDEC sequence (reset enable, reset memory).
\details A flash is not reset with the MCU and may be mid-sequence.
\return SUCCESS, or TIMEOUT if the QUADSPI stays busy.
*/
int QspiSoftwareReset(void);

/*!
\brief  Read the 3-byte JEDEC ID (command 0x9F).
\param  id  Output: ID with the first byte received in bits 7:0.
\return SUCCESS, or TIMEOUT if the QUADSPI stays busy.
*/
int QspiReadJedecId(uint32_t *id);

/*!
\brief  Map the flash at QSPI_MEM_BASE, reading in 1-1-4 mode.

\details
  Instruction and 24-bit address on one line, data on four. Read-only: a
  write to the mapped region is a bus fault.

\param  read_cmd      Quad output read instruction of the flash.
\param  dummy_cycles  Dummy cycles required by that instruction.
\return SUCCESS, or TIMEOUT if the QUADSPI stays busy.
*/
int QspiMemoryMappedQuadOut(uint8_t read_cmd, uint32_t dummy_cycles);

#endif
