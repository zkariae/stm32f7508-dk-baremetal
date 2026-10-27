<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/protocol.md
\brief      HIL firmware-to-host protocol specification.

\author     Z. BEN-AKKA
\version    1.3
\date       22/10/2026

\details
  Specifies the HIL host-firmware serial interface, including record syntax,
  version compatibility, HELLO/CAPS commands, reset reporting, error handling,
  transaction timeouts, and session recovery. The document revision is
  independent of the wire protocol and firmware versions.

\section protocol_md_version_history Version history
| Version | Date       | Author      | Description                              |
|:-------:|:----------:|:------------|:-----------------------------------------|
| 1.0     | 14/10/2026 | Z. BEN-AKKA | Initial version.                         |
| 1.1     | 16/10/2026 | Z. BEN-AKKA | Formalize HIL records, commands, reset reporting, and recovery. |
| 1.2     | 22/10/2026 | Z. BEN-AKKA | Update §2.4 note: the UART driver now receives. |
| 1.3     | 22/10/2026 | Z. BEN-AKKA | Add noise and RX overflow to BAD_FRAME; report line errors once at the terminator. |
****************************
-->

# HIL host–firmware protocol specification

## 1. Scope

This specification defines the serial interface between the PC test host and
the STM32F7508-DK HIL bench firmware. It specifies:

- the serial transport parameters and line framing;
- session establishment and version compatibility;
- the request and response records;
- the result and error codes;
- the reporting of the board reset cause;
- timeouts and recovery.


The initial command set contains `HELLO` and `CAPS`. Additional commands
SHALL be specified in section 6 before either endpoint implements them.

### 1.1 Conventions

The key words **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, and
**MAY** in this document are to be interpreted as described in RFC 2119 and
RFC 8174 when, and only when, they appear in all capitals:

- **SHALL** / **SHALL NOT**: absolute requirement or prohibition.
- **SHOULD** / **SHOULD NOT**: recommendation; a deviation requires a
  documented reason.
- **MAY**: optional behavior.

### 1.2 Terms

| Term         | Definition                                                                               |
|:-------------|:-----------------------------------------------------------------------------------------|
| Host         | The PC test runner that drives the protocol.                                             |
| Firmware     | The program running on the STM32F7508-DK that answers requests.                          |
| Record       | One line of text sent over the link, terminated as defined in section 2.2.               |
| Session      | The exchange that starts with a valid readiness banner and ends at the next board reset. |
| Transaction  | One request and its correlated response records.                                         |

Examples and notes are informative. All other text is normative.

## 2. Transport

### 2.1 Serial link

Both endpoints SHALL use the following link parameters:

| Parameter | Value |
|:--|:--|
| Interface | ST-LINK virtual COM port, connected to the board's USART1 |
| Baud rate | 115200 bit/s |
| Data format | 8 data bits, no parity, 1 stop bit (8N1) |
| Flow control | None |

### 2.2 Line framing

- Each record SHALL be sent as one line terminated by CRLF (`\r\n`).
- On reception, each endpoint SHALL also accept LF (`\n`) alone as a line
  terminator and SHALL remove one CR immediately preceding the LF.
- A line SHALL contain only printable ASCII characters (0x20 to 0x7E),
  excluding the terminator.
- A line SHALL NOT exceed 128 bytes, excluding the terminator. This limit
  applies in both directions.
- A received line that is empty or contains only spaces SHALL be ignored.

### 2.3 Record syntax

Each record SHALL have the following form:

```text
<TYPE> [<key>=<value> ...]
```

- `<TYPE>` SHALL consist of uppercase letters (`A` to `Z`).
- `<key>` SHALL consist of lowercase letters, digits, and underscores
  (`a` to `z`, `0` to `9`, `_`), and SHALL start with a letter.
- `<value>` SHALL be a non-empty sequence of printable ASCII characters
  excluding space (0x20) and `=` (0x3D). Values are case-sensitive.
- An endpoint SHALL send exactly one space (0x20) between tokens and SHALL
  NOT send leading or trailing spaces. On reception, an endpoint SHALL
  accept one or more spaces between tokens and SHALL ignore leading and
  trailing spaces.
- Protocol version 1.x does not support quoting, escape sequences, or binary
  payloads.

