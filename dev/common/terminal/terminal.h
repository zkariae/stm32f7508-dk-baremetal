// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/terminal/terminal.h
\brief      Character grid of a text terminal.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  The received bytes change a grid of cells given by the caller; nothing is
  drawn or sent. The application reads the cells and draws those that differ
  from what it shows, so that a line feed costs no pixel.

\section terminal_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef TERMINAL_H
#define TERMINAL_H

#include <stdint.h>

/// Look of a cell; its colours belong to the caller.
typedef enum {
  TERMINAL_NORMAL,   ///< Received character.
  TERMINAL_INVERTED, ///< '?' for a byte from 0x80.
  TERMINAL_ERROR,    ///< '!' for a series of reception errors.
} TerminalStyle;

/// One cell of the grid.
typedef struct {
  uint8_t code;  ///< Character, 0x20 to 0x7E.
  uint8_t style; ///< TerminalStyle.
} TerminalCell;

/// A terminal: its grid and its cursor. Set by TerminalInit(), private to the module.
typedef struct {
  TerminalCell *cells; ///< rows * columns cells, given by the caller.
  uint32_t columns;    ///< Cells per line.
  uint32_t rows;       ///< Lines.
  uint32_t top;        ///< Line of the grid shown at the top: the grid is circular.
  uint32_t row;        ///< Cursor line, from the top of the screen.
  uint32_t column;     ///< Cursor column; equal to columns while a wrap waits.
  uint32_t in_error;   ///< The current series of errors is already shown.
} Terminal;

/*!
\brief  Start with an empty screen, cursor at the top left.
\param  term     Terminal.
\param  cells    Grid of rows * columns cells, kept by the terminal.
\param  columns  Cells per line, at least 1.
\param  rows     Lines, at least 1.
*/
void TerminalInit(Terminal *term, TerminalCell *cells, uint32_t columns, uint32_t rows);

/*!
\brief   Apply a received byte, and end the series of errors.
\details The wrap waits for the next character: a full line followed by CR LF
         gives one line break.

| Byte              | Effect                                                             |
|:------------------|:-------------------------------------------------------------------|
| 0x20 to 0x7E      | Character at the cursor, on the next line if a wrap waits          |
| 0x08, 0x7F        | Erases the previous character; stops at column 0                   |
| 0x09 (tab)        | Next multiple of 8, at most the last column; none if a wrap waits  |
| 0x0A (LF)         | Column 0 of the next line; scrolls on the last line                |
| 0x0C (form feed)  | Empty screen, cursor at the top left                               |
| 0x0D (CR)         | Column 0, nothing erased                                           |
| Other, below 0x20 | Ignored                                                            |
| 0x80 to 0xFF      | '?' with TERMINAL_INVERTED, as a character                         |

\param   term  Terminal.
\param   byte  Received byte.
*/
void TerminalPut(Terminal *term, uint8_t byte);

/*!
\brief  Report a reception error: '!' with TERMINAL_ERROR, as a character.
\details Once per series: no effect until TerminalPut() receives a byte.
\param  term  Terminal.
*/
void TerminalError(Terminal *term);

/*!
\brief  Read a cell of the screen.
\param  term    Terminal.
\param  row     Line, 0 at the top.
\param  column  Column, 0 at the left.
\return The cell; an empty one outside the screen.
*/
TerminalCell TerminalGetCell(const Terminal *term, uint32_t row, uint32_t column);

/*!
\brief  Read the position of the cursor; the last column while a wrap waits.
\param  term    Terminal.
\param  row     Output: line, 0 at the top.
\param  column  Output: column, 0 at the left.
*/
void TerminalGetCursor(const Terminal *term, uint32_t *row, uint32_t *column);

#endif
