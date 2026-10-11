// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/defines.h
\brief      Project-wide definitions, independent of the board.

\author     Z. BEN-AKKA
\version    1.1
\date       11/10/2026

\details
  Return codes shared by every module (Contributing.md, part B.11). Registers
  come from the board: mcu.h, and board wiring from board.h.

\section defines_h_version_history Version history
| Version | Date       | Author      | Description                            |
|:-------:|:----------:|:------------|:---------------------------------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                       |
| 1.1     | 11/10/2026 | Z. BEN-AKKA | Registers and wiring moved to boards/. |
****************************
*/

#ifndef DEFINES_H
#define DEFINES_H

/* Return codes (Contributing.md, part B.11) */
#define SUCCESS 0x00 ///< Operation completed.
#define FAILURE 0x01 ///< Generic failure.
#define TIMEOUT 0x02 ///< Hardware did not respond in time.

#endif
