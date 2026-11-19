// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/touch_commands.c
\brief      TOUCH_ID and TOUCH_READ commands of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.0
\date       19/11/2026

\details
  Implements protocol.md sections 6.20 to 6.22.
  - The FT5336 reset is NRST: no access before HIL_TOUCH_START_MS after the
    start, so a command received earlier waits until then (section 6.20).
  - The first touch command of the session configures I2C3; the commands do
    not depend on LCD_INIT and never return BUSY.
  - Driver results map to the protocol codes: TIMEOUT (no acknowledge, or a
    wait past its limit) gives DEVICE_TIMEOUT; FAILURE (bus error, lost
    arbitration, more than 5 points) gives DEVICE_ERROR.

\section touch_commands_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 19/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "touch_commands.h"

#include <stddef.h>

#include "board.h" // BOARD_I2C_TOUCH, FT5336_ADDR
#include "defines.h"
#include "delay/delay.h"
#include "hil_protocol.h"
#include "touch/touch.h"

#define CHIP_ID_TEXT_LEN 4u ///< "0x" and two digits (section 6.21).

static uint8_t touch_ready; ///< I2C3 configured in this session.

/*!
\brief  Protocol code of a failed touch driver call (section 6.20).
*/
static const char *TouchError(int rc)
{
  return (rc == TIMEOUT) ? HIL_ERR_DEVICE_TIMEOUT : HIL_ERR_DEVICE_ERROR;
}

/*!
\brief  Wait for the controller start time, then configure I2C3 once.
\details The wait ends HIL_TOUCH_START_MS after the start at the latest, well
         within the 2 s response timeout (section 6.20).
\return NULL, or DEVICE_TIMEOUT if the I2C3 kernel clock does not start.
*/
static const char *TouchStart(void)
{
  while (SysTickMs() < HIL_TOUCH_START_MS) {
  }
  if (!touch_ready) {
    if (TouchInit(&BOARD_I2C_TOUCH) != SUCCESS) {
      return HIL_ERR_DEVICE_TIMEOUT; // HSI did not become ready
    }
    touch_ready = 1u;
  }
  return NULL;
}

/*!
\brief  Append the chip_id field: 0x and two uppercase hexadecimal digits (section 6.21).
*/
static void AddChipId(Record *result, uint8_t id)
{
  static const char digits[] = "0123456789ABCDEF";
  char text[CHIP_ID_TEXT_LEN + 1u] = {'0', 'x', digits[id >> 4], digits[id & 0xFu], '\0'};

  RecordAdd(result, HIL_KEY_CHIP_ID, text);
}

const char *TouchIdCmd(const CommandArg *args, uint32_t count, Record *result)
{
  const char *code;
  uint8_t id;
  int rc;

  (void)args;
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT; // Before any wait or bus access
  }
  code = TouchStart();
  if (code != NULL) {
    return code;
  }
  rc = TouchReadId(&BOARD_I2C_TOUCH, FT5336_ADDR, &id);
  if (rc != SUCCESS) {
    return TouchError(rc);
  }
  AddChipId(result, id);
  return NULL;
}

const char *TouchReadCmd(const CommandArg *args, uint32_t count, Record *result)
{
  const char *code;
  uint32_t points;
  TouchPoint p1;
  int rc;

  (void)args;
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT; // Before any wait or bus access
  }
  code = TouchStart();
  if (code != NULL) {
    return code;
  }
  rc = TouchRead(&BOARD_I2C_TOUCH, FT5336_ADDR, &points, &p1);
  if (rc != SUCCESS) {
    return TouchError(rc);
  }
  RecordAddDec(result, HIL_KEY_POINTS, points);
  if (points >= 1u) {
    RecordAddDec(result, HIL_KEY_X, p1.x);
    RecordAddDec(result, HIL_KEY_Y, p1.y);
  }
  return NULL;
}
