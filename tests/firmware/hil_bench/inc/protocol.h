// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/protocol.h
\brief      Split received records into tokens and write records to send.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements the record syntax of protocol.md section 2.3. RecordSplit()
  cuts a received line into tokens in place, accepting several spaces between
  tokens. A Record is built field by field in a buffer and RecordSend() sends
  it with CRLF only if it fits in HIL_LINE_MAX_LEN bytes. The firmware is
  built without a C library, so the few string helpers it needs are here.

\section protocol_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>

#include "hil_protocol.h"

/// Most tokens a line can hold: a token and its separator take 2 bytes at least.
#define RECORD_MAX_TOKENS (HIL_LINE_MAX_LEN / 2u)

/// Record being written.
typedef struct {
  char text[HIL_LINE_MAX_LEN + 1u]; ///< Record without terminator, NUL-terminated.
  uint32_t len;                     ///< Bytes in text.
  uint8_t overflow;                 ///< A field did not fit: the record is not sent.
} Record;

/*!
\brief  Cut a line into space-separated tokens, in place.
\param  line    NUL-terminated line; spaces are replaced by NULs.
\param  tokens  Receives a pointer to each token.
\return Number of tokens, at most RECORD_MAX_TOKENS.
*/
uint32_t RecordSplit(char *line, char *tokens[RECORD_MAX_TOKENS]);

/*!
\brief  Cut a key=value token at its '=' and check both parts.
\param  token  Token; its '=' is replaced by a NUL.
\param  key    Receives the key: a lowercase letter, then lowercase letters,
               digits and underscores.
\param  value  Receives the value: non-empty, without '='.
\return 1 if the token is a valid field, otherwise 0.
*/
int RecordSplitField(char *token, char **key, char **value);

/*!
\brief  Parse an unsigned decimal value without sign or leading zeros.
\param  text   NUL-terminated digits.
\param  max    Largest accepted value.
\param  value  Receives the value.
\return 1 if text is a valid value up to max, otherwise 0.
*/
int RecordParseDec(const char *text, uint32_t max, uint32_t *value);

/*!
\brief  Compare two NUL-terminated strings.
\return 1 if they are equal, otherwise 0.
*/
int RecordStrEq(const char *a, const char *b);

/*!
\brief  Length of a NUL-terminated string.
*/
uint32_t RecordStrLen(const char *s);

/*!
\brief  Start a record with its type.
\param  record  Record to write.
\param  type    Record type, for example HIL_REC_RESULT.
*/
void RecordBegin(Record *record, const char *type);

/*!
\brief  Append a key=value field, preceded by one space.
*/
void RecordAdd(Record *record, const char *key, const char *value);

/*!
\brief  Append a field with an unsigned decimal value.
*/
void RecordAddDec(Record *record, const char *key, uint32_t value);

/*!
\brief  Append a field with a value written as 0x and eight uppercase hexadecimal digits.
*/
void RecordAddHex32(Record *record, const char *key, uint32_t value);

/*!
\brief  Bytes still free in the record before it reaches HIL_LINE_MAX_LEN.
*/
uint32_t RecordRoom(const Record *record);

/*!
\brief  Send the record with CRLF on the protocol link.
\return 1 if sent; 0 if a field did not fit, and nothing was sent.
*/
int RecordSend(const Record *record);

#endif /* PROTOCOL_H */
