// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/protocol.c
\brief      Split received records into tokens and write records to send.

\author     Z. BEN-AKKA
\version    1.0
\date       23/10/2026

\details
  Implements the record syntax of protocol.md section 2.3. Received lines
  have already been checked by line.c, so they hold printable ASCII only.
  Records are written with exactly one space between tokens; a record that
  would exceed HIL_LINE_MAX_LEN bytes is marked and never sent.

\section protocol_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 23/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "protocol.h"

#include "board.h"

/// A key starts with a lowercase letter (section 2.3).
static int IsKeyStart(char c)
{
  return c >= 'a' && c <= 'z';
}

/// Then lowercase letters, digits and underscores.
static int IsKeyChar(char c)
{
  return IsKeyStart(c) || (c >= '0' && c <= '9') || c == '_';
}

uint32_t RecordSplit(char *line, char *tokens[RECORD_MAX_TOKENS])
{
  uint32_t count = 0u;
  char *p = line;

  for (;;) {
    while (*p == ' ') {
      *p++ = '\0';
    }
    if (*p == '\0' || count == RECORD_MAX_TOKENS) {
      return count;
    }
    tokens[count++] = p;
    while (*p != ' ' && *p != '\0') {
      ++p;
    }
  }
}

int RecordSplitField(char *token, char **key, char **value)
{
  char *equal = token;

  if (!IsKeyStart(*equal)) {
    return 0;
  }
  while (IsKeyChar(*equal)) {
    ++equal;
  }
  if (*equal != '=' || equal[1] == '\0') {
    return 0;
  }
  for (const char *p = equal + 1; *p != '\0'; ++p) {
    if (*p == '=') {
      return 0;
    }
  }
  *equal = '\0';
  *key = token;
  *value = equal + 1;
  return 1;
}

int RecordParseDec(const char *text, uint32_t max, uint32_t *value)
{
  uint32_t v = 0u;

  if (text[0] == '\0' || (text[0] == '0' && text[1] != '\0')) {
    return 0; // Empty, or a leading zero
  }
  for (const char *p = text; *p != '\0'; ++p) {
    if (*p < '0' || *p > '9') {
      return 0;
    }
    uint32_t digit = (uint32_t)(*p - '0');
    if (digit > max || v > (max - digit) / 10u) {
      return 0; // v * 10 + digit would exceed max
    }
    v = v * 10u + digit;
  }
  *value = v;
  return 1;
}

int RecordStrEq(const char *a, const char *b)
{
  while (*a != '\0' && *a == *b) {
    ++a;
    ++b;
  }
  return *a == *b;
}

uint32_t RecordStrLen(const char *s)
{
  uint32_t len = 0u;

  while (s[len] != '\0') {
    ++len;
  }
  return len;
}

/*!
\brief  Append a string to the record, or mark it as overflowed.
*/
static void RecordPut(Record *record, const char *s)
{
  for (; *s != '\0'; ++s) {
    if (record->len >= HIL_LINE_MAX_LEN) {
      record->overflow = 1u;
      break;
    }
    record->text[record->len++] = *s;
  }
  record->text[record->len] = '\0';
}

void RecordBegin(Record *record, const char *type)
{
  record->len = 0u;
  record->overflow = 0u;
  RecordPut(record, type);
}

void RecordAdd(Record *record, const char *key, const char *value)
{
  RecordPut(record, " ");
  RecordPut(record, key);
  RecordPut(record, "=");
  RecordPut(record, value);
}

void RecordAddDec(Record *record, const char *key, uint32_t value)
{
  char digits[11]; // 4294967295 and its NUL
  char *p = &digits[sizeof digits - 1u];

  *p = '\0';
  do {
    *--p = (char)('0' + value % 10u);
    value /= 10u;
  } while (value != 0u);
  RecordAdd(record, key, p);
}

void RecordAddHex32(Record *record, const char *key, uint32_t value)
{
  static const char hex[] = "0123456789ABCDEF";
  char text[11]; // 0x, eight digits and the NUL

  text[0] = '0';
  text[1] = 'x';
  for (uint32_t i = 0u; i < 8u; ++i) {
    text[2u + i] = hex[(value >> (28u - 4u * i)) & 0xFu];
  }
  text[10] = '\0';
  RecordAdd(record, key, text);
}

uint32_t RecordRoom(const Record *record)
{
  return record->overflow ? 0u : HIL_LINE_MAX_LEN - record->len;
}

int RecordSend(const Record *record)
{
  if (record->overflow) {
    return 0;
  }
  UartPuts(&BOARD_UART_VCP, record->text);
  UartPuts(&BOARD_UART_VCP, "\n"); // UartPuts sends CRLF
  return 1;
}