Only records defined by this specification SHALL be sent on the protocol
link. Debug or other non-protocol output SHALL NOT be sent on it.

### 2.4 Line errors

- If a received line exceeds the maximum length, the firmware SHALL discard
  all bytes up to and including the next terminator. It SHALL then send
  `ERROR code=LINE_TOO_LONG` once.
- If a received line contains a byte outside 0x20 to 0x7E, or a UART framing,
  noise or overrun error or a receive-buffer overflow occurs while it is being
  received, the firmware SHALL discard all bytes up to and including the next
  terminator. It SHALL then send `ERROR code=BAD_FRAME` once.
- If a line both exceeds the maximum length and contains such an error, the
  firmware SHALL send `ERROR code=LINE_TOO_LONG` only (see section 5.2.2).
- If the host receives a line from the firmware that violates sections 2.2 or
  2.3, it SHALL treat it as a protocol failure, except during startup (see
  section 4.1).

> **Note (informative):** A CR that is not immediately followed by LF is a
> byte outside 0x20 to 0x7E. An error that occurs between two lines belongs to
> the next line, which is then reported as `BAD_FRAME` when its terminator is
> received.

## 3. Versioning and compatibility

### 3.1 Version identifiers

This document uses three independent version identifiers:

| Identifier | Location | Purpose |
|:--|:--|:--|
| Document revision | `\version` in the file header | Tracks editorial and normative changes to this document. |
| Protocol version | `proto` field of the readiness banner | Identifies the wire protocol implemented by the firmware. |
| Firmware version | `fw` field of the readiness banner | Identifies the firmware image. |

This revision of the document specifies protocol version **1.0**. A document
revision MAY change without changing the protocol version, for example to
clarify wording.

The firmware version SHALL NOT be used to determine protocol compatibility.
The commands supported by a firmware image are reported by the `CAPS`
command (see section 6.3).

### 3.2 Protocol version format

The protocol version SHALL have the form `<major>.<minor>`, where `<major>`
and `<minor>` are unsigned decimal integers without leading zeros.

The major version SHALL be incremented for any change that is not backward
compatible, including:

- removing a command, argument, or result field;
- changing the syntax or meaning of an existing record, field, or value;
- adding a new record type.

The minor version SHALL be incremented, and the major version kept, for any
backward-compatible addition, limited to:

- a new command;
- a new optional argument for an existing command;
- a new result field;
- a new error code.

### 3.3 Compatibility rules

For minor additions to remain compatible, both endpoints SHALL follow these
rules:

- The host SHALL ignore result fields that it does not recognize.
- The host SHALL treat an error code that it does not recognize as a
  firmware-reported functional error.
- The firmware SHALL reject an argument that it does not recognize with
  `status=ERR code=INVALID_ARGUMENT`.

### 3.4 Host compatibility check

After receiving the readiness banner and before sending any request, the host
SHALL check the `proto` field:

- If the field is missing or malformed, the host SHALL treat the session as a
  startup failure.
- If the major version differs from the major version supported by the host,
  the host SHALL NOT send any request and SHALL report the session as
  `INCOMPATIBLE_PROTOCOL`.
- If the major versions match, the host SHALL proceed, regardless of the minor
  version.

`HELLO` and `CAPS` are mandatory in every firmware and MAY be sent without
prior capability discovery. Before sending any other command in a session,
the host SHALL obtain the complete list of supported commands with `CAPS`
(see section 6.3).

The host SHALL NOT send a command that is not in the list returned by
`CAPS`. A test case that requires a command that is not in this list SHALL
be reported as `UNSUPPORTED_COMMAND`.

`INCOMPATIBLE_PROTOCOL` and `UNSUPPORTED_COMMAND` are host-side report
outcomes. They are never sent on the protocol link.

## 4. Session establishment and reset reporting

### 4.1 Readiness banner

After reset-cause capture (see section 4.2) and firmware initialization, the
firmware SHALL send exactly one readiness banner per boot:

```text
READY name=hil-bench fw=1.0.0 proto=1.0 build=3f2a9c1 reset=IWDG reset_flags=0x24000000
```

The banner SHALL contain the following fields, in this order:

