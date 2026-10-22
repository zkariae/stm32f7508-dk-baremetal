#!/usr/bin/env python3
"""Send raw test bytes to the HIL UART and verify the firmware echo.

The firmware must be built in a temporary raw-echo mode for this check.
This diagnostic is separate from the line-based HIL protocol.
Serial settings, timeouts and delays come from config/bench.yaml; command-line
options override them. Test parameters and expected results come from
plans/uart_rx.yaml.
Requires pyserial and PyYAML: python -m pip install pyserial pyyaml

Version: 1.16
Date: 22/10/2026
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
  1.10 19/10/2026  Load T1-T4 from uart_rx.yaml, add T4 wrong baud, run all tests.
  1.11 19/10/2026  Show only the description in --help.
  1.12 21/10/2026  Add T5 hardware overrun test.
  1.13 21/10/2026  Add T6 RX buffer overflow test.
  1.14 21/10/2026  Add T7 no interrupt storm test; enforce plan "after" order.
  1.15 21/10/2026  Add T8 RX flush test.
  1.16 22/10/2026  Rename from uart_tx_check.py: the script runs the UART RX plan.
"""

import argparse
import sys
import time
from dataclasses import dataclass
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

HIL_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = HIL_DIR / "config" / "bench.yaml"
DEFAULT_PLAN = HIL_DIR / "plans" / "uart_rx.yaml"
SUPPORTED_SCHEMA = 1
PARITIES = {"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN, "odd": serial.PARITY_ODD}
FLOW_CONTROLS = ("none", "rtscts", "xonxoff")
MAX_MARKER_LINES = 16  # Bound on marker lines read before the recovery line.


class PlanError(Exception):
    """Invalid or incomplete test plan entry."""


@dataclass
class Bench:
    """Bench values shared by all tests."""

    timeout: float
    baud_switch_settle: float


def load_yaml(path: Path) -> dict:
    """Load a YAML file and reject an unsupported schema."""
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict) or data.get("schema_version") != SUPPORTED_SCHEMA:
        raise ValueError(f"schema_version must be {SUPPORTED_SCHEMA}")
    return data


def load_bench_config(path: Path) -> dict:
    """Load bench.yaml and reject invalid serial options."""
    config = load_yaml(path)
    link = config["serial"]
    if link["parity"] not in PARITIES:
        raise ValueError(f"serial.parity must be one of {', '.join(PARITIES)}")
    if link["flow_control"] not in FLOW_CONTROLS:
        raise ValueError(f"serial.flow_control must be one of {', '.join(FLOW_CONTROLS)}")
    return config


def load_test_plan(path: Path) -> list:
    """Load uart_rx.yaml and reject unknown or duplicate test IDs."""
    tests = load_yaml(path)["tests"]
    seen = set()
    for test in tests:
        test_id = test["id"]
        if test_id not in TESTS:
            raise ValueError(f"unknown test id {test_id}; known: {', '.join(TESTS)}")
        if test_id in seen:
            raise ValueError(f"duplicate test id {test_id}")
        seen.add(test_id)
    return tests


def first_mismatch(received: bytes, expected: bytes) -> int:
    limit = min(len(received), len(expected))
    return next((index for index in range(limit) if received[index] != expected[index]), limit)


def check_no_extra(link: serial.Serial, test_id: str, expected: dict) -> bool:
    if expected.get("extra_bytes", 0) != 0:
        raise PlanError(f"{test_id}: only extra_bytes: 0 is supported")
    extra = link.read(1)
    if extra:
        print(f"FAIL {test_id}: unexpected extra byte {extra.hex(' ')}", file=sys.stderr)
        return False
    return True


def send_at_wrong_baud(link: serial.Serial, payload: bytes, wrong_baud: int, settle: float) -> bool:
    """Send payload at wrong_baud, then restore the bench baud rate and drop input."""
    normal_baud = link.baudrate
    link.reset_input_buffer()
    link.baudrate = wrong_baud
    written = link.write(payload)
    # flush() returns once the USB bridge holds the data, not once it is on the wire.
    link.flush()
    time.sleep(settle)  # Let the bridge shift the bytes out at the wrong baud rate.
    link.baudrate = normal_baud
    time.sleep(settle)  # Let the bridge apply the restored baud rate.
    link.reset_input_buffer()  # Drop switch glitches; the firmware defers its markers.
    return written == len(payload)


def pattern_payload(test_id: str, params: dict) -> bytes:
    """Build byte_count bytes from the named pattern."""
    if params["pattern"] != "index_mod_256":
        raise PlanError(f"{test_id}: only pattern index_mod_256 is supported")
    return bytes(index & 0xFF for index in range(params["byte_count"]))


