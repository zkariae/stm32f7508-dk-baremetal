// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/terminal/terminal.c
\brief      Character grid of a text terminal.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  API documented in terminal.h. The work per byte is bounded by the size of
  the grid; nothing waits.

\section terminal_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "terminal/terminal.h"

#include <stdint.h>

#define CODE_FIRST 0x20U ///< First character: space.
#define CODE_LAST  0x7EU ///< Last character.
#define CODE_DEL   0x7FU ///< Backspace of some terminals.
#define TAB_WIDTH  8U    ///< Columns between two tab stops.

/// Content of an empty cell.
static const TerminalCell empty_cell = {CODE_FIRST, TERMINAL_NORMAL};

/*!
\brief  Find a cell of the screen in the circular grid.
*/
static TerminalCell *cell_at(const Terminal *term, uint32_t row, uint32_t column)
{
  return &term->cells[(term->top + row) % term->rows * term->columns + column];
}

/*!
\brief  Empty a line of the screen.
*/
static void clear_row(const Terminal *term, uint32_t row)
{
  TerminalCell *cells = cell_at(term, row, 0U);

  for (uint32_t i = 0; i < term->columns; i++) {
    cells[i] = empty_cell;
  }
}

/*!
\brief  Empty the screen, cursor at the top left.
*/
static void clear_screen(Terminal *term)
{
  term->top = 0U;
  term->row = 0U;
  term->column = 0U;
  for (uint32_t row = 0; row < term->rows; row++) {
    clear_row(term, row);
  }
}

/*!
\brief  Go to the start of the next line; scroll on the last one.
*/
static void line_feed(Terminal *term)
{
  term->column = 0U;
  if (term->row + 1U < term->rows) {
    term->row++;
  } else {
    // The top line becomes the last one, empty
    term->top = (term->top + 1U) % term->rows;
    clear_row(term, term->row);
  }
}

/*!
\brief  Put a character at the cursor, after the waiting wrap if any.
*/
static void put_char(Terminal *term, uint8_t code, TerminalStyle style)
{
  if (term->column == term->columns) {
    line_feed(term);
  }

  TerminalCell *cell = cell_at(term, term->row, term->column);

  cell->code = code;
  cell->style = (uint8_t)style;
  term->column++;
}

/*!
\brief  Erase the previous character of the line.
*/
static void backspace(Terminal *term)
{
  if (term->column > 0U) {
    term->column--;
    *cell_at(term, term->row, term->column) = empty_cell;
  }
}

/*!
\brief  Go to the next tab stop, at most the last column.
*/
static void tab(Terminal *term)
{
  // While a wrap waits, moving back would let the next character erase the last one
  if (term->column < term->columns) {
    const uint32_t next = (term->column / TAB_WIDTH + 1U) * TAB_WIDTH;

    term->column = (next < term->columns) ? next : term->columns - 1U;
  }
}

void TerminalInit(Terminal *term, TerminalCell *cells, uint32_t columns, uint32_t rows)
{
  term->cells = cells;
  term->columns = columns;
  term->rows = rows;
  term->in_error = 0U;
  clear_screen(term);
}

void TerminalPut(Terminal *term, uint8_t byte)
{
  term->in_error = 0U;

  switch (byte) {
  case '\b':
  case CODE_DEL:
    backspace(term);
    break;
  case '\t':
    tab(term);
    break;
  case '\n':
    line_feed(term);
    break;
  case '\f':
    clear_screen(term);
    break;
  case '\r':
    term->column = 0U;
    break;
  default:
    if (byte > CODE_LAST) { // 0x7F is handled above
      put_char(term, '?', TERMINAL_INVERTED);
    } else if (byte >= CODE_FIRST) {
      put_char(term, byte, TERMINAL_NORMAL);
    }
    break;
  }
}

void TerminalError(Terminal *term)
{
  if (!term->in_error) {
    term->in_error = 1U;
    put_char(term, '!', TERMINAL_ERROR);
  }
}

TerminalCell TerminalGetCell(const Terminal *term, uint32_t row, uint32_t column)
{
  if (row >= term->rows || column >= term->columns) {
    return empty_cell;
  }
  return *cell_at(term, row, column);
}

void TerminalGetCursor(const Terminal *term, uint32_t *row, uint32_t *column)
{
  *row = term->row;
  *column = (term->column < term->columns) ? term->column : term->columns - 1U;
}