| Field | Definition | Format | Max. value length |
|:--|:--|:--|:--|
| `name` | Firmware identifier. | Lowercase letters, digits, and `-`. | 16 |
| `fw` | Firmware image version. | `<major>.<minor>.<patch>`, unsigned decimal integers. | 16 |
| `proto` | Protocol version (see section 3.2). | `<major>.<minor>` | 7 |
| `build` | Abbreviated source revision. | 7 to 12 lowercase hexadecimal characters, optionally followed by `-dirty`; or `unknown`. | 18 |
| `reset` | Decoded reset cause (see section 4.2). | One token from the table in section 4.2, or unknown | 7 |
| `reset_flags` | Raw `RCC_CSR` reset flags, bits 31:25, masked with `0xFE000000`. | `0x` followed by 8 uppercase hexadecimal digits. | 10 |

With these limits, the banner does not exceed 123 bytes, within the
maximum line length of section 2.2.

The host SHALL ignore banner fields that it does not recognize. A valid
readiness banner is a `READY` record that conforms to section 2.3 and
contains all the fields above with values in the specified formats.

Before releasing the board from reset, the host SHALL flush its serial
receive buffer. It SHALL then wait for a valid readiness banner within the
startup timeout (see section 8.1). While waiting, the host SHALL ignore any
line that is not a valid readiness banner. If no valid readiness banner is
received within the startup timeout, the host SHALL report
`STARTUP_FAILURE`.

The firmware SHALL discard any byte received before it has sent the
readiness banner.

### 4.2 Reset-cause capture

At the earliest firmware startup point, before clearing reset flags or running
application initialization, the firmware SHALL read `RCC_CSR` and save the reset
cause bits. It SHALL then clear the flags by setting `RMVF` after saving the
snapshot. The firmware SHALL report the masked snapshot in `reset_flags`.

| RCC_CSR flag | `reset` token | Meaning |
|:--|:--|:--|
| `LPWRRSTF` | `LPWR` | Low-power reset |
| `WWDGRSTF` | `WWDG` | Window watchdog reset |
| `IWDGRSTF` | `IWDG` | Independent watchdog reset |
| `SFTRSTF` | `SW` | Software reset |
| `PINRSTF` | `PIN` | Reset through NRST pin |
| `PORRSTF` | `POR` | POR/PDR reset |
| `BORRSTF` | `BOR` | Brownout reset  |

`reset` SHALL contain exactly one token, selected as the first flag set in
the following priority order:

`LPWR`, `WWDG`, `IWDG`, `SW`, `POR`, `BOR`, `PIN`.

If no recognized flag is set, `reset` SHALL be `unknown`. `reset_flags`
SHALL always contain the raw masked flags, so that all set flags remain
available to the host.

> **Note (informative):** Internal resets (watchdog, software, low-power)
> drive the NRST pin, so `PINRSTF` is normally set together with the flag of
> the actual cause. A POR/PDR also sets `BORRSTF`. The priority order reports
> the actual cause in these cases. RCC reset flags identify the reset
> mechanism; they do not identify a preceding HardFault.

### 4.3 Unexpected reset during a session

The host SHALL accept a `READY` record only while in the startup or explicit
recovery state. Receipt of any `READY` record in the active session SHALL be
reported as `UNEXPECTED_RESET`. The host MUST fail the current
transaction, if any, fail the session, record the banner's reset fields, and
MUST NOT treat the banner as a new session. A new session requires an explicit
host reset and a new startup phase.

## 5. Requests and responses

### 5.1 Request
The host SHALL send each request as a single line with this format:

```text
CMD id=<id> command=<command> [<key>=<value> ...]
```

- `CMD` SHALL be the first token, followed by `id` and then `command`, in that
  order. Command arguments, if any, SHALL follow `command`.
- `<id>` SHALL be an unsigned decimal integer in the range 1 to 65535, written
  without a sign or leading zeros.
- `<command>` SHALL be `HELLO`, `CAPS`, or a command name returned by
  `CAPS` in the current session (see section 6.3).
- `id` and `command` are reserved keys and SHALL NOT be used as argument keys.
  Each argument key SHALL appear at most once in a request.

The host SHALL NOT send a new request until it has received the `END` record
of the previous request, or until that request has timed out (see section 8.1).

Within a session, the host SHALL use ID 1 for the first request and SHALL
increment the ID by exactly 1 for each subsequent request. An ID SHALL NOT be
reused within a session. After sending the request with ID 65535, the host
SHALL reset the board and wait for a new readiness banner before sending
another request. The next session starts again at ID 1.

