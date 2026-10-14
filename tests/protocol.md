<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/protocol.md
\brief      HIL firmware-to-host protocol specification.

\author     Z. BEN-AKKA
\version    1.2
\date       14/10/2026

\details
  Documents the communication protocol shared by the HIL firmware and host
  test runner. This document revision is independent of both the wire protocol
  version and the firmware version.

\section protocol_md_version_history Version history
| Version | Date       | Author      | Description                              |
|:-------:|:----------:|:------------|:-----------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                         |
****************************
-->

# HIL host–firmware protocol

## Purpose and scope

This document defines the first serial protocol between the PC test runner and
the STM32F7508-DK HIL bench firmware. The initial end-to-end exchange is
`HELLO`; later commands can use the same message envelope and be added to the
capability list.

Three version numbers have separate meanings:

- **Document revision** (`\version` in this header) tracks edits to this
  specification.
- **Protocol version** identifies the wire format and command contract. It is
  written as `MAJOR.MINOR`.
- **Firmware version** identifies the firmware image and is versioned
  independently of the protocol.

The host must compare the protocol major in the startup banner with the
protocol major it supports. It refuses the session before sending any command
if the majors differ. A minor version change is backward-compatible; when the
major matches, the host proceeds and uses `CAPS` to check command availability.
Firmware version differences alone do not make the protocol incompatible.

The host is responsible for building and programming the firmware, resetting
the board, opening the serial port, sending commands, enforcing timeouts, and
checking the replies. The firmware announces readiness after initialization,
executes each accepted command, and returns an explicit success or error.

## Serial transport and framing

- Use the ST-LINK virtual COM port connected to the board's USART1.
- Configure the link for **115200 baud, 8 data bits, no parity, 1 stop bit**
  (8N1), with no hardware flow control. This matches the repository's existing
  USART console applications.
- Messages are printable ASCII lines terminated by CRLF (`\r\n`). The firmware
  accepts LF (`\n`) as the line terminator too and strips an optional preceding
  CR. The host sends CRLF.
- Each line is at most 128 bytes before its line terminator. Empty lines are
  ignored. A line that exceeds this limit is discarded through its terminator
  and reported as a protocol error.
- Fields are separated by one or more spaces. Command names and status values
  are uppercase. Arguments and result fields use `key=value` tokens without
  embedded spaces. The first protocol version has no quoting or binary payloads.
- The protocol UART carries only the startup banner and protocol records; do
  not interleave unstructured debug output with them.

The current shared UART driver only transmits. Firmware command handling will
need bounded UART reception before this protocol can be used on the board.

## Startup and readiness

After reset and initialization, the firmware sends one readiness line:

```text
HIL-BENCH PROTO=1.0 FW=1.0 READY CAPS=HELLO
```

`PROTO` is the wire protocol version; `FW` is the firmware image version.
These fields must not be treated as interchangeable. The line also contains
the firmware name, ready state, and comma-separated list of commands supported
by this build. The host opens or flushes the serial port around reset, then
waits up to **5 seconds** for this line. It must parse and validate the banner,
then compare the protocol major before sending any command. A missing or
malformed banner is a startup/communication failure; a different protocol
major is an incompatible-protocol failure and the host rejects the session.

As commands are implemented, their names are added to `CAPS`; the host should
check that a command is advertised before requesting it. For example,
`CAPS=HELLO,QSPI_READ_ID` advertises both commands.

## Request and response format

The host sends one command at a time:

```text
CMD <id> <command> [argument=value ...]
```

The firmware returns exactly one result record, followed by one end record:

```text
RESULT <id> OK [field=value ...]
END <id>
```

If the command fails, the result uses an explicit error status and code:

```text
RESULT <id> ERR <error-code> [field=value ...]
END <id>
```

`END` marks the completion of that transaction and is always the last record
for it. A response may not be treated as complete until both its matching
`RESULT` and `END` have arrived. The firmware echoes the request ID in both
records so the host can reject stale or mismatched replies.

Transaction IDs are unsigned decimal integers from 1 to 65535. The host starts
at 1, increases the ID for each request, and allows only one outstanding
request. It does not reuse IDs in the same serial session; after reaching 65535
it resets the board and starts a new session at 1.

### Initial command: `HELLO`

`HELLO` takes no arguments and checks that the command path is ready:

```text
Host -> CMD 1 HELLO
Firmware -> RESULT 1 OK name=hil-bench protocol=1.0 firmware=1.0
Firmware -> END 1
```

The `protocol` field reports the wire protocol version and the `firmware` field
reports the firmware image version. The host passes the check only if it
receives `RESULT 1 OK` with the expected identity and supported protocol major,
then `END 1`, before the command timeout. The `HELLO` version fields must agree
with the startup banner.

### Example of a later peripheral command

The same envelope can carry future commands without changing the transport.
For example, the planned QSPI identifier check could look like this once that
command is implemented and advertised:

```text
Host -> CMD 42 QSPI_READ_ID
Firmware -> RESULT 42 OK id=<device-id>
Firmware -> END 42
```

The exact result fields for each peripheral command must be specified here
before that command is implemented by either side.

## Errors and malformed input

For a valid request whose command cannot be completed, the firmware returns a
transaction result with one of these error codes:

| Error code | Meaning |
|:--|:--|
| `BAD_REQUEST` | The request syntax or required fields are invalid. |
| `UNKNOWN_COMMAND` | The command name is not supported by this firmware. |
| `INVALID_ARGUMENT` | An argument is missing, unsupported, or out of range. |
| `BUSY` | The firmware cannot accept the command in its current state. |
| `INTERNAL` | The command failed because of an unexpected firmware error. |

For example:

```text
CMD 7 NO_SUCH_COMMAND
RESULT 7 ERR UNKNOWN_COMMAND
END 7
```

If a line is too long or its transaction ID cannot be parsed, the firmware
returns an uncorrelated error record, which has no `END` record:

```text
ERROR LINE_TOO_LONG
```

The host treats an uncorrelated error, malformed reply, unexpected ID, or
missing `END` as a protocol/communication failure. A syntactically valid
request with a parseable ID always receives `RESULT` and `END`, including on
error.

## Timeouts and recovery

- Startup banner timeout: **5 seconds** after reset.
- `HELLO` response timeout: **2 seconds** after the complete request is sent.
- Every later command must specify its own response timeout; the host
  configuration may override the default for a test case.
- Firmware operations must be bounded so that a command either returns a
  result or can be classified as timed out by the host.
- On timeout, the host records a communication failure, stops issuing commands,
  resets the board, and waits for a fresh readiness banner before starting a
  new session. It does not blindly resend a command because a timed-out command
  may already have changed hardware state.

The runner should report at least three distinct outcomes: programming/reset
failure, serial/protocol failure (including timeout), and a firmware-reported
functional error.

## Open-source examples consulted

- [STM32 OpenHTF demo](https://github.com/bbmegareve/stm32_openhtf_demo): an
  STM32 firmware UART CLI tested from a host that flashes through ST-Link and
  checks serial behavior.
- [PHiLIP](https://github.com/riot-appstore/PHiLIP): a serial command interface
  with a Python wrapper and explicit operation results; its firmware is a test
  fixture that drives another device, so its bench arrangement differs.
- [pytest-embedded](https://github.com/espressif/pytest-embedded): pytest
  examples and serial services for observing firmware output and managing
  embedded targets.
- [GM65 scanner CDC protocol](https://github.com/Amperstrand/gm65-scanner): a
  documented binary frame, command table, response format, and host/firmware
  sequence diagram. It is useful as a framing reference; this HIL protocol
  starts with readable text records instead.
