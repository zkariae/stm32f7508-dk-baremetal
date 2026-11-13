"""Progress box of the TUI: a small modal box in the style of the dialog(1) gauge.

A light grey box, centred on a dimmed screen, with a thin raised border (light
top and left, dark bottom and right), the title centred in the top border in
the primary colour, a status message on the left and a sunken gauge at the
bottom. The gauge fills with the primary colour and shows the percentage in
its middle, in the primary colour on the empty part and in the cursor text
colour on the filled part, as dialog(1) does. Without a percentage (progress
None) a block a fifth of the gauge wide moves to and fro instead, for a wait
whose end cannot be measured.

One box is shown at a time: update() replaces its title, message, progress
and auto close in place, so a new event never opens a second box. With
auto_close the box closes itself that many seconds after the last update;
without it the box stays until Escape or Enter ("Esc: close" in the bottom
border). A box covered by another screen (a Yes or No question) waits until
it is on top again before it closes, since Textual always dismisses the top
screen. On top means the top screen of the application: Screen.is_current is
also true for a screen seen under a modal one, so it cannot tell.

A modal screen stops the bindings of the application. keys lists those that
must still work under the box, as bindings to application actions
(Binding("f7,ctrl+r", "app.recover", "Recover")); the footer shows them.

The text uses the terminal font, so the box keeps the fixed-width look of
dialog(1). The colours come from the theme ($surface, $primary,
$block-cursor-foreground); the bevel uses fixed light and dark greys.

Version: 1.1
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  11/11/2026  Initial version.
  1.1  11/11/2026  Close only when the box is the top screen: is_current is also true under a modal.
"""

from collections.abc import Iterable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Static

FRAME_RATE = 10  # Steps per second of the moving block
BLOCK_SHARE = 5  # The moving block is a fifth of the gauge wide
CLOSE_RETRY = 0.5  # Seconds before a covered box tries to close again


class Gauge(Widget):
    """One line gauge in a sunken frame: a percentage, or a moving block when the value is None."""

    COMPONENT_CLASSES = {"gauge--filled", "gauge--empty"}
    DEFAULT_CSS = """
    Gauge {
        height: 3;
        background: $surface;
        border-top: solid #404040; border-left: solid #404040;
        border-bottom: solid #FFFFFF; border-right: solid #FFFFFF;
    }
    Gauge > .gauge--filled { background: $primary; color: $block-cursor-foreground; text-style: bold; }
    Gauge > .gauge--empty { color: $primary; text-style: bold; }
    """

    value: reactive[float | None] = reactive(0.0)
    step: reactive[int] = reactive(0)

    def on_mount(self) -> None:
        self._timer = self.set_interval(1 / FRAME_RATE, self._advance, pause=self.value is not None)

    def watch_value(self, value: float | None) -> None:
        timer = getattr(self, "_timer", None)
        if timer is None:
            return
        if value is None:
            timer.resume()
        else:
            timer.pause()

    def _advance(self) -> None:
        self.step += 1

    def block(self, width: int) -> tuple[int, int]:
        """Start and end of the moving block on a gauge of width cells, for the current step."""
        size = max(1, width // BLOCK_SHARE)
        travel = width - size
        if travel <= 0:
            return 0, width
        position = self.step % (2 * travel)
        start = position if position <= travel else 2 * travel - position  # To and fro
        return start, start + size

    def render(self) -> Text:
        width = self.content_size.width
        filled_style = self.get_component_rich_style("gauge--filled")
        empty_style = self.get_component_rich_style("gauge--empty")
        if self.value is None:
            start, end = self.block(width)
            label = ""
        else:
            value = min(100.0, max(0.0, self.value))
            start, end = 0, round(width * value / 100)
            label = f"{value:.0f}%"
        cells = list(" " * width)
        left = max(0, (width - len(label)) // 2)
        cells[left:left + len(label)] = label
        text = Text()
        for index, char in enumerate(cells[:width]):
            text.append(char, filled_style if start <= index < end else empty_style)
        return text


class ProgressBox(ModalScreen[None]):
    """Title in the border, a message and a gauge; update() replaces the content in place."""

    DEFAULT_CSS = """
    ProgressBox { align: center middle; background: #000080 40%; }
    ProgressBox > Vertical {
        width: 64; max-width: 100%; height: auto; padding: 0 1; background: $surface;
        border-top: solid #FFFFFF; border-left: solid #FFFFFF;
        border-bottom: solid #404040; border-right: solid #404040;
        border-title-align: center; border-title-color: $primary; border-title-style: bold;
        border-subtitle-align: right; border-subtitle-color: $foreground;
    }
    ProgressBox #box-message { height: auto; margin-bottom: 1; }
    """
    BINDINGS = [("escape", "close", "Close"), ("enter", "close", "Close")]

    def __init__(self, title: str, message: str, progress: float | None = 0.0, auto_close: float | None = None,
                 keys: Iterable[Binding] = ()):
        super().__init__()
        self.box_title = title
        self.message = message
        self.progress = progress
        self.auto_close = auto_close
        self._close_timer = None
        for key in keys:  # Application keys that stay active under the box
            self._bindings.bind(key.key, key.action, key.description, show=key.show, key_display=key.key_display,
                                priority=key.priority)

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static("", id="box-message", markup=False)
            yield Gauge(id="gauge")

    def on_mount(self) -> None:
        self._show()

    def update(self, title: str, message: str, progress: float | None = 0.0, auto_close: float | None = None) -> None:
        """Replace the whole content: title, message, progress (0 to 100, None to move) and auto close (s, None)."""
        self.box_title, self.message, self.progress, self.auto_close = title, message, progress, auto_close
        if self.is_mounted:
            self._show()

    def _show(self) -> None:
        box = self.query_one("#box", Vertical)
        box.border_title = f" {self.box_title} "
        box.border_subtitle = " Esc: close " if self.auto_close is None else ""
        self.query_one("#box-message", Static).update(self.message)
        self.query_one(Gauge).value = self.progress
        if self._close_timer is not None:
            self._close_timer.stop()
            self._close_timer = None
        if self.auto_close is not None:
            self._close_timer = self.set_timer(self.auto_close, self._close_when_on_top)

    def _on_top(self) -> bool:
        return self.app.screen is self  # Not is_current: also true under a modal screen

    def _close_when_on_top(self) -> None:
        if self._on_top():
            self.dismiss()
        else:  # A question covers the box: Textual would dismiss that one
            self._close_timer = self.set_timer(CLOSE_RETRY, self._close_when_on_top)

    def action_close(self) -> None:
        if self._on_top():
            self.dismiss()
