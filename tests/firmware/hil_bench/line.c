// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/line.c
\brief      Assemble protocol lines from UART receive events.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md sections 2.2 and 2.4. LF ends a line and one CR
  right before it is removed; any other CR is an invalid byte. Bytes past
  HIL_LINE_MAX_LEN are dropped but the line is still read up to its
  terminator. At the terminator, the length check comes first
  (section 5.2.2): a line too long gives LINE_TOO_LONG, otherwise an invalid
  byte or a receive error (FE, NE, ORE, queue full) gives LINE_BAD_FRAME.

\section line_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "line.h"

/*!
\brief  Store one byte of the line; past the maximum, only note the overflow.
*/
static void LineAdd(LineAssembler *line, char c)
{
  if (line->len < HIL_LINE_MAX_LEN) {
    line->text[line->len] = c;
  }
  if (line->len <= HIL_LINE_MAX_LEN) {
    ++line->len; // Stops at HIL_LINE_MAX_LEN + 1: too long
  }
}

/*!
\brief  Report the line that the terminator ends, then start a new one.
*/
static LineStatus LineEnd(LineAssembler *line)
{
  LineStatus status = LINE_NONE;

  if (line->len > HIL_LINE_MAX_LEN) {
    status = LINE_TOO_LONG;
  } else if (line->bad) {
    status = LINE_BAD_FRAME;
  } else {
    line->text[line->len] = '\0';
    for (uint32_t i = 0u; i < line->len; ++i) {
      if (line->text[i] != ' ') {
        status = LINE_READY; // Blank lines stay LINE_NONE
        break;
      }
    }
  }
  line->len = 0u;
  line->cr = 0u;
  line->bad = 0u;
  return status;
}

LineStatus LinePush(LineAssembler *line, UartRxEvent event)
{
  if (event > UART_RX_EVENT_BYTE_MAX) {
    line->bad = 1u; // FE, NE, ORE or queue full: the bytes of the line are not reliable
    return LINE_NONE;
  }
  if (line->cr) {
    line->cr = 0u;
    if (event == '\n') {
      return LineEnd(line);
    }
    LineAdd(line, '\r'); // A CR not followed by LF is an invalid byte
    line->bad = 1u;
  }
  if (event == '\r') {
    line->cr = 1u;
    return LINE_NONE;
  }
  if (event == '\n') {
    return LineEnd(line);
  }
  if (event < HIL_CHAR_MIN || event > HIL_CHAR_MAX) {
    line->bad = 1u;
  }
  LineAdd(line, (char)event);
  return LINE_NONE;
}
