#!/usr/bin/env python3
"""Send raw test bytes to the HIL UART and verify the firmware echo.

The firmware must be built in a temporary raw-echo mode for this check.
This diagnostic is separate from the line-based HIL protocol.
Requires pyserial: python -m pip install pyserial

Version: 1.2
Date: 16/10/2026
Author: Z. BEN-AKKA
History:
  1.0  16/10/2026  Initial host-side UART echo check.
  1.1  16/10/2026  Add T1 nominal reception test: 100 lines of 128 characters.
  1.2  16/10/2026  Translate T1 test comments to English.
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
# Method: Send 100 lines of 128 characters, each terminated by CRLF.
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
    payload = b"".join(lines)

    link.timeout = timeout
    link.reset_input_buffer()
    written = link.write(payload)
    link.flush()
    if written != len(payload):
        print(f"FAIL T1: wrote {written}/{len(payload)} bytes", file=sys.stderr)
        return False

    echoed = link.read(len(payload))
    if echoed != payload:
        limit = min(len(echoed), len(payload))
        mismatch = next(
            (index for index in range(limit) if echoed[index] != payload[index]),
            limit,
        )
        print(
            f"FAIL T1: echo differs at byte {mismatch}; "
            f"received {len(echoed)}/{len(payload)} bytes",
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
            return 0 if test_t1_nominal_receive(link, args.timeout) else 1
    except (serial.SerialException, OSError) as error:
        print(f"Serial error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
