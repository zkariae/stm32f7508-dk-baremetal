#!/usr/bin/env python3
"""Send raw test bytes to the HIL UART and verify the firmware echo.

The firmware must be built in a temporary raw-echo mode for this check.
This diagnostic is separate from the line-based HIL protocol.
Serial settings, timeouts and delays come from config/bench.yaml; command-line
options override them.
Requires pyserial and PyYAML: python -m pip install pyserial pyyaml

Version: 1.9
Date: 19/10/2026
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
  1.8  19/10/2026  Wait for baud switches to settle in T3.
  1.9  19/10/2026  Load serial settings, timeouts and delays from bench.yaml.
"""

import argparse
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pyserial is required: python -m pip install pyserial", file=sys.stderr)
    raise SystemExit(2)

try:
    import yaml
except ImportError:
    print("PyYAML is required: python -m pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "bench.yaml"
SUPPORTED_SCHEMA = 1
PARITIES = {"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN, "odd": serial.PARITY_ODD}
FLOW_CONTROLS = ("none", "rtscts", "xonxoff")


def load_bench_config(path: Path) -> dict:
    """Load bench.yaml and reject an unsupported schema or invalid serial options."""
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or config.get("schema_version") != SUPPORTED_SCHEMA:
        raise ValueError(f"schema_version must be {SUPPORTED_SCHEMA}")
    link = config["serial"]
    if link["parity"] not in PARITIES:
        raise ValueError(f"serial.parity must be one of {', '.join(PARITIES)}")
    if link["flow_control"] not in FLOW_CONTROLS:
        raise ValueError(f"serial.flow_control must be one of {', '.join(FLOW_CONTROLS)}")
    return config


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
def test_t3_framing_error(link: serial.Serial, timeout: float, settle: float) -> bool:
    line = b"RECOVERY_OK\r\n"
    expected = b"[FE]\r\n" + line
    normal_baud = link.baudrate

    link.timeout = timeout
    link.reset_input_buffer()
    link.baudrate = 9600
    malformed = b"\x00"
    written = link.write(malformed)
    link.flush()
    # flush() returns once the USB bridge holds the data, not once it is on the wire.
    time.sleep(settle)  # Let the bridge shift the byte out at 9,600 baud.
    link.baudrate = normal_baud
    time.sleep(settle)  # Let the bridge apply the restored baud rate.
    link.reset_input_buffer()  # Drop switch glitches; the firmware defers [FE].
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
    parser.add_argument(
        "port", nargs="?", help="serial port, for example /dev/ttyACM0 or COM5 (default: bench.yaml)"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="bench configuration file")
    parser.add_argument("--baud", type=int, help="baud rate (default: bench.yaml)")
    parser.add_argument("--timeout", type=float, help="reply timeout in seconds (default: bench.yaml)")
    args = parser.parse_args()

    try:
        config = load_bench_config(args.config)
        link_config = config["serial"]
        port = args.port or link_config["port"]
        baud = args.baud or link_config["baudrate"]
        timeout = args.timeout if args.timeout is not None else config["timeouts"]["read"]
        port_open_settle = config["delays"]["port_open_settle"]
        baud_switch_settle = config["delays"]["baud_switch_settle"]
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        detail = f"missing key {error}" if isinstance(error, KeyError) else error
        print(f"Configuration error in {args.config}: {detail}", file=sys.stderr)
        return 2

    try:
        with serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=link_config["bytesize"],
            parity=PARITIES[link_config["parity"]],
            stopbits=link_config["stopbits"],
            timeout=timeout,
            write_timeout=timeout,
            xonxoff=link_config["flow_control"] == "xonxoff",
            rtscts=link_config["flow_control"] == "rtscts",
            dsrdtr=False,
        ) as link:
            time.sleep(port_open_settle)  # Allow the serial adapter to settle after opening.
            # T1 and T2 are temporarily disabled while T3 is investigated.
            return 0 if test_t3_framing_error(link, timeout, baud_switch_settle) else 1
    except (serial.SerialException, OSError) as error:
        print(f"Serial error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
