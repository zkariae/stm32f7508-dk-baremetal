// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/commands.c
\brief      Command table of the HIL protocol firmware: HELLO and CAPS.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md sections 6.2 and 6.3.
  - HELLO takes no argument and returns name, proto, fw and build, the
    values of the readiness banner.
  - CAPS returns the table names from start (default 0), as many as fit in
    one line, with next when names remain.
  A new command is added to the table only once it is specified in
  protocol.md section 6 (section 6.1).

\section commands_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "commands.h"

#include <stddef.h>

#include "hil_protocol.h"

#define CAPS_NAMES_PREFIX_LEN 7u ///< " names=" before the names.
#define CAPS_NEXT_FIELD_MAX   9u ///< " next=255": total is 255 at most.

static const char *Hello(const CommandArg *args, uint32_t count, Record *result);
static const char *Caps(const CommandArg *args, uint32_t count, Record *result);

/// Fixed order: CAPS reports the names in this order.
static const Command commands[] = {
  {HIL_CMD_HELLO, Hello},
  {HIL_CMD_CAPS, Caps},
};

#define COMMAND_COUNT ((uint32_t)(sizeof commands / sizeof commands[0]))

/*!
\brief  HELLO: firmware identity, identical to the readiness banner.
*/
static const char *Hello(const CommandArg *args, uint32_t count, Record *result)
{
  (void)args;
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  RecordAdd(result, HIL_KEY_NAME, HIL_FW_NAME);
  RecordAdd(result, HIL_KEY_PROTO, HIL_PROTO_VERSION_STR);
  RecordAdd(result, HIL_KEY_FW, HIL_FW_VERSION);
  RecordAdd(result, HIL_KEY_BUILD, HIL_BUILD_ID);
  return NULL;
}

/*!
\brief  CAPS: one page of command names.
*/
static const char *Caps(const CommandArg *args, uint32_t count, Record *result)
{
  uint32_t start = 0u;

  for (uint32_t i = 0u; i < count; ++i) {
    if (!RecordStrEq(args[i].key, HIL_KEY_START) || !RecordParseDec(args[i].value, COMMAND_COUNT - 1u, &start)) {
      return HIL_ERR_INVALID_ARGUMENT; // Unknown argument, or start malformed or not lower than total
    }
  }
  RecordAddDec(result, HIL_KEY_TOTAL, COMMAND_COUNT);
  RecordAddDec(result, HIL_KEY_START, start);

  uint32_t room = RecordRoom(result);
  room = (room > CAPS_NAMES_PREFIX_LEN) ? room - CAPS_NAMES_PREFIX_LEN : 0u;

  /* Add whole names while they fit, keeping room for next while names remain. */
  char names[HIL_LINE_MAX_LEN + 1u];
  uint32_t len = 0u;
  uint32_t end = start;

  while (end < COMMAND_COUNT) {
    uint32_t need = RecordStrLen(commands[end].name) + ((end > start) ? 1u : 0u);
    uint32_t reserve = (end + 1u < COMMAND_COUNT) ? CAPS_NEXT_FIELD_MAX : 0u;

    if (len + need + reserve > room) {
      break;
    }
    if (end > start) {
      names[len++] = ',';
    }
    for (const char *p = commands[end].name; *p != '\0'; ++p) {
      names[len++] = *p;
    }
    ++end;
  }
  if (end == start) {
    return HIL_ERR_INTERNAL; // Not even one name fits
  }
  names[len] = '\0';
  RecordAdd(result, HIL_KEY_NAMES, names);
  if (end < COMMAND_COUNT) {
    RecordAddDec(result, HIL_KEY_NEXT, end);
  }
  return NULL;
}

const Command *CommandFind(const char *name)
{
  for (uint32_t i = 0u; i < COMMAND_COUNT; ++i) {
    if (RecordStrEq(commands[i].name, name)) {
      return &commands[i];
    }
  }
  return NULL;
}