### 5.2 Response

#### 5.2.1 Correlated response

For each request whose `id` field is present and valid (see section 5.1), the
firmware SHALL send exactly one `RESULT` record followed by exactly one `END`
record. Both records SHALL carry the request ID unchanged.

On success:

```text
RESULT id=<id> status=OK [<key>=<value> ...]
END id=<id>
```

On failure:

```text
RESULT id=<id> status=ERR code=<error-code> [<key>=<value> ...]
END id=<id>
```

- `id` and `status` SHALL be the first two fields of `RESULT`, in that order.
  When `status=ERR`, `code` SHALL be the third field. When `status=OK`, the
  `code` field SHALL NOT be present.
- `status` SHALL be either `OK` or `ERR`.
- `id`, `status`, and `code` are reserved keys and SHALL NOT be used as result
  field keys. Each result field key SHALL appear at most once.
- `END` SHALL contain only the `id` field.
- A request with a valid ID whose other fields are invalid (for example, a
  missing `command`, a duplicate key, or an argument token without =) SHALL receive a
  correlated `RESULT` with `status=ERR code=BAD_REQUEST`.

A `READY` record received while a transaction is outstanding SHALL be
handled as defined in section 4.3, not as a protocol failure.

The firmware SHALL NOT send any other record for a transaction after its
`END` record.

#### 5.2.2 Uncorrelated error

The firmware SHALL send an uncorrelated `ERROR` record, without `RESULT` or
`END`, in these cases:

| Condition | Record |
|:--|:--|
| The line exceeds the maximum length (see section 2.2). | `ERROR code=LINE_TOO_LONG` |
| The line does not start with `CMD`, or its `id` field is missing, not a decimal integer, or outside 1 to 65535. | `ERROR code=BAD_FRAME` |

The length check SHALL be applied before any other check. The firmware SHALL
discard the offending line and SHALL NOT execute any command from it.

#### 5.2.3 Host validation

The host SHALL consider a transaction complete only after it has received a
valid `RESULT` and then a valid `END`, both carrying the ID of the outstanding
request, before the response timeout (see section 8.1).

The host SHALL classify the transaction as a protocol failure if any of the
following occurs while it is outstanding:

- a record with an ID other than the outstanding ID;
- a record that does not conform to this section;
- a second `RESULT`, or an `END` received before `RESULT`;
- an `ERROR` record;
- the response timeout expiring before `END` is received.

On a protocol failure, the host SHALL apply the recovery procedure of
section 8.3.

## 6. Command definition

### 6.1 Command specification rules

Each command SHALL be specified in this section with the following
information before either endpoint implements it:

| Item | Content |
|:--|:--|
| Arguments | Key, value format, and range of each argument; whether it is required or optional. |
| Success result | Key and value format of each result field. |
| Error codes | The `code` values that the command can return, with their meaning for this command. |
| Timeout | Maximum time from the end of the request transmission to the reception of `END`. |
| Side effects | Hardware or firmware state changed by the command, if any. |

A complete response line SHALL NOT exceed the maximum line length defined in
section 2.2. The host SHALL NOT rely on the order of result fields after the
reserved fields defined in section 5.2.1.

A command name SHALL consist of 1 to 32 uppercase letters, digits, and
underscores, and SHALL start with a letter.

### 6.2 `HELLO`

`HELLO` checks the complete command path: firmware reception, parsing,
dispatch, and response. Every conforming firmware SHALL implement `HELLO` and SHALL include it in the
list returned by `CAPS`.

| Item | Specification |
|:--|:--|
| Arguments | None. |
| Success result | `name=<name> proto=<proto> fw=<fw> build=<build>` |
| Error codes | `INVALID_ARGUMENT` if any argument is present. `BAD_REQUEST` as defined in section 5.2.1. |
| Timeout | 2 s. |
| Side effects | None. `HELLO` MAY be sent any number of times in a session. |

Result fields:

| Field | Value |
|:--|:--|
| `name` | Firmware name. For the HIL bench firmware: `hil-bench`. |
| `proto` | Protocol version implemented by the firmware (see section 3.2). |
| `fw` | Firmware version. |
| `build` | Abbreviated source revision, in the format defined in section 4.1. |

