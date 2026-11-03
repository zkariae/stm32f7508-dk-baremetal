<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       work/doc_zak/plan_test_hil.md
\brief      HIL test plan of the STM32F7508-DK project.

\author     Z. BEN-AKKA
\version    1.2
\date       03/11/2026

\details
  Describes the hardware-in-the-loop test bench: principle, layout of the
  firmware and host files, protocol, test scope with its progress, Git
  workflow and deliverables. The protocol itself is specified in
  tests/protocol.md; the bench phases are detailed in
  work/doc_zak/local/plan_hil_bench_phases.md.

\section plan_test_hil_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 13/10/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 23/10/2026 | Z. BEN-AKKA | Show rx_check/ and the shared bench config. |
| 1.2     | 03/11/2026 | Z. BEN-AKKA | Align the plan with the delivered bench (protocol 1.3, v0.3.0); translate it to English. |
****************************
-->

# HIL test plan — STM32F7508-DK

## 1. Goal and principle

Automate, from a PC, the programming, control and checking of the project on the STM32F7508-DK board. The PC runs the scenarios with pytest; a dedicated firmware receives the commands over UART, calls the board drivers and sends results back. ST-LINK/OpenOCD or DFU programs the target. External instruments complete the checks when a result must be verified physically.

```text
PC: runner + pytest + adapters
       ├── ST-LINK/OpenOCD or DFU ── programming/reset ──┐
       ├── virtual serial port ── commands/results ──────┤
       └── optional instruments ── measurements ─────────┤
                                                        ▼
STM32F7508-DK: bench firmware → existing drivers → peripherals
```

## 2. Folders and files

The product applications stay in `dev/`. The validation firmware and the Python tests are grouped in `tests/`. The bench firmware reuses the `dev/common/` drivers and the `stm32f7508-dk/` BSP; it does not duplicate their code. Items marked "(planned)" do not exist yet.

```text
.
├── Makefile                         # Declares the hil-bench image (sources, modules, memory, build ID)
├── dev/
│   ├── apps/                        # Existing applications, unchanged
│   └── common/                      # Drivers shared by the applications and the bench
│       └── uart/
│           ├── uart.c               # UART transmit and receive (time-bounded reception)
│           └── uart.h
├── stm32f7508-dk/                   # Submodule: BSP, startup, linker, programming and reset
└── tests/
    ├── protocol.md                  # HIL protocol specification (normative reference)
    ├── firmware/
    │   ├── hil_bench/
    │   │   ├── main.c               # Clock, UART, banner and command loop
    │   │   ├── reset_cause.c        # Reset cause reported in the banner
    │   │   ├── line.c               # Bounded line reception (LINE_TOO_LONG, BAD_FRAME)
    │   │   ├── protocol.c           # Request decoding and response writing
    │   │   ├── dispatch.c           # Routes each command to its handler
    │   │   ├── commands.c           # Command table: HELLO, CAPS, LED, QSPI
    │   │   ├── lcd_commands.c       # GPIO_CONFIG and LCD commands
    │   │   └── inc/                 # Headers, including hil_protocol.h (names, keys, codes, versions)
    │   └── uart_diag/
    │       └── main.c               # Raw echo image for tests T1 to T8
    └── host/
        ├── config/
        │   └── bench.yaml            # Bench shared by rx_check/ and hil/: port, baud rate, delays, hardware options
        ├── rx_check/                 # UART driver regression (uart-diag image)
        │   ├── uart_rx_check.py      # Tests T1 to T8
        │   ├── plans/
        │   │   └── uart_rx.yaml      # Parameters and expected results of T1 to T8
        │   └── run_tests.md          # Run commands
        └── hil/                      # Protocol tests (hil-bench image)
            ├── pyproject.toml        # Python dependencies, pytest configuration and markers
            ├── conftest.py           # Loads the fixtures/board_fixtures.py plugin
            ├── run_tests.md          # Run commands and manual requests
            ├── run_hil.py            # Entry point of a campaign (planned)
            ├── adapters/
            │   ├── serial_adapter.py # Dialogue with the firmware
            │   ├── programmer.py     # Build/flash with the repository tools
            │   ├── board.py          # Board reset and preparation
            │   ├── outcomes.py       # Normalised outcomes (protocol.md section 7.3)
            │   └── instruments.py    # Optional measurements (planned)
            ├── fixtures/
            │   └── board_fixtures.py # Bench options, connection and pytest life cycle
            ├── unit/                 # Adapters tested against a fake firmware, no board
            └── cases/
                ├── expected.py       # Expected values taken from the datasheets
                ├── test_smoke.py
                ├── test_protocol_*.py  # startup, hello, caps, lines, requests, recovery
                ├── test_led.py
                ├── test_qspi.py
                ├── test_lcd.py
                ├── test_bootloader.py  # (planned)
                └── test_dfu.py         # (planned)
```

### File responsibilities

