// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/touch_commands.h
\brief      TOUCH_ID and TOUCH_READ commands of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.0
\date       19/11/2026

\details
  Implements protocol.md sections 6.20 to 6.22. The handlers have the
  CommandRun signature of commands.h and are listed in its table.

\section touch_commands_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 19/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef TOUCH_COMMANDS_H
#define TOUCH_COMMANDS_H

#include <stdint.h>

#include "commands.h"

/// TOUCH_ID: chip identifier of the touch controller (section 6.21).
const char *TouchIdCmd(const CommandArg *args, uint32_t count, Record *result);

/// TOUCH_READ: number of points and first point (section 6.22).
const char *TouchReadCmd(const CommandArg *args, uint32_t count, Record *result);

#endif /* TOUCH_COMMANDS_H */
