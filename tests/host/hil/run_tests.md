<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/hil/run_tests.md
\brief      Commands to run the HIL protocol tests with pytest.

\author     Z. BEN-AKKA
\version    1.1
\date       26/10/2026

\details
  Lists the commands to run the pytest protocol tests of the hil-bench
  firmware, the options of the HIL bench plugin, the bench prerequisites and
  the outcomes of tests/protocol.md section 7.3. Bench settings are in
  tests/host/config/bench.yaml, shared with the rx_check/ UART tests.

\section hil_run_tests_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 26/10/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 26/10/2026 | Z. BEN-AKKA | Add the live display of make, TX and RX lines. |
****************************
-->

# Running the HIL protocol tests

All commands run from the repository root.

## Prerequisites

```bash
python3 -m pip install pyserial pyyaml pytest   # host dependencies (tests/host/hil/pyproject.toml)
```

- OpenOCD runs without sudo: the udev rule shipped with OpenOCD
  (`60-openocd.rules`) gives the ST-LINK to the `plugdev` group, and the user
  must be in `plugdev` (`id -nG`). The serial port must be readable by the
  user too (`ls -l /dev/ttyACM0`).
- The serial port is `serial.port` in `tests/host/config/bench.yaml`.

## Run all tests

```bash
python3 -m pytest tests/host/hil
```

The session flashes the hil-bench image (`make hil-bench-flash`), resets the
board (`make reset`), waits for the readiness banner, then checks HELLO and
CAPS before the first test.

## Common runs

```bash
python3 -m pytest tests/host/hil -v                         # one line per test
python3 -m pytest tests/host/hil --log-cli-level=INFO       # show make commands, TX and RX lines
python3 -m pytest tests/host/hil --no-flash                 # test the image already on the board
python3 -m pytest tests/host/hil -m smoke                   # banner, HELLO and CAPS only
python3 -m pytest tests/host/hil --port /dev/ttyACM1        # another serial port
python3 -m pytest tests/host/hil --junitxml=work/hil-results/junit.xml   # JUnit report
```

## Live display

`--log-cli-level=INFO` prints, under each test, the make commands run on the
board, every line sent to the firmware (`TX`) and every line received from it
(`RX`), decoded as text. A line that holds a byte outside 0x20-0x7E is shown
as escaped bytes, for example `TX  b'CMD id=20 command=HE\x7fLLO'`. The
OpenOCD output is not shown; it stays in `work/hil-results/pytest.log`
(`--log-cli-level=DEBUG` shows it too).

```text
10:42:01 RUN make reset
10:42:02 RX  READY name=hil-bench fw=1.0.0 proto=1.0 build=3a03de9 reset=PIN reset_flags=0x04000000
10:42:02 session started: READY name=hil-bench fw=1.0.0 proto=1.0 build=3a03de9 reset=PIN reset_flags=0x04000000
10:42:02 TX  CMD id=1 command=HELLO
10:42:02 RX  RESULT id=1 status=OK name=hil-bench proto=1.0 fw=1.0.0 build=3a03de9
10:42:02 RX  END id=1
```

## Options

| Option | Default | Purpose |
|:--|:--|:--|
| `--port PORT` | `serial.port` in `bench.yaml` | Serial port |
| `--no-flash` | flash | Do not flash; with `expected_build: auto`, the last build is still expected |
| `--bench-config FILE` | `tests/host/config/bench.yaml` | Bench configuration |
| `--log-file FILE` | `work/hil-results/pytest.log` | Log of every serial line and make output |
| `--log-cli-level=INFO` | off | Show make commands, TX and RX lines live in the terminal |

```bash
# Serial port
python3 -m pytest tests/host/hil --port /dev/ttyACM1

# Test the image already on the board, without flashing
python3 -m pytest tests/host/hil --no-flash

# Bench configuration
python3 -m pytest tests/host/hil --bench-config path/to/my_bench.yaml

# Log file
python3 -m pytest tests/host/hil --log-file work/hil-results/run1.log

# Live display of make commands, TX and RX lines
python3 -m pytest tests/host/hil --no-flash --log-cli-level=INFO

# One test, by name
python3 -m pytest tests/host/hil -k test_hello_matches_banner

# Options combined
python3 -m pytest tests/host/hil -v --no-flash --port /dev/ttyACM1 --junitxml=work/hil-results/junit.xml

# List the tests without running them (no board needed)
python3 -m pytest tests/host/hil --collect-only -q

# List all options, the HIL bench ones under "HIL bench"
python3 -m pytest tests/host/hil --help
```

Bench settings used by these tests:

| Key | Default | Purpose |
|:--|:--|:--|
| `timeouts.startup` | `5.0` | Readiness banner after the reset (section 8.1) |
| `timeouts.response` | `2.0` | END of each request (section 8.1) |
| `timeouts.make` | `120.0` | One make call: flash or reset |
| `delays.port_open_settle` | `0.1` | After opening the port, and stale input drained before each reset |
| `hardware.reset_target` | `reset` | make target that resets the board |
| `firmware.expected_build` | `auto` | Build HELLO must report: `auto` (the flashed image), a value, or `null` to skip |
| `firmware.accept_build_mismatch` | `false` | `true` turns BUILD_MISMATCH into a logged warning |
| `results_dir` | `work/hil-results` | Folder of the log file, relative to the repository root |

## Outcomes

A failure message starts with the outcome of `tests/protocol.md` section 7.3:

| Outcome | Typical cause |
|:--|:--|
| `PROGRAMMING_FAILURE` | make failed: build error, ST-LINK not found, OpenOCD permission |
| `STARTUP_FAILURE` | No valid READY within 5 s: wrong image (for example uart-diag), wrong port |
| `INCOMPATIBLE_PROTOCOL` | The firmware's protocol major version is not 1 |
| `BUILD_MISMATCH` | HELLO build differs from `firmware.expected_build` |
| `UNSUPPORTED_COMMAND` | A test needs a command missing from CAPS |
| `UNEXPECTED_RESET` | A READY record during the session |
| `PROTOCOL_FAILURE` | Invalid record, wrong ID, ERROR record, or no END in time |
| `FUNCTIONAL_ERROR` | A command answered status=ERR or unexpected values |

## Exit codes

| Code | Meaning |
|:--:|:--|
| 0 | All selected tests passed |
| 1 | At least one test failed, or the board session could not start |
| 2 | Interrupted |
| 4 | Usage error, such as an invalid bench configuration |
| 5 | No test selected |
