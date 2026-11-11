<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/tui/hil_tui.md
\brief      Commands and keys of the HIL bench TUI, and its pytest event stream.

\author     Z. BEN-AKKA
\version    1.5
\date       11/11/2026

\section tui_hil_tui_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 09/11/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 09/11/2026 | Z. BEN-AKKA | Add the event stream of the hil_events pytest plugin. |
| 1.2     | 10/11/2026 | Z. BEN-AKKA | Fix the JUnit counting rule: a call and teardown failure counts once in tests. |
| 1.3     | 10/11/2026 | Z. BEN-AKKA | Add the Tests tab: keys, runs and the board state after a run. |
| 1.4     | 11/11/2026 | Z. BEN-AKKA | Fix the JUnit counting rule of a teardown error: it changed in pytest 9.1. |
| 1.5     | 11/11/2026 | Z. BEN-AKKA | Add the Export key and the report of a run. |
****************************
-->

# hil_tui.py

Close miniterm, minicom and any other program on the port first: only one
program may hold it.

## Launch

| Command | Effect |
|:--|:--|
| `python3 tests/host/tui/hil_tui.py` | Opens the TUI on the port of `bench.yaml` and connects |
| `python3 tests/host/tui/hil_tui.py --port /dev/ttyACM1` | Uses another serial port |
| `python3 tests/host/tui/hil_tui.py --bench FILE` | Uses another bench configuration (default `tests/host/config/bench.yaml`) |
| `python3 tests/host/tui/hil_tui.py --catalog FILE` | Uses another command catalogue (default `tests/host/config/commands.yaml`) |
| `python3 tests/host/tui/hil_tui.py --help` | Shows the options |

The script runs from any folder. Exit code 0 after Quit; exit code 2 with one
line on stderr when Textual is missing, `bench.yaml` is unusable or the
catalogue is invalid. Install Textual with
`python3 -m pip install --user textual==8.2.8`.

## Keys

| Key | Action |
|:--|:--|
| F5 or ctrl+n | Connect: reset, banner, HELLO and CAPS |
| F6 or ctrl+b | Disconnect: closes the port, no reset |
| F7 or ctrl+r | Recover after a lost session or an unknown image |
| F2 or ctrl+t | Shows or hides the monitor |
| F3 or ctrl+o | Switches between the Commands and Tests tabs |
| F4 or ctrl+y | Export: writes the report of the last run |
| ctrl+q or ctrl+l | Quit and free the port; during a run, asks first |
| Enter in a field | Sends the command, as the Send button does |
| Space in the test tree | Marks or unmarks a test, a file or a family |
| Enter in the test tree | Opens or closes a node |
| Escape in a confirmation | Answers No |

The VS Code terminal keeps F5, F6 and ctrl+q: use the ctrl keys there.

## Tests tab

The tree lists the pytest files and tests of `tests/host/hil`, T1-T8 of
`uart_rx.yaml` and the scenarios of `tests/host/tui/scenarios/`, read again on
Refresh. A run covers one family; "Will run" shows what Run starts.

| Selection | Run |
|:--|:--|
| The whole pytest family | The whole suite |
| A file, or some tests | Those files and tests |
| T7 | T3 to T7: T7 needs T3 to T6 |
| One scenario | Its steps in the open session: Connect first |

| During and after a run | Behaviour |
|:--|:--|
| Start (pytest, T1-T8) | The TUI closes the port, the run opens it |
| Live | Counters, current test, one line per test, TX and RX in the monitor (5 updates per second) |
| Stop | SIGINT to the run; during a flash it waits for the flash end, a second Stop kills it at once |
| End of a pytest run | The TUI connects again |
| End of T1-T8, or a Stop forced during a flash | `UNKNOWN_IMAGE`; the TUI offers to flash hil-bench, then connects |
| Scenario prompt | Yes or No; a No fails the step, the next steps still run |

Each run has its own folder `work/hil-results/<date-time>-<suite>/` with
`events.jsonl`, `run.json` and, for pytest, `junit.xml` and `pytest.log`.

## Report

Export is grey until a run ends. It is then active whatever the verdict,
`INTERRUPTED` after a Stop included, and grey again during the next run. It
writes `report.md` and `report.html` in the folder of the last run; the
message line gives their path. The report holds the verdict, the totals, one
line per test with its outcome (`tests/protocol.md` section 7.3), the banner,
the Git commit, the timeouts that differ from section 8.1 and, for each
failure, the last request and the records received for it.

After a run killed with the TUI, rebuild the report from `events.jsonl`:

```bash
python3 tests/host/tui/core/report.py work/hil-results/<date-time>-<suite>
```

The report is then `INTERRUPTED` and counts only the tests that ran. Open the
page from WSL with
`explorer.exe "$(wslpath -w work/hil-results/<date-time>-<suite>/report.html)"`.

## Event stream (plugins/hil_events.py)

The TUI follows a pytest run through `events.jsonl`, written by a plugin that
is loaded only on request. Without it, pytest, `ci/scripts/hil.sh` and
Jenkins are unchanged. It can also be run by hand:

```bash
PYTHONPATH=tests/host/tui/plugins python3 -m pytest tests/host/hil -m smoke \
    -p hil_events --hil-events /tmp/ev.jsonl
tail -f /tmp/ev.jsonl    # In another terminal: the run, live
```

One JSON object per line, flushed at once: a run killed with SIGKILL keeps
every line written so far. Each line has `t` (epoch seconds) and `event`:

| `event` | Fields |
|:--|:--|
| `session_start` | `pid`, `args`, `rootdir` |
| `collected` | `count`, `nodeids` |
| `test_start` | `nodeid` |
| `log` | `nodeid` (null outside a test), `logger`, `level`, `text`: every `hil.*` record (TX, RX, `RUN make`, banner), the same lines as `pytest.log` |
| `report` | `nodeid`, `when` (setup, call, teardown), `outcome`, `hil_outcome`, `duration`, `message`, `xfail` |
| `test_end` | `nodeid` |
| `session_end` | `exitstatus` |

`hil_outcome` of a phase:

| Cause | `hil_outcome` |
|:--|:--|
| Phase passed | `PASS` |
| Skip or xfail | `SKIPPED` |
| `HilOutcome` exception | Its outcome, e.g. `UNEXPECTED_RESET` (`tests/protocol.md` section 7.3) |
| `assert` | `FUNCTIONAL_ERROR` |
| Any other exception | `BENCH_ERROR` |

The plugin does not count. To get the `junit.xml` totals, count the `report`
lines as pytest does: a passed `call` is passed, a failed `call` a failure, a
failed `setup` or `teardown` an error, a skip or an xfail skipped. The
`tests` attribute is their sum, less one for some teardown errors; the rule
changed in pytest 9.1 (pytest issue #3850):

| Failed `teardown` after | pytest < 9.1 | pytest ≥ 9.1 |
|:--|:--|:--|
| A failed `call` (two test cases in `junit.xml`) | Less one: counted once | Counted twice |
| Anything else (passed `call`, skip, failed `setup`) | Counted twice | Less one: counted once |

`core/runner.py` counts by the rule of the installed pytest, the one that runs
the tests. A write error never fails the tests: one line on stderr, then the
stream stops.
