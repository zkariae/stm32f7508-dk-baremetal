<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/hil/run_tests.md
\brief      Commands to run the UART RX HIL tests.

\author     Z. BEN-AKKA
\version    1.7
\date       22/10/2026

\details
  Lists the commands to run the UART RX tests T1 to T8, all together or one
  at a time, and the options that override the default files and settings.
  Test definitions are in plans/uart_rx.yaml; bench settings are in
  config/bench.yaml.

\section run_tests_md_version_history Version history
| Version | Date       | Author      | Description                                    |
|:-------:|:----------:|:------------|:-----------------------------------------------|
| 1.0     | 19/10/2026 | Z. BEN-AKKA | Initial version.                               |
| 1.1     | 21/10/2026 | Z. BEN-AKKA | Add T5 hardware overrun run.                   |
| 1.2     | 21/10/2026 | Z. BEN-AKKA | Add T6 RX buffer overflow run.                 |
| 1.3     | 21/10/2026 | Z. BEN-AKKA | Add T7 run with its prerequisites; port first. |
| 1.4     | 22/10/2026 | Z. BEN-AKKA | Add T8 RX flush run.                           |
| 1.5     | 22/10/2026 | Z. BEN-AKKA | Use the renamed uart_rx_check.py script.       |
| 1.6     | 22/10/2026 | Z. BEN-AKKA | Run-all command alone; bench delays; 6 s runs. |
| 1.7     | 22/10/2026 | Z. BEN-AKKA | Flash the uart-diag image before T1 to T8.     |
****************************
-->

# Running the UART RX HIL tests

All commands run from the repository root.

## Prerequisites

```bash
python3 -m pip install pyserial pyyaml   # host dependencies
make uart-diag-flash                     # flash the raw-echo UART diagnostic image
```

## Run all tests

```bash
python3 tests/host/hil/uart_rx_check.py
```

Runs T1 to T8 in plan order. T7 prints
`CHECK T7: LD1 keeps blinking at 2 Hz (visual)`: check LD1 on the board.

## Run one test

```bash
python3 tests/host/hil/uart_rx_check.py --only T1     # Nominal reception
python3 tests/host/hil/uart_rx_check.py --only T2     # Burst reception
python3 tests/host/hil/uart_rx_check.py --only T3     # Framing error
python3 tests/host/hil/uart_rx_check.py --only T4     # Wrong baud rate
python3 tests/host/hil/uart_rx_check.py --only T5     # Hardware overrun
python3 tests/host/hil/uart_rx_check.py --only T6     # RX buffer overflow
python3 tests/host/hil/uart_rx_check.py --only T3 T4 T5 T6 T7   # No interrupt storm
python3 tests/host/hil/uart_rx_check.py --only T8     # RX flush
```

T7 must run after T3 to T6 in the same run: `--only T7` alone is refused
(exit code 2).

## Run a selection

```bash
python3 tests/host/hil/uart_rx_check.py --only T3 T4  # runs in plan order
python3 tests/host/hil/uart_rx_check.py /dev/ttyACM1 --only T3 T4   # port before --only
```

`--only` takes every following word as a test ID, so put the port before it.

## Repeat a run

```bash
for i in $(seq 10); do python3 tests/host/hil/uart_rx_check.py; done   # about 6 s per run
```

## Options

| Option | Default | Purpose |
|:--|:--|:--|
| `port` | `serial.port` in `bench.yaml` | Serial port, e.g. `/dev/ttyACM0` or `COM5` |
| `--only ID ...` | all plan tests | Test IDs to run |
| `--plan FILE` | `plans/uart_rx.yaml` | Test plan |
| `--config FILE` | `config/bench.yaml` | Bench configuration |
| `--baud N` | `serial.baudrate` in `bench.yaml` | Bench baud rate |
| `--timeout S` | `timeouts.read` in `bench.yaml` | Read timeout in seconds |

```bash
# Serial port
python3 tests/host/hil/uart_rx_check.py /dev/ttyACM1

# Test plan
python3 tests/host/hil/uart_rx_check.py --plan path/to/my_plan.yaml

# Bench configuration
python3 tests/host/hil/uart_rx_check.py --config path/to/my_bench.yaml

# Bench baud rate (must match the firmware, otherwise the tests fail)
python3 tests/host/hil/uart_rx_check.py --baud 115200

# Read timeout in seconds
python3 tests/host/hil/uart_rx_check.py --timeout 5

# Options combined
python3 tests/host/hil/uart_rx_check.py /dev/ttyACM1 --only T4 --timeout 5

# List all options
python3 tests/host/hil/uart_rx_check.py --help
```

Bench delays have no command-line option; change them in `config/bench.yaml`:

| Key | Default | Purpose |
|:--|:--|:--|
| `delays.port_open_settle` | `0.1` | Wait after opening the port |
| `delays.baud_switch_settle` | `0.05` | Wait around a baud rate switch (T3, T4) and USB margin (T5, T6) |
| `delays.extra_byte_wait` | `0.2` | Wait for an unexpected byte at the end of each test; `--timeout` does not change it |

## Exit codes

| Code | Meaning |
|:--:|:--|
| 0 | All selected tests passed |
| 1 | At least one test failed |
| 2 | Configuration, plan or serial port error |