def wrong_baud_payload(test_id: str, params: dict) -> bytes:
    payload = bytes(params["payload"]) * params["repeat"]
    if not payload:
        raise PlanError(f"{test_id}: payload is empty")
    return payload


# ---------------------------------------------------------------------------
# Test T1: Nominal reception
# Method: Send printable ASCII lines with CRLF, one line at a time.
# Expected result: Byte-for-byte identical echo with no extra bytes.
# ---------------------------------------------------------------------------
def test_t1_nominal_receive(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["echo"] != "identical" or expected["markers"]:
        raise PlanError("T1: only an identical echo without markers is supported")
    terminator = params["terminator"].encode("ascii")
    lines = []
    for line_index in range(params["line_count"]):
        chars = bytes(
            params["first_char"]
            + (line_index * params["line_stride"] + column) % params["char_count"]
            for column in range(params["chars_per_line"])
        )
        lines.append(chars + terminator)

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
            print(
                f"FAIL T1: line {line_index + 1} differs at byte {first_mismatch(echoed, line)}; "
                f"received {len(echoed)}/{len(line)} bytes",
                file=sys.stderr,
            )
            return False

    if not check_no_extra(link, "T1", expected):
        return False

    print(
        f"PASS T1: {len(lines)} lines x {params['chars_per_line']} characters "
        "echoed identically; no extra byte received"
    )
    return True


# ---------------------------------------------------------------------------
# Test T2: Burst reception
# Method: Send binary bytes in one write while firmware reads continuously.
# Expected result: No byte loss and no extra output bytes.
# ---------------------------------------------------------------------------
def test_t2_burst_receive(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["echo"] != "identical" or expected["markers"]:
        raise PlanError("T2: only an identical echo without markers is supported")
    payload = pattern_payload("T2", params)

    link.reset_input_buffer()
    written = link.write(payload)
    link.flush()
    if written != len(payload):
        print(f"FAIL T2: wrote {written}/{len(payload)} bytes", file=sys.stderr)
        return False

    echoed = link.read(len(payload))
    if echoed != payload:
        print(
            f"FAIL T2: echo differs at byte {first_mismatch(echoed, payload)}; "
            f"received {len(echoed)}/{len(payload)} bytes",
            file=sys.stderr,
        )
        return False

    if not check_no_extra(link, "T2", expected):
        return False

    print(f"PASS T2: {len(payload):,}-byte burst echoed identically; no extra byte received")
    return True


# ---------------------------------------------------------------------------
# Test T3: Framing error
# Method: Send one byte at a wrong baud rate to the firmware, then restore the
#         bench baud rate and send one valid line.
# Expected result: [FE] marker followed by the exact echo of the valid line.
# ---------------------------------------------------------------------------
def test_t3_framing_error(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["then"] != "recovery_line":
        raise PlanError("T3: only then: recovery_line is supported")
    malformed = wrong_baud_payload("T3", params)
    line = params["recovery_line"].encode("ascii")
    expected_bytes = "".join(expected["markers"]).encode("ascii") + line

    if not send_at_wrong_baud(link, malformed, params["wrong_baud"], bench.baud_switch_settle):
        print(f"FAIL T3: could not write {len(malformed)} malformed bytes", file=sys.stderr)
        return False

    written = link.write(line)
    link.flush()
    if written != len(line):
        print(f"FAIL T3: wrote {written}/{len(line)} bytes", file=sys.stderr)
        return False

    received = link.read(len(expected_bytes))
    if received != expected_bytes:
        print(
            "FAIL T3: expected markers then valid-line echo; "
            f"mismatch at byte {first_mismatch(received, expected_bytes)}, "
            f"received {len(received)}/{len(expected_bytes)} bytes ({received.hex(' ')})",
            file=sys.stderr,
        )
        return False

    if not check_no_extra(link, "T3", expected):
        return False

    names = " ".join(marker.strip() for marker in expected["markers"])
    print(f"PASS T3: {names} reported; following line echoed identically")
    return True


# ---------------------------------------------------------------------------
# Test T4: Wrong baud rate
# Method: Send a burst at a wrong baud rate, then restore the bench baud rate
#         and send one valid line.
# Expected result: [FE] and/or [NE] markers, then the exact echo of the valid
#                  line, which proves the firmware is not blocked.
# ---------------------------------------------------------------------------
def test_t4_wrong_baud(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["then"] != "recovery_line":
        raise PlanError("T4: only then: recovery_line is supported")
    payload = wrong_baud_payload("T4", params)
    line = params["recovery_line"].encode("ascii")
    allowed = {marker.encode("ascii") for marker in expected["markers_any_of"]}
    min_markers = expected["min_markers"]

    if not send_at_wrong_baud(link, payload, params["wrong_baud"], bench.baud_switch_settle):
        print(f"FAIL T4: could not write {len(payload)} bytes at {params['wrong_baud']} baud",
              file=sys.stderr)
        return False

    written = link.write(line)
    link.flush()
    if written != len(line):
        print(f"FAIL T4: wrote {written}/{len(line)} bytes", file=sys.stderr)
        return False

    markers = []
    while True:
        received = link.read_until(b"\n")
        if received == line:
            break
        if received not in allowed or len(markers) >= MAX_MARKER_LINES:
            print(
                f"FAIL T4: expected markers then valid-line echo; after {len(markers)} "
                f"marker(s) received {len(received)} bytes ({received.hex(' ')})",
                file=sys.stderr,
            )
            return False
        markers.append(received)

    if len(markers) < min_markers:
        print(f"FAIL T4: {len(markers)} marker(s) received, at least {min_markers} expected",
              file=sys.stderr)
        return False

    if not check_no_extra(link, "T4", expected):
        return False

    names = " ".join(marker.decode("ascii").strip() for marker in markers)
    print(f"PASS T4: {len(payload)} bytes at {params['wrong_baud']} baud reported {names}; "
          "following line echoed identically")
    return True


# ---------------------------------------------------------------------------
# Test T5: Hardware overrun
# Method: Send the trigger line and a burst of valid bytes in one write; the
#         firmware masks interrupts on the trigger, so the burst overruns RDR.
#         Then send one valid line once the mask has ended.
# Expected result: Trigger echo, a prefix of the burst (bytes kept before the
#                  overrun), one [ORE], then the exact echo of the valid line.
# ---------------------------------------------------------------------------
def test_t5_overrun(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["then"] != "recovery_line":
        raise PlanError("T5: only then: recovery_line is supported")
    trigger = params["trigger_line"].encode("ascii")
    burst = params["burst"].encode("ascii")
    line = params["recovery_line"].encode("ascii")
    marker = "".join(expected["markers"]).encode("ascii")
    if not burst or not marker:
        raise PlanError("T5: burst and markers must not be empty")

    link.reset_input_buffer()
    written = link.write(trigger + burst)
    link.flush()
    if written != len(trigger) + len(burst):
        print(f"FAIL T5: wrote {written}/{len(trigger) + len(burst)} bytes", file=sys.stderr)
        return False
    # The recovery line must arrive after the mask; flush() only reaches the bridge.
    time.sleep(params["mask_ms"] / 1000 + bench.baud_switch_settle)

    written = link.write(line)
    link.flush()
    if written != len(line):
        print(f"FAIL T5: wrote {written}/{len(line)} bytes", file=sys.stderr)
        return False

    echoed = link.read(len(trigger))
    if echoed != trigger:
        print(f"FAIL T5: trigger echo differs ({echoed.hex(' ')})", file=sys.stderr)
        return False

    # Kept burst bytes come first; the deferred marker precedes the next valid byte.
    received = link.read_until(marker, size=len(burst) + len(marker))
    kept = received[: -len(marker)]
    if not received.endswith(marker) or not burst.startswith(kept) or not kept:
        print(
            f"FAIL T5: expected a burst prefix then {marker!r}; "
            f"received {len(received)} bytes ({received.hex(' ')})",
            file=sys.stderr,
        )
        return False
    if expected["burst_loss"] and len(kept) == len(burst):
        print("FAIL T5: whole burst echoed; no byte lost to the overrun", file=sys.stderr)
        return False

    echoed = link.read(len(line))
    if echoed != line:
        print(
            f"FAIL T5: valid-line echo differs at byte {first_mismatch(echoed, line)}; "
            f"received {len(echoed)}/{len(line)} bytes ({echoed.hex(' ')})",
            file=sys.stderr,
        )
        return False

    if not check_no_extra(link, "T5", expected):
        return False

    print(
        f"PASS T5: {len(kept)}/{len(burst)} burst bytes kept, {marker.decode('ascii').strip()} "
        "reported; following line echoed identically"
    )
    return True


# ---------------------------------------------------------------------------
# Test T6: RX buffer overflow
# Method: Send the trigger line and a burst larger than the RX queue in one
#         write; the firmware stops reading the queue on the trigger, so it
#         fills up. Read the echo, then send one valid line.
# Expected result: Trigger echo, the first kept burst bytes, one [FULL], then
#                  the exact echo of the valid line.
# ---------------------------------------------------------------------------
def test_t6_buffer_overflow(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["then"] != "recovery_line":
        raise PlanError("T6: only then: recovery_line is supported")
    trigger = params["trigger_line"].encode("ascii")
    payload = pattern_payload("T6", params)
    line = params["recovery_line"].encode("ascii")
    marker = "".join(expected["markers"]).encode("ascii")
    kept = expected["kept"]
    if not 0 < kept < len(payload):
        raise PlanError("T6: kept must be between 1 and byte_count - 1")

    link.reset_input_buffer()
    written = link.write(trigger + payload)
    link.flush()
    if written != len(trigger) + len(payload):
        print(f"FAIL T6: wrote {written}/{len(trigger) + len(payload)} bytes", file=sys.stderr)
        return False

    echoed = link.read(len(trigger))
    if echoed != trigger:
        print(f"FAIL T6: trigger echo differs ({echoed.hex(' ')})", file=sys.stderr)
        return False

    # The queue keeps the oldest bytes; the firmware echoes them after the pause.
    echoed = link.read(kept)
    if echoed != payload[:kept]:
        print(
            f"FAIL T6: kept bytes differ at byte {first_mismatch(echoed, payload[:kept])}; "
            f"received {len(echoed)}/{kept} bytes",
            file=sys.stderr,
        )
        return False

    # The driver drops new bytes until the firmware has read the overflow event.
    time.sleep(bench.baud_switch_settle)
    written = link.write(line)
    link.flush()
    if written != len(line):
        print(f"FAIL T6: wrote {written}/{len(line)} bytes", file=sys.stderr)
        return False

    expected_bytes = marker + line
    received = link.read(len(expected_bytes))
    if received != expected_bytes:
        print(
            f"FAIL T6: expected {marker!r} then valid-line echo; "
            f"mismatch at byte {first_mismatch(received, expected_bytes)}, "
            f"received {len(received)}/{len(expected_bytes)} bytes ({received.hex(' ')})",
            file=sys.stderr,
        )
        return False

    if not check_no_extra(link, "T6", expected):
        return False

    print(
        f"PASS T6: {kept}/{len(payload)} bytes kept, {marker.decode('ascii').strip()} "
        "reported; following line echoed identically"
    )
    return True


# ---------------------------------------------------------------------------
# Test T7: No interrupt storm
# Method: After T3 to T6 in the same run, stay idle, then send valid lines
#         spaced in time.
# Expected result: No output while idle, each line echoed identically, and
#                  LD1 still blinking (visual check).
# ---------------------------------------------------------------------------
def test_t7_no_irq_storm(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["echo"] != "identical" or expected["markers"]:
        raise PlanError("T7: only an identical echo without markers is supported")
    lines = [line.encode("ascii") for line in params["lines"]]
    if not lines:
        raise PlanError("T7: lines must not be empty")

    # No reset_input_buffer(): output left by the previous tests must show here.
    time.sleep(params["idle_s"])
    idle = link.read(link.in_waiting)
    if idle:
        print(f"FAIL T7: {len(idle)} bytes received while idle ({idle.hex(' ')})", file=sys.stderr)
        return False

    for index, line in enumerate(lines):
        if index:
            time.sleep(params["interval_s"])
        written = link.write(line)
        link.flush()
        if written != len(line):
            print(f"FAIL T7: line {index + 1}: wrote {written}/{len(line)} bytes", file=sys.stderr)
            return False
        echoed = link.read(len(line))
        if echoed != line:
            print(
                f"FAIL T7: line {index + 1} differs at byte {first_mismatch(echoed, line)}; "
                f"received {len(echoed)}/{len(line)} bytes ({echoed.hex(' ')})",
                file=sys.stderr,
            )
            return False

    if not check_no_extra(link, "T7", expected):
        return False

    print(
        f"PASS T7: idle {params['idle_s']} s silent; {len(lines)} lines "
        f"{params['interval_s']} s apart echoed identically"
    )
    print(f"CHECK T7: {expected['manual_check']} (visual)")
    return True


# ---------------------------------------------------------------------------
# Test T8: RX flush
# Method: Send the trigger line and a burst in one write; the firmware lets
#         the burst queue, calls UartRxFlush() and reports the flushed count.
#         Then send one valid line.
# Expected result: Trigger echo, [EMPTY n=<byte_count>] with no burst byte
#                  echoed, then the exact echo of the valid line.
# ---------------------------------------------------------------------------
def test_t8_flush(link: serial.Serial, test: dict, bench: Bench) -> bool:
    params, expected = test["params"], test["expected"]
    if expected["then"] != "recovery_line" or expected["burst_echo"] != "none":
        raise PlanError("T8: only burst_echo: none then recovery_line is supported")
    trigger = params["trigger_line"].encode("ascii")
    payload = pattern_payload("T8", params)
    line = params["recovery_line"].encode("ascii")
    marker = expected["marker"].format(**params).encode("ascii")

    link.reset_input_buffer()
    written = link.write(trigger + payload)
    link.flush()
    if written != len(trigger) + len(payload):
        print(f"FAIL T8: wrote {written}/{len(trigger) + len(payload)} bytes", file=sys.stderr)
        return False

    # A flushed byte echoed before the marker would show up as a mismatch here.
    expected_bytes = trigger + marker
    received = link.read(len(expected_bytes))
    if received != expected_bytes:
        print(
            f"FAIL T8: expected trigger echo then {marker!r}; "
            f"mismatch at byte {first_mismatch(received, expected_bytes)}, "
            f"received {len(received)}/{len(expected_bytes)} bytes ({received.hex(' ')})",
            file=sys.stderr,
        )
        return False

    written = link.write(line)
    link.flush()
    if written != len(line):
        print(f"FAIL T8: wrote {written}/{len(line)} bytes", file=sys.stderr)
        return False
    echoed = link.read(len(line))
    if echoed != line:
        print(
            f"FAIL T8: valid-line echo differs at byte {first_mismatch(echoed, line)}; "
            f"received {len(echoed)}/{len(line)} bytes ({echoed.hex(' ')})",
            file=sys.stderr,
        )
        return False

    if not check_no_extra(link, "T8", expected):
        return False

    print(
        f"PASS T8: {len(payload)} bytes flushed, {marker.decode('ascii').strip()} "
        "reported; following line echoed identically"
    )
    return True


TESTS = {
    "T1": test_t1_nominal_receive,
    "T2": test_t2_burst_receive,
    "T3": test_t3_framing_error,
    "T4": test_t4_wrong_baud,
    "T5": test_t5_overrun,
    "T6": test_t6_buffer_overflow,
    "T7": test_t7_no_irq_storm,
    "T8": test_t8_flush,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\nVersion:")[0],  # Keep the version history out of --help.
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "port", nargs="?", help="serial port, for example /dev/ttyACM0 or COM5 (default: bench.yaml)"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="bench configuration file")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN, help="UART RX test plan file")
    parser.add_argument("--only", nargs="+", metavar="ID", help="run only these test IDs, e.g. T1 T3")
    parser.add_argument("--baud", type=int, help="baud rate (default: bench.yaml)")
    parser.add_argument("--timeout", type=float, help="reply timeout in seconds (default: bench.yaml)")
    args = parser.parse_args()

    source = args.config
    try:
        config = load_bench_config(args.config)
        link_config = config["serial"]
        port = args.port or link_config["port"]
        baud = args.baud or link_config["baudrate"]
        timeout = args.timeout if args.timeout is not None else config["timeouts"]["read"]
        port_open_settle = config["delays"]["port_open_settle"]
        bench = Bench(timeout, config["delays"]["baud_switch_settle"])

        source = args.plan
        plan = load_test_plan(args.plan)
        if args.only:
            planned = [test["id"] for test in plan]
            unknown = [test_id for test_id in args.only if test_id not in planned]
            if unknown:
                raise ValueError(f"--only: {', '.join(unknown)} not in plan ({', '.join(planned)})")
            plan = [test for test in plan if test["id"] in args.only]
        selected = [test["id"] for test in plan]
        for position, test in enumerate(plan):
            missing = [test_id for test_id in test.get("after", []) if test_id not in selected[:position]]
            if missing:
                raise ValueError(
                    f"{test['id']} must run after {', '.join(missing)} in the same run; "
                    f"add them to --only"
                )
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        detail = f"missing key {error}" if isinstance(error, KeyError) else error
        print(f"Configuration error in {source}: {detail}", file=sys.stderr)
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
            failed = []
            for test in plan:
                try:
                    passed = TESTS[test["id"]](link, test, bench)
                except (PlanError, KeyError, TypeError, ValueError) as error:
                    detail = f"missing key {error}" if isinstance(error, KeyError) else error
                    print(f"Plan error in {args.plan}, test {test['id']}: {detail}",
                          file=sys.stderr)
                    return 2
                if not passed:
                    failed.append(test["id"])
    except (serial.SerialException, OSError) as error:
        print(f"Serial error: {error}", file=sys.stderr)
        return 2

    if failed:
        print(f"FAILED: {', '.join(failed)} ({len(plan) - len(failed)}/{len(plan)} passed)")
        return 1
    print(f"ALL PASSED: {len(plan)}/{len(plan)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
