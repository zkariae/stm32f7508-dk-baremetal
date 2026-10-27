// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/line.h
\brief      Assemble protocol lines from UART receive events.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md sections 2.2 and 2.4. LinePush() takes one event
  from UartRxGet() at a time and reports a result when a line terminator
  arrives: a complete line, LINE_TOO_LONG or BAD_FRAME, each once per line.
  Empty lines and lines of spaces only are ignored.

\section line_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef LINE_H
#define LINE_H

#include <stdint.h>

#include "hil_protocol.h"
#include "uart/uart.h"

/// Result of LinePush().
typedef enum {
  LINE_NONE,      ///< No complete line yet, or a blank line was ignored.
  LINE_READY,     ///< LineAssembler.text holds a complete line.
  LINE_TOO_LONG,  ///< The line exceeded HIL_LINE_MAX_LEN bytes.
  LINE_BAD_FRAME, ///< The line had an invalid byte or a receive error.
} LineStatus;

/// Line being received. A zero-initialized assembler is empty.
typedef struct {
  char text[HIL_LINE_MAX_LEN + 1u]; ///< Line without terminator, NUL-terminated on LINE_READY.
  uint32_t len;                     ///< Bytes received; HIL_LINE_MAX_LEN + 1 means too long.
  uint8_t cr;                       ///< The last byte was a CR, kept until the next byte.
  uint8_t bad;                      ///< An invalid byte or a receive error was seen.
} LineAssembler;

/*!
\brief  Add one receive event to the line being assembled.
\param  line   Line assembler.
\param  event  Byte or UART_RX_EVENT_* error from UartRxGet().
\return LINE_READY when line->text holds a complete line, valid until the
        next call; LINE_TOO_LONG or LINE_BAD_FRAME when a line was
        discarded; otherwise LINE_NONE.
*/
LineStatus LinePush(LineAssembler *line, UartRxEvent event);

#endif /* LINE_H */
