"""Traffic monitor of the TUI: the hil loggers shown live in a RichLog.

The session sends no event for the traffic: SerialAdapter already logs each
TX and RX line on hil.serial, Board the session start on hil.board and
Programmer each make target on hil.programmer (README.md section 3). A
MonitorHandler on the parent logger "hil" turns each record into a
MonitorLine and hands it to a sink. It runs in the thread that logged, the
session thread, so the application gives a sink that crosses to the UI
thread (app.call_from_thread(monitor.add, line)).

Nothing configures logging in the TUI process, so attach() lowers the "hil"
logger to INFO there and detach() restores it. pytest runs in its own
process: pytest.log and the make output do not change.

MonitorLine.created is the time of the log record, kept for the measure of
the display delay (C3). Text is written as rich Text, never as markup, so
received bytes such as "[FE]" show as they are. No command or test name.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import logging
import time
from dataclasses import dataclass

from rich.text import Text
from textual.widgets import RichLog

LOGGER = "hil"  # Parent of hil.serial, hil.board and hil.programmer
MAX_LINES = 5000  # Lines kept on screen: memory and redraw stay bounded over a full suite
DIRECTIONS = ("TX", "RX")  # Message prefixes of hil.serial: "TX  <line>", "RX  <line>"
STYLES = {"TX": "bold cyan", "RX": "bold green", "INFO": "dim", "WARN": "bold yellow", "ERROR": "bold red"}


@dataclass(frozen=True)
class MonitorLine:
    """One displayed line: kind is TX, RX, INFO, WARN or ERROR; created is time.time()."""

    created: float
    kind: str
    text: str


def to_line(record: logging.LogRecord) -> MonitorLine:
    """MonitorLine of a log record: TX and RX from their prefix, else from the level."""
    message = record.getMessage()
    head, _, rest = message.partition("  ")
    if head in DIRECTIONS and rest:
        return MonitorLine(record.created, head, rest)
    if record.levelno >= logging.ERROR:
        kind = "ERROR"
    elif record.levelno >= logging.WARNING:
        kind = "WARN"
    else:
        kind = "INFO"
    source = record.name.rpartition(".")[2]  # serial, board, programmer
    return MonitorLine(record.created, kind, f"{source}: {message}")


class MonitorHandler(logging.Handler):
    """Logging handler that hands each record to sink(MonitorLine)."""

    def __init__(self, sink):
        super().__init__(logging.INFO)
        self.sink = sink
        self._saved_level = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink(to_line(record))
        except Exception:  # A closing UI must not break the session thread
            self.handleError(record)


def attach(handler: MonitorHandler) -> None:
    """Feed the handler with the hil loggers, at INFO in this process only."""
    logger = logging.getLogger(LOGGER)
    handler._saved_level = logger.level
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def detach(handler: MonitorHandler) -> None:
    """Stop feeding the handler and restore the level found by attach()."""
    logger = logging.getLogger(LOGGER)
    logger.removeHandler(handler)
    if handler._saved_level is not None:
        logger.setLevel(handler._saved_level)
        handler._saved_level = None


def render(line: MonitorLine) -> Text:
    """Time, kind and text of a line, styled by kind."""
    clock = time.strftime("%H:%M:%S", time.localtime(line.created)) + f".{int(line.created * 1000) % 1000:03d}"
    text = Text(no_wrap=True)
    text.append(clock, style="dim")
    text.append(f" {line.kind:<5} ", style=STYLES.get(line.kind, ""))
    text.append(line.text)
    return text


class Monitor(RichLog):
    """Live view of the bench traffic; add() is called on the UI thread."""

    DEFAULT_CSS = """
    Monitor {
        border: round $primary;
        border-title-align: left;
    }
    """

    def __init__(self, *, max_lines: int = MAX_LINES, **kwargs):
        super().__init__(max_lines=max_lines, markup=False, highlight=False, wrap=False, **kwargs)
        self.border_title = "Monitor"

    def add(self, line: MonitorLine) -> None:
        self.write(render(line))
