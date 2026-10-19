#!/usr/bin/env python3
"""Send raw test bytes to the HIL UART and verify the firmware echo.

The firmware must be built in a temporary raw-echo mode for this check.
This diagnostic is separate from the line-based HIL protocol.
Requires pyserial: python -m pip install pyserial

Version: 1.7
Date: 16/10/2026
Author: Z. BEN-AKKA
History:
  1.0  16/10/2026  Initial host-side UART echo check.
  1.1  16/10/2026  Add T1 nominal reception test: 100 lines of 128 characters.
  1.2  16/10/2026  Translate T1 test comments to English.
  1.3  16/10/2026  Pace T1 one line at a time to stay within RX queue capacity.
  1.4  16/10/2026  Add T2 burst reception test with 1,000 bytes.
  1.5  16/10/2026  Add T3 framing-error recovery test.
  1.6  16/10/2026  Temporarily run T3 only.
  1.7  16/10/2026  Generate a framing error with a baud mismatch instead of BREAK.
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial is required: python -m pip install pyserial", file=sys.stderr)
    raise SystemExit(2)


# ---------------------------------------------------------------------------
# Test T1: Nominal reception
# Method: Send 100 lines of 128 characters with CRLF, one line at a time.
# Expected result: Byte-for-byte identical echo with no extra bytes.
# ---------------------------------------------------------------------------
def test_t1_nominal_receive(link: serial.Serial, timeout: float) -> bool:
    line_count = 100
    chars_per_line = 128
    lines = []
    for line_index in range(line_count):
        chars = bytes(
            0x20 + ((line_index * 17 + column) % 95)
            for column in range(chars_per_line)
        )
        lines.append(chars + b"\r\n")

    link.timeout = timeout
    link.reset_input_buffer()
    for line_index, line in enumerate(lines):
        written = link.write(line)
        link.flush()
        if written != len(line):
            print(
                f"FAIL T1: line {line_index + 1}: wrote {written}/{len(line)} bytes",
                file=sys.stderr,
            )
            return False

        echoed = link.read(len(line))
        if echoed != line:
            limit = min(len(echoed), len(line))
            mismatch = next(
                (index for index in range(limit) if echoed[index] != line[index]),
                limit,
            )
            print(
                f"FAIL T1: line {line_index + 1} differs at byte {mismatch}; "
                f"received {len(echoed)}/{len(line)} bytes",
                file=sys.stderr,
            )
            return False

    extra = link.read(1)
    if extra:
        print(f"FAIL T1: unexpected extra byte {extra.hex(' ')}", file=sys.stderr)
        return False

    print(
        f"PASS T1: {line_count} lines x {chars_per_line} characters "
        "echoed identically; no extra byte received"
    )
    return True


# ---------------------------------------------------------------------------
# Test T2: Burst reception
# Method: Send 1,000 binary bytes in one write while firmware reads continuously.
# Expected result: No byte loss and no extra output bytes.
# ---------------------------------------------------------------------------
def test_t2_burst_receive(link: serial.Serial, timeout: float) -> bool:
    payload = bytes(index & 0xFF for index in range(1000))

    link.timeout = timeout
    link.reset_input_buffer()
    written = link.write(payload)
    link.flush()
    if written != len(payload):
        print(f"FAIL T2: wrote {written}/{len(payload)} bytes", file=sys.stderr)
        return False

    echoed = link.read(len(payload))
    if echoed != payload:
        limit = min(len(echoed), len(payload))
        mismatch = next(
            (index for index in range(limit) if echoed[index] != payload[index]),
            limit,
        )
        print(
            f"FAIL T2: echo differs at byte {mismatch}; "
            f"received {len(echoed)}/{len(payload)} bytes",
            file=sys.stderr,
        )
        return False

    extra = link.read(1)
    if extra:
        print(f"FAIL T2: unexpected extra byte {extra.hex(' ')}", file=sys.stderr)
        return False

    print("PASS T2: 1,000-byte burst echoed identically; no extra byte received")
    return True


# ---------------------------------------------------------------------------
# Test T3: Framing error
# Method: Send one byte at 9,600 baud to the 115,200-baud firmware, then restore
#         115,200 baud and send one valid line.
# Expected result: [FE] marker followed by the exact echo of the valid line.
# ---------------------------------------------------------------------------
def test_t3_framing_error(link: serial.Serial, timeout: float) -> bool:
    line = b"RECOVERY_OK\r\n"
    expected = b"[FE]\r\n" + line
    normal_baud = link.baudrate

    link.timeout = timeout
    link.reset_input_buffer()
    link.baudrate = 9600
    malformed = b"\x00"
    written = link.write(malformed)
    link.flush()
    link.baudrate = normal_baud
    if written != len(malformed):
        print(f"FAIL T3: wrote {written}/{len(malformed)} malformed bytes", file=sys.stderr)
        return False

    written = link.write(line)
    link.flush()
    if written != len(line):
        print(f"FAIL T3: wrote {written}/{len(line)} bytes", file=sys.stderr)
        return False

    received = link.read(len(expected))
    if received != expected:
        limit = min(len(received), len(expected))
        mismatch = next(
            (index for index in range(limit) if received[index] != expected[index]),
            limit,
        )
        print(
            f"FAIL T3: expected [FE] then valid-line echo; mismatch at byte {mismatch}, "
            f"received {len(received)}/{len(expected)} bytes "
            f"({received.hex(' ')})",
            file=sys.stderr,
        )
        return False

    extra = link.read(1)
    if extra:
        print(f"FAIL T3: unexpected extra byte {extra.hex(' ')}", file=sys.stderr)
        return False

    print("PASS T3: [FE] reported; following line echoed identically")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="serial port, for example /dev/ttyACM0 or COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=2.0, help="reply timeout in seconds")
    args = parser.parse_args()

    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=args.timeout,
            write_timeout=args.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        ) as link:
            time.sleep(0.1)  # Allow the serial adapter to settle after opening.
            # T1 and T2 are temporarily disabled while T3 is investigated.
            return 0 if test_t3_framing_error(link, args.timeout) else 1
    except (serial.SerialException, OSError) as error:
        print(f"Serial error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
