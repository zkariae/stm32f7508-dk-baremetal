"""Options window of the TUI: the run options of the Tests tab.

Built from core/run_options.py, so no option name is written here: a box to
tick for a bool, a list for a choice, with a field beside it when another
value can be typed (the typed value wins), a field for an int. OK checks
every value and shows the rule under a refused one; the window then stays
open. It closes with the values, or with None on Cancel or Escape.

Version: 1.0
Date: 23/11/2026
Author: Z. BEN-AKKA
History:
  1.0  23/11/2026  Initial version.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from core.run_options import RunOption, RunOptions, ValueRefused


class OptionsScreen(ModalScreen[dict]):
    """One field per option; OK or Cancel."""

    DEFAULT_CSS = """
    OptionsScreen { align: center middle; background: #000080 70%; }
    OptionsScreen > Vertical {
        width: 84; max-width: 100%; height: auto; max-height: 100%; padding: 1 2; background: $surface;
    }
    OptionsScreen #fields { height: auto; max-height: 24; }
    OptionsScreen .field { height: auto; margin-top: 1; }
    OptionsScreen .field Label { width: 18; padding: 0 1 0 0; }
    OptionsScreen .field Select, OptionsScreen .field Input { width: 1fr; }
    OptionsScreen .field Input { margin-left: 1; }
    OptionsScreen Checkbox { margin-top: 1; }
    OptionsScreen .error { color: $error; height: auto; }
    OptionsScreen #buttons { height: auto; margin-top: 1; align-horizontal: right; }
    OptionsScreen #buttons Button { margin-left: 2; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, options: RunOptions, values: dict):
        super().__init__()
        self.options = options
        self.values = values

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Options of the pytest runs")
            with VerticalScroll(id="fields"):
                for option in self.options.options:
                    yield self._field(option, self.values[option.name])
                    yield Static(option.help, markup=False)
                    yield Static("", id=f"err-{option.name}", classes="error", markup=False)
            with Horizontal(id="buttons"):
                yield Button("< Cancel >", id="cancel")
                yield Button("< OK >", id="ok", variant="primary")

    @staticmethod
    def _field(option: RunOption, value):
        if option.type == "bool":
            return Checkbox(option.label, value, id=f"opt-{option.name}", compact=True)
        if option.type == "int":
            return Horizontal(Label(option.label), Input(value, placeholder=f"{option.low} to {option.high}",
                                                         id=f"opt-{option.name}", compact=True), classes="field")
        listed = value in [choice for choice, _ in option.choices]
        widgets = [Label(option.label),
                   Select([(", ".join([choice, *aliases]), choice) for choice, aliases in option.choices],
                          value=value if listed else option.default, allow_blank=False,
                          id=f"opt-{option.name}", compact=True)]
        if option.pattern:
            widgets.append(Input("" if listed else value, placeholder=f"or {option.hint}",
                                 id=f"other-{option.name}", compact=True))
        return Horizontal(*widgets, classes="field")

    def _typed(self, option: RunOption):
        """The value of a field; the typed text of a choice wins over its list."""
        if option.pattern:
            other = self.query_one(f"#other-{option.name}", Input).value.strip()
            if other:
                return other
        return self.query_one(f"#opt-{option.name}").value

    @on(Button.Pressed, "#ok")
    @on(Input.Submitted)  # Enter in a field is OK
    def _ok(self) -> None:
        values, refused = {}, False
        for option in self.options.options:
            error = self.query_one(f"#err-{option.name}", Static)
            error.update("")
            try:
                values[option.name] = option.check(self._typed(option))
            except ValueRefused as failure:
                error.update(f"{option.label}: {failure.message}")
                refused = True
        if not refused:
            self.dismiss(values)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)
