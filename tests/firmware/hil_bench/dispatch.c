// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/dispatch.c
\brief      Check protocol requests and run the matching command.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements protocol.md sections 5.1, 5.2 and 7. Checks run in this order:
  - first token CMD and second token id=<1..65535> without a leading zero,
    otherwise ERROR code=BAD_FRAME (section 5.2.2);
  - command=<name> as third token, then key=value arguments with distinct
    and non-reserved keys, otherwise BAD_REQUEST;
  - a command of the table, otherwise UNKNOWN_COMMAND.
  A request with a valid id always gets one RESULT and one END. A result
  line that would exceed the maximum length is replaced by code INTERNAL.

\section dispatch_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "dispatch.h"

#include <stddef.h>

#include "commands.h"
#include "hil_protocol.h"
#include "protocol.h"

void DispatchFrameError(const char *code)
{
  Record error;

  RecordBegin(&error, HIL_REC_ERROR);
  RecordAdd(&error, HIL_KEY_CODE, code);
  RecordSend(&error);
}

/*!
\brief  Send RESULT id=<id> status=ERR code=<code>.
*/
static void SendResultError(uint32_t id, const char *code)
{
  Record result;

  RecordBegin(&result, HIL_REC_RESULT);
  RecordAddDec(&result, HIL_KEY_ID, id);
  RecordAdd(&result, HIL_KEY_STATUS, HIL_STATUS_ERR);
  RecordAdd(&result, HIL_KEY_CODE, code);
  RecordSend(&result);
}

/*!
\brief  Send END id=<id>.
*/
static void SendEnd(uint32_t id)
{
  Record end;

  RecordBegin(&end, HIL_REC_END);
  RecordAddDec(&end, HIL_KEY_ID, id);
  RecordSend(&end);
}

/*!
\brief  Check the tokens after id: command first, then the arguments.
\param  tokens  Tokens after id.
\param  count   Number of tokens.
\param  name    Receives the command name.
\param  args    Receives the arguments.
\param  nargs   Receives the number of arguments.
\return NULL if the request is well formed, otherwise HIL_ERR_BAD_REQUEST.
*/
static const char *CheckRequest(char *tokens[], uint32_t count, const char **name, CommandArg *args,
                                uint32_t *nargs)
{
  char *key;
  char *value;

  *nargs = 0u;
  if (count == 0u || !RecordSplitField(tokens[0], &key, &value) || !RecordStrEq(key, HIL_KEY_COMMAND)) {
    return HIL_ERR_BAD_REQUEST;
  }
  *name = value;

  for (uint32_t i = 1u; i < count; ++i) {
    if (!RecordSplitField(tokens[i], &key, &value) || RecordStrEq(key, HIL_KEY_ID) ||
        RecordStrEq(key, HIL_KEY_COMMAND)) {
      return HIL_ERR_BAD_REQUEST; // No '=', bad key or value, or reserved key
    }
    for (uint32_t j = 0u; j < *nargs; ++j) {
      if (RecordStrEq(args[j].key, key)) {
        return HIL_ERR_BAD_REQUEST; // Duplicate key
      }
    }
    args[*nargs].key = key;
    args[*nargs].value = value;
    ++*nargs;
  }
  return NULL;
}

void DispatchLine(char *line)
{
  char *tokens[RECORD_MAX_TOKENS];
  uint32_t count = RecordSplit(line, tokens);
  char *key;
  char *value;
  uint32_t id;

  /* Without CMD and a valid id, there is no request to answer (section 5.2.2). */
  if (count < 2u || !RecordStrEq(tokens[0], HIL_REC_CMD) || !RecordSplitField(tokens[1], &key, &value) ||
      !RecordStrEq(key, HIL_KEY_ID) || !RecordParseDec(value, HIL_ID_MAX, &id) || id < HIL_ID_MIN) {
    DispatchFrameError(HIL_FRAME_BAD_FRAME);
    return;
  }

  const char *name = NULL;
  CommandArg args[COMMAND_MAX_ARGS];
  uint32_t nargs;
  const Command *command = NULL;
  const char *code = CheckRequest(&tokens[2], count - 2u, &name, args, &nargs);

  if (code == NULL) {
    command = CommandFind(name);
    if (command == NULL) {
      code = HIL_ERR_UNKNOWN_COMMAND;
    }
  }
  if (code == NULL) {
    Record result;

    RecordBegin(&result, HIL_REC_RESULT);
    RecordAddDec(&result, HIL_KEY_ID, id);
    RecordAdd(&result, HIL_KEY_STATUS, HIL_STATUS_OK);
    code = command->run(args, nargs, &result);
    if (code == NULL && !RecordSend(&result)) {
      code = HIL_ERR_INTERNAL; // The result fields do not fit in one line
    }
  }
  if (code != NULL) {
    SendResultError(id, code);
  }
  SendEnd(id);
}
