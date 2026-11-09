<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/tui/hil_tui.md
\brief      Commands and keys of the HIL bench TUI, and its pytest event stream.

\author     Z. BEN-AKKA
\version    1.1
\date       09/11/2026

\section tui_hil_tui_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 09/11/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 09/11/2026 | Z. BEN-AKKA | Add the event stream of the hil_events pytest plugin. |
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
| ctrl+q or ctrl+l | Quit and free the port |
| Enter in a field | Sends the command, as the Send button does |
| Escape in a confirmation | Answers No |

The VS Code terminal keeps F5, F6 and ctrl+q: use the ctrl keys there.

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
lines as JUnit does: a failed `call` is a failure, a failed `setup` or
`teardown` an error, a skip or an xfail skipped; a test that fails in `call`
and in `teardown` counts as two test cases. A write error never fails the
tests: one line on stderr, then the stream stops.