The values of `name`, `proto`, `fw`, and `build` SHALL be identical to the
corresponding fields of the readiness banner sent at the start of the
session. The host SHALL treat any difference as a protocol failure.

If the host configuration provides the expected build identifier, the host
SHALL compare it with `build`. A different value, including `unknown`, SHALL
be reported as `BUILD_MISMATCH` unless the host configuration explicitly
accepts it. `BUILD_MISMATCH` is a host-side report outcome and is never sent
on the protocol link.

Example (informative):

```text
CMD id=1 command=HELLO
RESULT id=1 status=OK name=hil-bench proto=1.0 fw=1.0.0 build=3f2a9c1
END id=1
```

### 6.3 `CAPS`

`CAPS` returns the names of the commands supported by the firmware. Because a
response line is limited in length, the list is returned in pages. Every
conforming firmware SHALL implement `CAPS`.

| Item | Specification |
|:--|:--|
| Arguments | `start` (optional): zero-based index of the first name to return, unsigned decimal integer. Default: 0. |
| Success result | `total=<n> start=<i> names=<name>[,<name>...] [next=<j>]` |
| Error codes | `INVALID_ARGUMENT` if `start` is malformed or not lower than `total`, or if any other argument is present. `BAD_REQUEST` as defined in section 5.2.1. |
| Timeout | 2 s. |
| Side effects | None. |

Result fields:

| Field | Value |
|:--|:--|
| `total` | Total number of supported commands, from 2 to 255. |
| `start` | Index of the first name in `names`, equal to the requested `start`. |
| `names` | One or more command names, separated by commas, starting at index `start`. |
| `next` | Index of the next name to request. Present only if names remain after this page. |

Firmware requirements:

- The list SHALL include `HELLO` and `CAPS`, and SHALL NOT contain
  duplicates.
- The order of the list SHALL be fixed for a given firmware image.
- Each page SHALL contain as many complete names as fit within the maximum
  line length of section 2.2, and at least one name.

Host requirements:

- The host SHALL request pages starting with `start=0`, and then with
  `start` set to the received `next`, until a response has no `next` field.
- The host SHALL treat the following as a protocol failure: a `total` that
  changes between pages, a `start` that differs from the request, a
  duplicate name, a final count of names different from `total`, or a list
  without `HELLO` or `CAPS`.

Example (informative), with a single page:

```text
CMD id=2 command=CAPS
RESULT id=2 status=OK total=3 start=0 names=HELLO,CAPS,QSPI_READ_ID
END id=2
```

Example (informative), with two pages:

```text
CMD id=2 command=CAPS
RESULT id=2 status=OK total=12 start=0 names=HELLO,CAPS,QSPI_READ_ID,SDRAM_TEST next=4
END id=2
CMD id=3 command=CAPS start=4
RESULT id=3 status=OK total=12 start=4 names=...
END id=3
```

### 6.4 Future commands (informative)

The following example shows how a future peripheral command would use the
same envelope. `QSPI_READ_ID` is not part of protocol version 1.0 and SHALL
NOT be implemented until it is specified according to section 6.1.

```text
CMD id=2 command=CAPS
RESULT id=2 status=OK total=2 start=0 names=HELLO,CAPS
END id=2
```


## 7. Error codes

Error codes fall into three categories:

- **Response codes** are sent by the firmware in a correlated `RESULT` record
  (section 7.1).
- **Frame codes** are sent by the firmware in an uncorrelated `ERROR` record
  (section 7.2).
- **Host outcomes** are reported by the host in its test report and are never
  sent on the protocol link (section 7.3).

Response and frame codes SHALL consist of uppercase letters, digits, and
underscores, and SHALL start with a letter.

### 7.1 Response codes

When the firmware cannot complete a request that has a valid ID, it SHALL
send `RESULT id=<id> status=ERR code=<code>` followed by `END id=<id>`, as
defined in section 5.2.1. The `RESULT` record MAY include a `detail=<value>`
field with diagnostic information. The host SHALL NOT rely on the content of
`detail`.

