<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/hil/run_tests.md
\brief      Commands to run the UART RX HIL tests.

\author     Z. BEN-AKKA
\version    1.2
\date       21/10/2026

\details
  Lists the commands to run the UART RX tests T1 to T6, all together or one
  at a time, and the options that override the default files and settings.
  Test definitions are in plans/uart_rx.yaml; bench settings are in
  config/bench.yaml.

\section run_tests_md_version_history Version history
| Version | Date       | Author      | Description                    |
|:-------:|:----------:|:------------|:-------------------------------|
| 1.0     | 19/10/2026 | Z. BEN-AKKA | Initial version.               |
| 1.1     | 21/10/2026 | Z. BEN-AKKA | Add T5 hardware overrun run.   |
| 1.2     | 21/10/2026 | Z. BEN-AKKA | Add T6 RX buffer overflow run. |
****************************
-->

# Running the UART RX HIL tests

All commands run from the repository root.

## Prerequisites

```bash
python3 -m pip install pyserial pyyaml   # host dependencies
make hil-bench-flash                     # flash the raw-echo bench firmware
```

## Run all tests

```bash
python3 tests/host/hil/uart_tx_check.py               # T1 to T6, in plan order
```

## Run one test

```bash
python3 tests/host/hil/uart_tx_check.py --only T1     # Nominal reception
python3 tests/host/hil/uart_tx_check.py --only T2     # Burst reception
python3 tests/host/hil/uart_tx_check.py --only T3     # Framing error
python3 tests/host/hil/uart_tx_check.py --only T4     # Wrong baud rate
python3 tests/host/hil/uart_tx_check.py --only T5     # Hardware overrun
python3 tests/host/hil/uart_tx_check.py --only T6     # RX buffer overflow
```

## Run a selection

```bash
python3 tests/host/hil/uart_tx_check.py --only T3 T4  # runs in plan order
```

## Repeat a run

```bash
for i in $(seq 10); do python3 tests/host/hil/uart_tx_check.py; done   # about 14 s per run
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
python3 tests/host/hil/uart_tx_check.py /dev/ttyACM1

# Test plan
python3 tests/host/hil/uart_tx_check.py --plan path/to/my_plan.yaml

# Bench configuration
python3 tests/host/hil/uart_tx_check.py --config path/to/my_bench.yaml

# Bench baud rate (must match the firmware, otherwise the tests fail)
python3 tests/host/hil/uart_tx_check.py --baud 115200

# Read timeout in seconds
python3 tests/host/hil/uart_tx_check.py --timeout 5

# Options combined
python3 tests/host/hil/uart_tx_check.py /dev/ttyACM1 --only T4 --timeout 5

# List all options
python3 tests/host/hil/uart_tx_check.py --help
```

## Exit codes

| Code | Meaning |
|:--:|:--|
| 0 | All selected tests passed |
| 1 | At least one test failed |
| 2 | Configuration, plan or serial port error |
