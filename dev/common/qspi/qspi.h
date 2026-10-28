// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/qspi/qspi.h
\brief      QUADSPI driver for a single serial NOR flash.

\author     Z. BEN-AKKA
\version    1.4
\date       28/10/2026

\details
  Chip independent: the flash size, read command and dummy cycles are
  parameters; reset and ID use the JEDEC standard commands (0x66/0x99, 0x9F).
  Status, read, erase and program use the JEDEC standard commands too: read
  status (0x05), write enable (0x06), read (0x03), page program (0x02) and
  4 KB erase (0x20), in indirect mode with instruction, address and data on
  one line (1-1-1).
  The pins must be configured first, by the application (GpioSetAf()).
  The functions with a timeout_ms parameter wait with DelayMs(): SysTick must
  run (SysTickInit()), otherwise they never return.

\section qspi_h_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Generic: flash size and commands are params. |
| 1.2     | 11/10/2026 | Z. BEN-AKKA | Pins configured by the applications.         |
| 1.3     | 27/10/2026 | Z. BEN-AKKA | Status, read, 4 KB erase and page program.   |
| 1.4     | 28/10/2026 | Z. BEN-AKKA | QspiInit: timing and prescaler choice.       |
****************************
*/

#ifndef QSPI_H
#define QSPI_H

#include <stdint.h>

/*!
\brief  Enable the QUADSPI clock and configure it for one flash.
\details NCS stays high at least 6 cycles between commands and data are
         sampled half a cycle late, both needed at 108 MHz. Choose prescaler
         so the QUADSPI clock stays within the flash maximum at the highest
         HCLK of the image: an application started in place may raise HCLK,
         which raises the QUADSPI clock too (N25Q128A: 108 MHz, so 1 at 216 MHz).
\param  size_log2  Flash size as a power of two (24 for 16 MB).
\param  prescaler  QUADSPI clock = HCLK / (prescaler + 1).
*/
void QspiInit(uint32_t size_log2, uint32_t prescaler);

/*!
\brief  Send an instruction-only command (no address, no data).
\param  cmd  Flash instruction.
\return SUCCESS, or TIMEOUT if the QUADSPI does not respond in time.
*/
int QspiCommand(uint8_t cmd);

/*!
\brief  Reset the flash with the JEDEC sequence (reset enable, reset memory).
\details A flash is not reset with the MCU and may be mid-sequence.
\return SUCCESS, or TIMEOUT if the QUADSPI does not respond in time.
*/
int QspiSoftwareReset(void);

/*!
\brief  Read the 3-byte JEDEC ID (command 0x9F).
\param  id  Output: ID with the first byte received in bits 7:0; set on SUCCESS only.
\return SUCCESS, or TIMEOUT if the QUADSPI does not respond in time.
*/
int QspiReadJedecId(uint32_t *id);

/*!
\brief  Read the status register of the flash (command 0x05).
\param  status  Output: status register; bit 0 is WIP (write in progress).
\return SUCCESS, or TIMEOUT if the QUADSPI does not respond in time.
*/
int QspiReadStatus(uint8_t *status);

/*!
\brief  Wait for the end of an erase or a program: WIP back to 0.
\details Reads the status every millisecond; SysTick must run.
\param  timeout_ms  Time limit in milliseconds.
\return SUCCESS, or TIMEOUT if the QUADSPI or the flash does not respond in time.
*/
int QspiWaitReady(uint32_t timeout_ms);

/*!
\brief  Read bytes in indirect mode (command 0x03, 24-bit address, no dummy cycle).
\param  addr  Offset in the flash.
\param  data  Output buffer of len bytes.
\param  len   Number of bytes, at least 1.
\return SUCCESS, FAILURE if len is 0, or TIMEOUT if the QUADSPI does not respond in time.
*/
int QspiRead(uint32_t addr, uint8_t *data, uint32_t len);

/*!
\brief  Erase one 4 KB block (write enable, command 0x20), then wait for its end.
\param  addr        Offset in the flash, a multiple of 4096.
\param  timeout_ms  Time limit of the erase, in milliseconds; SysTick must run.
\return SUCCESS, FAILURE if addr is not aligned, or TIMEOUT if the QUADSPI or
        the flash does not respond in time.
*/
int QspiErase4K(uint32_t addr, uint32_t timeout_ms);

/*!
\brief  Program bytes in one page (write enable, command 0x02), then wait for its end.
\details Programming only clears bits: the bytes must have been erased first.
\param  addr        Offset in the flash.
\param  data        Bytes to program.
\param  len         Number of bytes, 1 to 256, all in the same 256-byte page.
\param  timeout_ms  Time limit of the program, in milliseconds; SysTick must run.
\return SUCCESS, FAILURE if len is 0 or the bytes cross a page, or TIMEOUT if
        the QUADSPI or the flash does not respond in time.
*/
int QspiProgram(uint32_t addr, const uint8_t *data, uint32_t len, uint32_t timeout_ms);

/*!
\brief  Map the flash at QSPI_MEM_BASE, reading in 1-1-4 mode.

\details
  Instruction and 24-bit address on one line, data on four. Read-only: a
  write to the mapped region is a bus fault.

\param  read_cmd      Quad output read instruction of the flash.
\param  dummy_cycles  Dummy cycles required by that instruction.
\return SUCCESS, or TIMEOUT if the QUADSPI does not respond in time.
*/
int QspiMemoryMappedQuadOut(uint8_t read_cmd, uint32_t dummy_cycles);

#endif