| Code | Condition | Command executed |
|:--|:--|:--|
| `BAD_REQUEST` | The ID is valid, but the request is otherwise malformed: `command` is missing, a key is duplicated, or a reserved key is used as an argument, or an argument token has no = | No |
| `UNKNOWN_COMMAND` | The command name is not implemented by the firmware. | No |
| `INVALID_ARGUMENT` | A required argument is missing, an argument is not recognized, or an argument value is malformed or out of range. | No |
| `BUSY` | The firmware state does not allow the command to start. | No |
| `DEVICE_TIMEOUT` | A peripheral or external device did not respond within the firmware's internal time limit. | Possibly, partially |
| `DEVICE_ERROR` | A peripheral or external device reported an error. | Possibly, partially |
| `INTERNAL` | An unexpected firmware failure occurred, for example a failed internal check. | Possibly, partially |

When the "Command executed" column is "No", the firmware SHALL NOT have
changed any hardware or firmware state while processing the request, and the
host MAY send the request again with a new ID. Otherwise, the host SHALL NOT
assume anything about the state of the hardware.

The firmware SHALL NOT return `UNKNOWN_COMMAND` for a command included in the
list returned by `CAPS`. The host SHALL treat such a response as a protocol
failure.



### 7.2 Frame codes

The firmware sends these codes in an uncorrelated record
`ERROR code=<code>`, without `RESULT` or `END`, as defined in sections 2.4 and
5.2.2.

| Code | Condition |
|:--|:--|
| `LINE_TOO_LONG` | A received line exceeds the maximum line length. |
| `BAD_FRAME` | A received line contains an invalid byte, was affected by a UART framing, noise or overrun error or by a receive-buffer overflow, does not start with `CMD`, or has a missing or invalid `id`. |

The host SHALL treat any `ERROR` record as a protocol failure.

### 7.3 Host outcomes

The host SHALL classify each session or test case with one of the following
outcomes:

| Outcome | Condition |
|:--|:--|
| `PASS` | All expected transactions completed with the expected results. |
| `PROGRAMMING_FAILURE` | Building, programming, or resetting the board failed. |
| `STARTUP_FAILURE` | No valid readiness banner was received before the startup timeout. |
| `INCOMPATIBLE_PROTOCOL` | The banner's protocol major version differs from the one supported by the host (section 3.4). |
| `BUILD_MISMATCH` | The `build` value differs from the expected build identifier (section 6.2). |
| `UNSUPPORTED_COMMAND` | A required command is not in the list returned by `CAPS` (sections 3.4 and 6.3). |
| `UNEXPECTED_RESET` | A readiness banner was received during an active session. |
| `PROTOCOL_FAILURE` | A record violated this specification, an `ERROR` record was received, or a response timeout expired. |
| `FUNCTIONAL_ERROR` | The firmware returned `status=ERR`, or `status=OK` with result values different from those expected by the test case. |



## 8. Timeouts and recovery

### 8.1 Timeout values

The host SHALL measure the following timeouts:

| Timeout | Starts when | Ends when | Value |
|:--|:--|:--|:--|
| Startup timeout | The host releases the board from reset. | A valid readiness banner is received. | 5 s |
| Response timeout | The host has sent the last byte of the request terminator. | The matching `END` record is received. | Specified per command in section 6 |

The host configuration MAY override a timeout value for a test case. Any
overridden value SHALL be recorded in the test report.

### 8.2 Firmware timing requirements

The firmware SHALL send the `END` record of each transaction within the
response timeout of the command, including when the command fails.

Every wait performed by the firmware on hardware, such as polling a
peripheral flag or waiting for an external device, SHALL be bounded by an
internal time limit. This limit SHALL be short enough that the firmware can
send `status=ERR code=DEVICE_TIMEOUT` and `END` before the response timeout
expires.

### 8.3 Recovery

The host SHALL apply the following recovery procedure after any of these
events: a response timeout, a `PROTOCOL_FAILURE`, or an `UNEXPECTED_RESET`
(see section 7.3).

1. Record the outcome of the current test case.
2. Stop sending requests and ignore any record still received for the
   current session.
3. Flush the serial receive buffer.
4. Reset the board.
5. Wait for a valid readiness banner within the startup timeout. The new
   session starts with ID 1 (see section 5.1).

If no valid banner is received in step 5, the host SHALL report
`STARTUP_FAILURE` and SHALL stop the test run.

The host SHALL NOT automatically resend a request that timed out, in either
the same session or a new one, because the command may already have changed
the hardware state. The test case that contained the request SHALL be
reported as failed. After a successful recovery, the host MAY continue with
the next test case.