- `main.c` sets the clock to 216 MHz, initialises the UART, sends the banner and runs the main loop of the bench.
- `reset_cause.*` reads and clears the reset flags reported in the banner.
- `line.*` receives a bounded line and reports lines that are too long or invalid.
- `protocol.*` decodes the requests and writes the responses and the protocol errors.
- `dispatch.*` maps each command to its handler, without any transport logic.
- `commands.*` and `lcd_commands.*` run the validation operations by calling the existing LED, RCC, GPIO, LCD/LTDC and QSPI drivers.
- `serial_adapter.py` sends the requests, matches the responses to their transactions and handles the timeouts.
- `programmer.py` calls the Makefile targets and the existing tools: OpenOCD/ST-LINK or DFU.
- `board.py` groups reset, start-up synchronisation and preparation of the initial state.
- `outcomes.py` classifies each failure with the outcomes of `tests/protocol.md` section 7.3.
- `cases/expected.py` holds the expected values; they come from the datasheets, not from the firmware.
- `cases/test_*.py` holds the scenarios, their assertions and acceptance criteria.
- `instruments.py` will be used only when a measuring instrument is available.

The Makefile builds the `hil-bench` image from `tests/firmware/hil_bench/`, linking the BSP sources and the `dev/common/` modules; it also generates `hil_build.h`, the build ID reported by the firmware.

## 3. Firmware ↔ PC protocol

UART reception is in place: the driver receives lines with a time-bounded wait. The protocol is text based, readable from a terminal and easy to handle in Python. Its full specification is `tests/protocol.md` (revision 1.9, protocol 1.3); it is the only reference, and this plan only gives an overview.

```text
READY name=hil-bench fw=1.3.0 proto=1.3 build=<rev> reset=PIN reset_flags=0x04000000
CMD id=42 command=QSPI_ID
RESULT id=42 status=OK jedec_id=0x0018BA20
END id=42
```

The number identifies the transaction. Every command ends with an explicit result, success or error with a code, then with `END`. The `READY` banner gives the name, the firmware and protocol versions, the build and the reset cause; `CAPS` lists the available commands. A command is first specified in `protocol.md`, then coded in the firmware, then tested on the host (section 6.1); each new command increments the minor version of the protocol.

## 4. Test scope

| Group | Main checks | Status |
|---|---|---|
| Start-up | Programming, reset, expected banner, available commands | Done (`v0.2.0`) |
| UART | Reception, framing errors, timeouts | Done: T1 to T8 with `rx_check` (`v0.1.0`) |
| Clock | Configuration values and expected timings | Partial: 216 MHz checked only through `LCD_CLOCK` |
| LED | Commands and LD1 state; external measurement if needed | Done (protocol 1.1) |
| QSPI | JEDEC ID, read, erase and write in the test area | Done (protocol 1.2) |
| LCD | Pins, pixel clock, LTDC timings, layer, scan and displayed patterns | Done (protocol 1.3) |
| Bootloader | Boot from QSPI and behaviour with a valid/invalid image | To do |
| DFU | Entry into the ROM bootloader, internal flash programming and restart | To do |

Battery ADC and RTC are not in the initial scope: these functions are not among the software functions currently identified in the repository.

## 5. Git branches and progress

`main` stays stable and only receives tagged versions. Work happens on `develop`: each phase has its integration branch, created from `develop`, and each modified file has its own sub-branch, merged into the phase branch. A finished phase is merged into `develop`, then the branches are deleted. The `stm32f7508-dk/` submodule follows the same principle in its own repository.

```text
main ──────────────── v0.1.0 ── v0.2.0 ── v0.3.0 ──
                         ▲         ▲         ▲
develop ─────────────────┴─────────┴─────────┴─────
   └── phase branch
         ├── file sub-branch 1
         └── file sub-branch 2
```

| Milestone | Content |
|---|---|
| `v0.1.0` | UART reception and tests T1 to T8 (`rx_check`, `uart-diag` image). |
| `v0.2.0` | `hil-bench` firmware, pytest framework and protocol 1.0 conformance. |
| `v0.3.0` | Protocol 1.3: LED, QSPI, GPIO and LCD commands with their tests. |
| Next | Bootloader and DFU, then campaign automation. |

Order followed: foundation → protocol → firmware and runner → first integrated test → peripherals → bootloaders/DFU. The first integrated test was merged before the campaign was extended to the other functions.

## 6. Execution and deliverables

A campaign follows this cycle: check the bench, build the image, program the target, reset, wait for the banner, run the scenarios, collect the responses/measurements, then generate the report. Each test states its prerequisites, expected result, timeout and tolerance.

Already in place: the serial log and the make output in `work/hil-results/pytest.log`, the JUnit report with `--junitxml`, and the classification of failures with `tests/protocol.md` section 7.3 (programming, start-up, protocol, functional…). Generated outputs go to `work/hil-results/` and are not tracked by Git.

Still to do: archive, for each run, the Git commit, the configuration, the binary, the serial log, the available measurements and the JUnit report.

## 7. Next step

The first increment (program, restart, receive the banner, send `HELLO` and check its response from pytest) is delivered, together with the LED, QSPI and LCD peripheral tests. The next steps are:

1. Bootloader: boot from QSPI, valid image and tampered image (`test_bootloader.py`).
2. DFU: entry into the ROM bootloader, programming and restart (`test_dfu.py`).
3. Automation: full campaign in one command (`run_hil.py`) and archiving of each run in `work/hil-results/`.
