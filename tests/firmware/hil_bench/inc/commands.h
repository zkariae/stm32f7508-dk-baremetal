// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/commands.h
\brief      Command table of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md section 6. Each command checks its own arguments
  and appends its result fields; dispatch.c has already checked the request
  envelope (section 5.1). The table order is the order CAPS reports.

\section commands_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>

#include "protocol.h"

/// Most arguments a request can hold: its tokens after CMD, id and command.
#define COMMAND_MAX_ARGS (RECORD_MAX_TOKENS - 3u)

/// One key=value argument of a request.
typedef struct {
  const char *key;
  const char *value;
} CommandArg;

/*!
\brief  Run a command.
\param  args    Request arguments, with distinct and non-reserved keys.
\param  count   Number of arguments.
\param  result  RESULT record, written up to status=OK; the command appends
                its result fields.
\return NULL on success, otherwise the response code (section 7.1); the
        result fields are then dropped.
*/
typedef const char *(*CommandRun)(const CommandArg *args, uint32_t count, Record *result);

/// A command of the table.
typedef struct {
  const char *name; ///< Command name (section 6.1).
  CommandRun run;   ///< Handler.
} Command;

/*!
\brief  Look a command up by name.
\param  name  Value of the command field.
\return The command, or NULL if the firmware does not implement it.
*/
const Command *CommandFind(const char *name);

#endif /* COMMANDS_H */