### 8.4 Reporting

The test report SHALL classify each session or test case using the outcomes
defined in section 7.3. For each failure, it SHOULD include the last request
sent and the records received for it.

## 9. References


### 9.1 Normative references

The following documents are required to implement this specification. Where
a reference is dated, only the cited edition applies.

| Ref. | Document | Used for |
|:--|:--|:--|
| [N1] | IETF, *Key words for use in RFCs to Indicate Requirement Levels*, RFC 2119 (BCP 14), March 1997. <https://www.rfc-editor.org/rfc/rfc2119> | Meaning of SHALL, SHOULD, MAY (section 1.1). |
| [N2] | IETF, *Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words*, RFC 8174 (BCP 14), May 2017. <https://www.rfc-editor.org/rfc/rfc8174> | Key words apply only in uppercase (section 1.1). |
| [N3] | ANSI, *Coded Character Set – 7-Bit American Standard Code for Information Interchange*, ANSI X3.4-1986 (equivalent: ISO/IEC 646, International Reference Version). | Character set and byte values of records (section 2.2). |
| [N4] | STMicroelectronics, *RM0385 Reference manual – STM32F75xxx and STM32F74xxx advanced Arm®-based 32-bit MCUs*, Rev. <x>. <https://www.st.com/resource/en/reference_manual/rm0385-stm32f75xxx-and-stm32f74xxx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf> | USART framing and error flags (FE, ORE) (section 2.4); reset flags of `RCC_CSR` and clearing with `RMVF` (banner `reset` field). |

### 9.2 Informative references

The following documents provide background or design examples. They are not
required to implement this specification.

| Ref. | Document | Used for |
|:--|:--|:--|
| [I1] | IETF, *Augmented BNF for Syntax Specifications: ABNF*, RFC 5234 (STD 68), January 2008. <https://www.rfc-editor.org/rfc/rfc5234> | Recommended notation for a formal grammar of records. |
| [I2] | T. Preston-Werner, *Semantic Versioning 2.0.0*. <https://semver.org/spec/v2.0.0.html> | Model for the `major.minor` protocol version (section 3) and the `fw` version. |
| [I3] | USB Implementers Forum, *Class Definitions for Communication Devices*, Revision 1.2, and *PSTN Devices* subclass, Revision 1.2. <https://www.usb.org/document-library/class-definitions-communication-devices-12> | USB CDC-ACM class used by the ST-LINK virtual COM port. |
| [I4] | JEDEC, *JEP106 – Standard Manufacturer's Identification Code*, latest revision. <https://www.jedec.org/standards-documents/docs/jep-106ab> | Manufacturer byte of the JEDEC identifier (section 6.4 example). |
| [I5] | JEDEC, *JESD216 – Serial Flash Discoverable Parameters (SFDP)*, latest revision. <https://www.jedec.org/standards-documents/docs/jesd216b> | Identification of serial flash devices for future QSPI commands. |
| [I6] | ISO/IEC/IEEE 29119-3, *Software and systems engineering – Software testing – Part 3: Test documentation*. | Structure of test reports (section 8.4). |
| [I7] | STMicroelectronics, *STM32F7508-DK* product page and user manual. <https://www.st.com/en/evaluation-tools/stm32f7508-dk.html> | Board wiring of USART1 to the ST-LINK virtual COM port. |

### 9.3 Related open-source projects (informative)

These projects were consulted as design examples on <date>. They are not
endorsed, and the protocol defined here is not compatible with them.

| Project | Relevance |
|:--|:--|
| [STM32 OpenHTF demo](https://github.com/bbmegareve/stm32_openhtf_demo) | STM32 UART command interface driven and checked by host tests, with ST-LINK programming. |
| [PHiLIP](https://github.com/riot-appstore/PHiLIP) | Serial command interface with a Python API and explicit operation results. Its firmware acts as a test fixture rather than as the device under test. |
| [pytest-embedded](https://github.com/espressif/pytest-embedded) | pytest plugins and serial services for embedded targets. |
| [GM65 scanner CDC protocol](https://github.com/Amperstrand/gm65-scanner) | Documented binary framing, command table, and sequence diagram. Used as a framing reference only; this protocol uses text records instead. |
