// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/commands.c
\brief      Command table of the HIL protocol firmware: HELLO, CAPS, LED_SET and LED_GET.

\author     Z. BEN-AKKA
\version    1.1
\date       27/10/2026

\details
  Implements protocol.md sections 6.2 to 6.5.
  - HELLO takes no argument and returns name, proto, fw and build, the
    values of the readiness banner.
  - CAPS returns the table names from start (default 0), as many as fit in
    one line, with next when names remain.
  - LED_SET drives LD1 on, off or to the opposite of its pin level, then
    reads the pin back; LED_GET reports that level. main.c configures the
    pin before the banner.
  A new command is added to the table only once it is specified in
  protocol.md section 6 (section 6.1).

\section commands_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 27/10/2026 | Z. BEN-AKKA | Add LED_SET and LED_GET. |
****************************
*/

#include "commands.h"

#include <stddef.h>

#include "board.h" // BOARD_LED_LD1, GPIO_IDR
#include "hil_protocol.h"

#define CAPS_NAMES_PREFIX_LEN 7u ///< " names=" before the names.
#define CAPS_NEXT_FIELD_MAX   9u ///< " next=255": total is 255 at most.
#define LED_READBACK_MAX      16u ///< IDR reads before LED_SET gives up: the input synchronizer lags a few cycles.

static const char *Hello(const CommandArg *args, uint32_t count, Record *result);
static const char *Caps(const CommandArg *args, uint32_t count, Record *result);
static const char *LedSet(const CommandArg *args, uint32_t count, Record *result);
static const char *LedGet(const CommandArg *args, uint32_t count, Record *result);

/// Fixed order: CAPS reports the names in this order.
static const Command commands[] = {
  {HIL_CMD_HELLO, Hello},
  {HIL_CMD_CAPS, Caps},
  {HIL_CMD_LED_SET, LedSet},
  {HIL_CMD_LED_GET, LedGet},
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

/*!
\brief  1 if LD1 is lit, from the pin level in GPIO_IDR (section 6.4).
*/
static uint32_t LedIsLit(void)
{
  uint32_t high = (GPIO_IDR(BOARD_LED_LD1.port) >> BOARD_LED_LD1.pin) & 1u;

  return (high != 0u) == (BOARD_LED_LD1.active_high != 0u);
}

/*!
\brief  LED_SET: drive LD1 and report the level read back on the pin.
*/
static const char *LedSet(const CommandArg *args, uint32_t count, Record *result)
{
  uint32_t lit;

  if (count != 1u || !RecordStrEq(args[0].key, HIL_KEY_STATE)) {
    return HIL_ERR_INVALID_ARGUMENT; // state missing, or another argument
  }
  if (RecordStrEq(args[0].value, HIL_LED_ON)) {
    lit = 1u;
  } else if (RecordStrEq(args[0].value, HIL_LED_OFF)) {
    lit = 0u;
  } else if (RecordStrEq(args[0].value, HIL_LED_TOGGLE)) {
    lit = !LedIsLit();
  } else {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  if (lit) {
    LedOn(&BOARD_LED_LD1);
  } else {
    LedOff(&BOARD_LED_LD1);
  }
  for (uint32_t i = 0u; LedIsLit() != lit; ++i) {
    if (i == LED_READBACK_MAX) {
      return HIL_ERR_DEVICE_ERROR; // The pin does not follow the output
    }
  }
  RecordAdd(result, HIL_KEY_STATE, lit ? HIL_LED_ON : HIL_LED_OFF);
  return NULL;
}

/*!
\brief  LED_GET: state of LD1, unchanged.
*/
static const char *LedGet(const CommandArg *args, uint32_t count, Record *result)
{
  (void)args;
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  RecordAdd(result, HIL_KEY_STATE, LedIsLit() ? HIL_LED_ON : HIL_LED_OFF);
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
