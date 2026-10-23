// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/dispatch.h
\brief      Check protocol requests and run the matching command.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md sections 5.1, 5.2 and 7. DispatchLine() checks a
  complete request line, runs the command and sends RESULT then END; a line
  without a valid CMD and id gets an uncorrelated ERROR instead.
  DispatchFrameError() sends the ERROR record of a discarded line.

\section dispatch_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef DISPATCH_H
#define DISPATCH_H

/*!
\brief  Check one request line, run its command and send the response.
\param  line  NUL-terminated line from line.c; it is cut into tokens in place.
*/
void DispatchLine(char *line);

/*!
\brief  Send an uncorrelated ERROR record.
\param  code  Frame code: HIL_FRAME_LINE_TOO_LONG or HIL_FRAME_BAD_FRAME.
*/
void DispatchFrameError(const char *code);

#endif /* DISPATCH_H */
