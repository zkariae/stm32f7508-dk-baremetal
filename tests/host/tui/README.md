<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/tui/README.md
\brief      HIL bench TUI: frozen criteria, architecture and phase E plan.

\author     Z. BEN-AKKA
\version    1.2
\date       23/11/2026

\details
  Reference document of the terminal interface that drives the HIL bench
  (PC to STM32 over UART). It records the acceptance criteria, the design,
  the working rules and the ordered sub-steps of phase E, so that the work
  can be resumed without any other context. Progress is tracked by the
  GitHub issues of section 6, not in this file.

\section tui_readme_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 09/11/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 17/11/2026 | Z. BEN-AKKA | Add the proof of each criterion, the run folder files, the minicom limit and the CI board skip. |
| 1.2     | 23/11/2026 | Z. BEN-AKKA | Add the run options and the operator instructions. |
****************************
-->

# HIL bench TUI

## 1. Purpose

A terminal tool, built with [Textual](https://textual.textualize.io/), that
drives the HIL bench with buttons and lists. It sends commands without typing
the protocol, runs the tests, shows the UART traffic and a readable result,
and exports the test report. The user guide (screens, keys, runs and
reports) is `hil_tui.md`.

The tool reuses `SerialAdapter`, `Board` and `Programmer` from
`tests/host/hil/adapters/`. It changes neither the firmware nor the protocol
1.3, and pytest, `ci/scripts/hil.sh` and Jenkins keep running without it.

Phase E delivers one version, `v0.5.0`, built step by step: every sub-step
adds to the same tool, and the tag is set once all the criteria are met.

## 2. Acceptance criteria

The criteria are frozen. No criterion is added without an explicit decision
of the developer.

| # | Criterion | Proof at the end of the phase |
|:-:|:--|:--|
| C1 | Send any command without typing the protocol | Every firmware command is sent to the board from the interface, a rejected case included. The CI fails if the names in `hil_protocol.h` and in the catalogue differ, in both directions. Destructive or rebooting commands are marked in the catalogue. A board test sends each command with its default arguments, and excludes the marked commands or keeps them in a safe area |
| C2 | Run the scenarios and pytest | All collected tests, T1–T8 and a scenario run from the TUI. Stop frees the port and a new connection works. During a flash, Stop is deferred; a second press forces it and goes to `UNKNOWN_IMAGE` |
| C3 | Live traffic and a readable result | The counters come from the events received during the run. `junit.xml` is only a reference: same passed, failed, error and skipped counts, same exit code. TX and RX lines match `pytest.log` and appear during the run; the delay between `pytest.log` and the display is measured automatically. T1–T8: same exit code as the script |
| C4 | Export the report | The button is grey without a report and active at the end of a run. After Stop, the report can be exported, is marked `INTERRUPTED`, never PASS, and counts only the tests that ran. After a brutal kill, the report is rebuilt from `events.jsonl` |
| C5 | Add without changing the interface | On a throwaway branch, a real test command is added to the firmware, `hil_protocol.h` and the YAML, with a test and a scenario. In `tests/host/tui/`, the diff touches only `scenarios/*.yaml` (existing argument types) |
| C6 | Stay stable through faults | Unplugged cable, busy port or silent board (at connection, in a session or during a run, each with its own message): no crash, and work resumes without restarting the TUI. "Port busy" names the program that holds the port. A Disconnect button is available. Quitting during a run asks for confirmation and stops the whole process group. The board state is checked again at the next launch. The interface timer gap stays at 500 ms at most over a full suite. pytest, `uart_rx_check.py`, `miniterm` and the TUI exclude each other on the port; `minicom` is checked or documented as a limit |

## 3. Constraints

| Constraint | Consequence |
|:--|:--|
| `pytest` and `uart_rx_check.py` open the serial port themselves | The TUI closes the port before a run, and connects again after it. The traffic of a run is not read on the port |
| From E7 and E8, pytest and `uart_rx_check.py` lock the port, as `miniterm` and the TUI do | **Keep the TUI closed while a Jenkins check runs**: the check would fail at once on a busy port |
| `minicom` takes no `flock` on the port | The exclusion does not cover it: a documented limit (`ci/README.md` section 4.2). Close it before a run or a Jenkins check |
| A Jenkins check flashes the shared board | Before a check by hand, read `fw=` and `build=` in the banner: the board may hold another build |
| `CAPS` gives names, never arguments | The forms come from a catalogue |
| `SerialAdapter` only listens during a transaction and is not thread-safe | One thread owns the port and also listens while idle |
| The `hil.serial` logger already traces TX and RX | A `logging.Handler` feeds the monitor. It changes no log level, otherwise the `make` output would leave `pytest.log` |
| `uart_rx_check.py` prints only PASS, FAIL and CHECK lines | It gets a `--trace` option |
| T1–T8 leaves `uart-diag` on the board | No `READY` arrives after it: the TUI offers to flash `hil-bench` |
| T7 needs T3 to T6 (`after` in `uart_rx.yaml`) | Selecting T7 also selects them |
| `Programmer` logs only the start of a flash | The end is taken from the next event: `RUN make reset`, an RX line or an error |
| Most test failures are plain `assert` statements | The plugin classifies them: `HilOutcome` gives its outcome, `AssertionError` gives `FUNCTIONAL_ERROR`, anything else is a bench error |
| `pytest --collect-only` overwrites `pytest.log` | Discovery passes its own `--log-file` |
| The HIL total of 216 includes `tests/host/hil/unit/` | The TUI tests stay out of `tests/host/hil/`, in a folder not named `unit/`, so that `from unit.hil_fake import` still works |

## 4. Architecture

```text
tests/host/config/commands.yaml    Command catalogue (data)
tests/host/config/run_options.yaml Run options (data)
tests/host/tui/
├── README.md                      This document
├── pyproject.toml                 Textual version, pytest settings
├── hil_tui.py                     Entry point
├── core/                          No Textual import
│   ├── catalog.py                 Catalogue and CAPS merged, arguments checked
│   ├── session.py                 Thread that owns the port, session states
│   ├── suites.py                  Discovery of pytest, T1–T8 and scenarios
│   ├── runner.py                  Subprocess, event stream, stop, verdict
│   ├── scenario.py                Scenario execution
│   ├── run_options.py             Run options: values checked, environment of a run
│   └── report.py                  Markdown and HTML reports
├── plugins/hil_events.py          pytest plugin (-p), writes events.jsonl
├── scenarios/*.yaml               One file per scenario
├── ui/                            Textual widgets, no bench logic
└── tests/                         Tests of the TUI
```

`ui/` knows no command name and no test name.

### 4.1 Session states

```text
DISCONNECTED ──► CONNECTING ──► CONNECTED ──► RUNNING
                     │              │
                     ▼              ▼
              UNKNOWN_IMAGE    SESSION_LOST
```

- Connect does a reset, waits for `READY`, then sends `HELLO` and `CAPS`.
- Disconnect closes the port and does not reset the board.
- A run closes the port; the state of the board has then changed, so the next
  step is a new connection.
- A `BUILD_MISMATCH` is shown and does not block.
- `READY` in an active session is `UNEXPECTED_RESET` (`tests/protocol.md`
  section 4.3). A request that timed out is never sent again (section 8.3).
  Sending stays blocked until the operator presses Recover.

### 4.2 Command catalogue

`CAPS` tells what the firmware can do; the catalogue tells how to ask for it.

| In `CAPS` | In the catalogue | Display |
|:--|:--|:--|
| yes | yes | Typed form |
| yes | no | Free `key=value` form |
| no | yes | Grey: not in this firmware |

```yaml
QSPI_ERASE:
  group: QSPI
  summary: Erase one 4 KB block of the test area
  effect: destructive          # Or reboots; asks for confirmation
  spec: "6.9"
  args:
    addr: {type: hex, digits: [1, 8], multiple_of: 4096,
           min: 0x00FF0000, max: 0x00FFF000, default: 0x00FF0000}
```

Argument types: `enum`, `int`, `hex`, `hexdata`, `letter`, `color`. The field
`requires: LCD_INIT` shows a warning and does not forbid sending. The free
form can also send a deliberately invalid value.

### 4.3 Runs

Each run has its own folder, `work/hil-results/<date-time>-<suite>/`, with
`events.jsonl`, `junit.xml`, `pytest.log`, a copy of `bench.yaml` and
`run.json` (selection, commit, run options, verdict and totals, written
atomically).
Export adds `report.md` and `report.html`.

- The plugin is loaded with `-p hil_events`, alongside `--log-file` and
  `--junitxml`. The pytest configuration does not change.
- The counters shown come from the events received during the run.
- The verdict is PASS only if the exit code is 0 and at least one test ran.
  Otherwise it is FAIL, BENCH ERROR or `INTERRUPTED`.
- Stop sends SIGINT to the process group, after the end of a flash.

A pytest run can have options: environment variables that its tests read.
`tests/host/config/run_options.yaml` lists them, and the Options window is
built from it, so the TUI code names none of them.

- A value equal to its default is not sent. The variable is also removed from
  the environment of the run, so a run uses what the Tests tab shows.
- The values start from the environment of the TUI and stay from one run to
  the next until it closes. T1–T8 and the scenarios get none.
- `run.json` and the report give the variables sent.
- A test gives its instructions to the operator on the logger `hil.operator`:
  the Tests tab shows them in bold on the progress line until the test ends.

### 4.4 Report

The report gives the verdict, the totals, one line per test with its outcome
from `tests/protocol.md` section 7.3, the banner, the Git commit and the
`bench.yaml` used, and the run options. It adds any overridden timeout (section 8.1) and, for each
failure, the last request and its records (section 8.4).

### 4.5 Scenarios

A scenario is a list of steps run in the open session. Adding a YAML file adds
a scenario.

```yaml
name: LCD colour check
steps:
  - {command: LCD_INIT}
  - {command: LCD_FILL, args: {color: "0xF800"}}
  - {command: LCD_PIXEL, args: {x: 0, y: 0}, expect: {color: "0xF800"}}
  - {prompt: "Is the screen red?"}
```

## 5. Dependencies

- Python 3.10, pyserial, PyYAML and pytest, as for `tests/host/hil/`.
- Textual 8.2.8, pinned. `core/` does not import it, so the catalogue and
  session tests need no installation.
- The `ui/` tests run in the CI, with Textual installed for the `jenkins`
  user:

```bash
python3 -m pip install --user textual==8.2.8
sudo -u jenkins -H python3 -m pip install --user textual==8.2.8
```

## 6. Issues and labels

| Label | Use |
|:--|:--|
| `enhancement` | Each feature, with its tests and CI changes |
| `bug` | Each problem found |
| `documentation` | README, GIF, video, post |
| `question` | A decision to take before coding |
| `duplicate`, `invalid` | Closing a duplicate or invalid issue |

| Lot | Issue | Sub-steps |
|:--|:--|:--|
| 1. Foundations and catalogue | #9 | E1 to E6 |
| 2. Serial link and session | #10 | E7 to E10 |
| 3. Commands on screen | #11 | E11 to E16 |
| 4. Test runs | #12 | E17 to E25 |
| 5. Report, faults and release | #13 | E26 to E34 |

Each pull request carries its label and `Refs #n`; the last one of a lot uses
`Closes #n`. Each problem found gets its own `bug` issue, and each open
decision its own `question` issue.

## 7. Working rules

The rules of `ci/README.md` section 9 apply, with these additions:

- Pull requests pass one at a time, since a branch must be up to date with its
  target. Each sub-branch starts from the integration branch just merged.
- The board stays attached to WSL for every check, and the TUI stays closed.
- A pull request that only changes `tests/host/tui/`, `work/doc_zak/` or
  `*.md` files skips the board stages of the check (`ci/README.md`
  section 4.1).
- The C5 proof uses a throwaway branch that holds several files, as a
  deliberate exception to the one file rule. It gets no pull request, is never
  merged and is deleted afterwards.

## 8. Release

Tag `v0.5.0` closes phase E once C1 to C6 are met:
`phaseE-tui/integration` → `develop` → `main`, then `main` → `develop`.

## 9. Sub-steps

One file per sub-step, in this order. The TUI starts at E14; each later
sub-step adds to it.

| # | File | Lot | Criteria |
|:-:|:--|:-:|:--|
| E0 | Branch `phaseE-tui/integration` | 1 | — |
| E1 | `tests/host/tui/README.md` | 1 | — |
| E2 | `tests/host/tui/pyproject.toml` | 1 | — |
| E3 | `tests/host/config/commands.yaml` | 1 | C1 |
| E4 | `tests/host/tui/core/catalog.py` | 1 | C1, C5 |
| E5 | `tests/host/tui/tests/test_catalog.py` | 1 | C1 |
| E6 | `ci/scripts/build.sh` | 1 | C1 |
| E7 | `tests/host/hil/adapters/serial_adapter.py` (port lock) | 2 | C6 |
| E8 | `tests/host/rx_check/uart_rx_check.py` (port lock, `--trace`) | 2 | C3, C6 |
| E9 | `tests/host/tui/core/session.py` | 2 | C1, C6 |
| E10 | `tests/host/tui/tests/test_session.py` | 2 | C6 |
| E11 | `tests/host/tui/ui/monitor.py` | 3 | C3 |
| E12 | `tests/host/tui/ui/commands_pane.py` | 3 | C1 |
| E13 | `tests/host/tui/ui/app.py` | 3 | C1, C6 |
| E14 | `tests/host/tui/hil_tui.py` | 3 | C1 |
| E15 | `tests/host/tui/tests/test_ui_commands.py` | 3 | C1 |
| E16 | `tests/host/tui/tests/test_catalog_board.py` | 3 | C1 |
| E17 | `tests/host/tui/plugins/hil_events.py` | 4 | C2, C3 |
| E18 | `tests/host/tui/core/scenario.py` | 4 | C2 |
| E19 | `tests/host/tui/core/suites.py` | 4 | C2, C5 |
| E20 | `tests/host/tui/core/runner.py` | 4 | C2, C3, C6 |
| E21 | `tests/host/tui/tests/test_runner.py` | 4 | C2, C3 |
| E22 | `tests/host/tui/scenarios/lcd_colors.yaml` | 4 | C2 |
| E23 | `tests/host/tui/ui/tests_pane.py` | 4 | C2, C3 |
| E24 | `tests/host/tui/ui/app.py` | 4 | C2, C3 |
| E25 | `tests/host/tui/tests/test_display_latency.py` | 4 | C3 |
| E26 | `tests/host/tui/core/report.py` | 5 | C4 |
| E27 | `tests/host/tui/tests/test_report.py` | 5 | C4 |
| E28 | `tests/host/tui/ui/app.py` | 5 | C4, C6 |
| E29 | `tests/host/tui/tests/test_faults.py` | 5 | C6 |
| E30 | `tests/host/tui/tests/test_responsiveness.py` | 5 | C6 |
| E31 | `tests/host/tui/tests/test_extensibility.py` | 5 | C5 |
| E32 | `ci/README.md` | 5 | C6 |
| E33 | `work/doc_zak/plan_test_hil.md` | 5 | — |
| E34 | `tests/host/tui/README.md` | 5 | C6 |

## 10. Proofs

Where each criterion of section 2 is proved. The test files are in
`tests/host/tui/tests/`; `@board` tests need the board.

| # | Proof |
|:-:|:--|
| C1 | `test_catalog.py`: names of `hil_protocol.h` and of the catalogue in both directions, confirmation of flash writes. `test_ui_commands.py`: forms, sending, answers and rejected values. `test_catalog_board.py` (`@board`): each command with its default arguments, a rejected value leaves the LED unchanged |
| C2 | `test_runner.py`: pytest, T1–T8 and scenario runs, Stop, Stop deferred during a flash, second Stop forces it. `scenarios/lcd_colors.yaml` runs on the board |
| C3 | `test_runner.py`: counters from the events equal to `junit.xml`, same exit code. `test_display_latency.py`: TX and RX lines and their times follow `pytest.log`, delay measured below the limit |
| C4 | `test_report.py`: totals equal to `junit.xml` and `run.json`, `INTERRUPTED` after Stop, report rebuilt from `events.jsonl` after a kill, Export writes both files |
| C5 | `test_extensibility.py`: a new command, scenario or pytest file appears without code change, and the TUI code names no command. Throwaway branch with `DELAY_MS` (firmware, `hil_protocol.h`, catalogue, test, scenario): in `tests/host/tui/` the diff is only `scenarios/delay_ms.yaml`; recorded in a comment of issue #13 |
| C6 | `test_session.py`: busy port with its holder, port lost, timed out request never sent again, Disconnect without reset. `test_faults.py`: each fault with its own message, Disconnect, quit during a run, board checked at the next launch. `test_responsiveness.py`: timer gap at most 500 ms (117 ms over the 216 board tests). `minicom`: limit documented in `ci/README.md` section 4.2 |

Results on 17/11/2026, integration build `fw=1.3.0 proto=1.3`: TUI tests
283 passed without the board, HIL suite 216 passed on the board.
