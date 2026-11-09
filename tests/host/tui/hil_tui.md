<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       tests/host/tui/hil_tui.md
\brief      Commands and keys of the HIL bench TUI.

\author     Z. BEN-AKKA
\version    1.0
\date       09/11/2026

\section tui_hil_tui_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 09/11/2026 | Z. BEN-AKKA | Initial version. |
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
