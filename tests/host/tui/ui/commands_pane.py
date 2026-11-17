"""Command pane of the TUI: the CAPS list and a form per command (C1).

The list is Catalog.merge(CAPS), grouped by the catalogue group (README.md
section 4.2): a typed command gets a form built from commands.yaml, a command
the catalogue does not know gets the free form, a catalogue command missing
from CAPS is shown grey and cannot be selected. "!" marks a destructive or
rebooting command.

Send checks the typed form with Catalog.check and shows the error under the
faulty field; nothing is sent then. The free form sends "key=value ..." as
typed, to make the firmware reject a value on purpose; only a token without
"=" is refused, since a request cannot carry it. requires is a note, never a
block.

The pane does not know the session: it posts CommandsPane.Send and the
application asks for confirmation when effect is set, then sends. The
application hands the answer back with show_result (status, the code of an
ERR, then every result field, whatever the command) or show_failure; the
last result of each command shows again with its form. No command name is
written here: everything comes from the catalogue, CAPS and the answers.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import time
from functools import partial

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Checkbox, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from core.catalog import ArgumentError, Catalog, Entry, EntryStatus, default_text

MARK_EFFECT = "!"


def hint(arg) -> str:
    """Placeholder of an argument field: the accepted form."""
    params = arg.params
    if arg.type == "int":
        text = f"{params['min']} to {params['max']}"
    elif arg.type == "hex":
        high = params["digits"][1]
        text = f"0x{params['min']:0{high}X} to 0x{params['max']:0{high}X}"
        if params.get("multiple_of"):
            text += f", multiple of {params['multiple_of']}"
    elif arg.type == "hexdata":
        text = f"{params['bytes'][0]} to {params['bytes'][1]} bytes, 2 hex digits each"
    elif arg.type == "letter":
        text = f"{params['min']} to {params['max']}"
    elif arg.type == "color":
        text = "RGB565, 0x and 1 to 4 hex digits"
    else:
        text = arg.type
    return text if arg.required else f"{text} (optional)"


def parse_free(text: str) -> dict:
    """key=value tokens of the free form, unchecked; ArgumentError for a token without '='."""
    args = {}
    for token in text.split():
        key, equal, value = token.partition("=")
        if not equal or not key:
            raise ArgumentError(token, "free form tokens are key=value")
        args[key] = value
    return args


def entry_prompt(entry: Entry) -> Text:
    """List line of an entry: name, effect mark and status."""
    text = Text(f"  {entry.name}")
    if entry.command is not None and entry.command.needs_confirmation:
        text.append(f" {MARK_EFFECT}", style="bold yellow")
    if entry.status is EntryStatus.FREE:
        text.append("  free", style="italic")
    elif entry.status is EntryStatus.ABSENT:
        text.append("  not in this firmware", style="italic")
    return text


class CommandsPane(Horizontal):
    """Command list on the left, form of the highlighted command on the right."""

    DEFAULT_CSS = """
    CommandsPane { height: auto; min-height: 12; }
    CommandsPane > OptionList { width: 34; border: round $primary; }
    CommandsPane > Vertical { border: round $primary; padding: 0 1; }
    CommandsPane #form { height: 1fr; }
    CommandsPane .field { height: auto; margin-top: 1; }
    CommandsPane .field Label { width: 10; padding: 0 1 0 0; }
    CommandsPane .field Input, CommandsPane .field Select { width: 1fr; }
    CommandsPane .error { color: $error; height: auto; }
    CommandsPane .note { color: $warning; }
    CommandsPane #result { height: auto; max-height: 8; border-top: solid $primary; }
    CommandsPane #actions { height: auto; }
    """

    class Send(Message):
        """Request to send: effect is destructive, reboots or None."""

        def __init__(self, name: str, args: dict, effect: str | None, free: bool):
            super().__init__()
            self.name = name
            self.args = args
            self.effect = effect
            self.free = free

    def __init__(self, catalog: Catalog, **kwargs):
        super().__init__(**kwargs)
        self.catalog = catalog
        self.entries = {}  # Name: Entry of the current list
        self.current = None  # Entry shown in the form
        self.enabled = False
        self.results = {}  # Name: rendered last result of that command

    def compose(self) -> ComposeResult:
        commands = OptionList(markup=False, id="commands")
        commands.border_title = "Commands"
        yield commands
        with Vertical() as right:
            right.border_title = "Form"
            yield VerticalScroll(id="form")  # Takes the free height: the lines below stay in view
            yield Static("", id="result")
            yield Static("", id="form-error", classes="error")
            with Horizontal(id="actions"):
                yield Checkbox("Free form", id="free", compact=True)
                yield Button("Send", id="send", variant="primary", disabled=True, compact=True)

    def on_mount(self) -> None:
        self.set_caps([])

    # Called by the application

    def set_caps(self, names: list) -> None:
        """Rebuild the list from a CAPS list; [] shows the catalogue alone, all grey."""
        entries = self.catalog.merge(names)
        self.entries = {entry.name: entry for entry in entries}
        groups = {}
        for entry in entries:
            group = entry.command.group if entry.command is not None else "Other"
            groups.setdefault(group, []).append(entry)
        options = []
        for group, members in groups.items():
            if options:
                options.append(None)  # Separator
            options.append(Option(Text(group, style="bold"), disabled=True))
            options += [Option(entry_prompt(entry), id=entry.name, disabled=entry.status is EntryStatus.ABSENT)
                        for entry in members]
        commands = self.query_one("#commands", OptionList)
        commands.clear_options()
        commands.add_options(options)
        keep = self.current.name if self.current is not None else None
        if keep in self.entries and self.entries[keep].status is not EntryStatus.ABSENT:
            commands.highlighted = commands.get_option_index(keep)
        else:
            first = next((entry for entry in entries if entry.status is not EntryStatus.ABSENT), None)
            if first is not None:
                commands.highlighted = commands.get_option_index(first.name)
            else:
                self.current = None
                self._refresh_form(None)

    def set_enabled(self, enabled: bool) -> None:
        """Send is active only in a connected session."""
        self.enabled = enabled
        self._update_send()

    def show_result(self, name: str, status: str, fields: dict, code: str | None = None) -> None:
        """Answer of a request: status, the code of an ERR, then every result field."""
        text = self._result_head(name)
        rows = [("status", status, "bold green" if status == "OK" else "bold red")]
        if code is not None:
            rows.append(("code", code, "bold red"))
        rows += [(key, str(value), "") for key, value in fields.items()]
        width = max(len(key) for key, _, _ in rows) + 2
        for key, value, style in rows:
            text.append(f"\n{key:<{width}}", style="dim")
            text.append(value, style=style)
        self._keep_result(name, text)

    def show_failure(self, name: str, message: str) -> None:
        """No answer for a request: timeout, reset or lost port."""
        text = self._result_head(name)
        text.append(f"\n{message}", style="bold red")
        self._keep_result(name, text)

    @staticmethod
    def _result_head(name: str) -> Text:
        return Text.assemble(("Result", "bold"), f"  {name}  ", (time.strftime("%H:%M:%S"), "dim"))

    def _keep_result(self, name: str, text: Text) -> None:
        self.results[name] = text
        if self.current is not None and self.current.name == name:
            self.query_one("#result", Static).update(text)

    # Form

    @on(OptionList.OptionHighlighted, "#commands")
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        entry = self.entries.get(event.option.id)
        if entry is not None and entry is not self.current:
            self.current = entry
            self._refresh_form(entry)

    @on(Checkbox.Changed, "#free")
    def _free_changed(self, event: Checkbox.Changed) -> None:
        if self.current is not None:
            prefill = self._typed_values() if event.value else None
            self._refresh_form(self.current, prefill)

    def _refresh_form(self, entry: Entry | None, free_prefill: dict | None = None) -> None:
        """Rebuild the form; a newer request cancels an older one not started yet."""
        self.run_worker(partial(self._show, entry, free_prefill), exclusive=True, group="form")

    async def _show(self, entry: Entry | None, free_prefill: dict | None = None) -> None:
        form = self.query_one("#form", VerticalScroll)
        await form.remove_children()
        self._set_error("")
        self.query_one("#result", Static).update(self.results.get(entry.name, "") if entry is not None else "")
        if entry is None:
            self._update_send()
            return
        free_box = self.query_one("#free", Checkbox)
        command = entry.command
        free = entry.status is EntryStatus.FREE or free_box.value
        free_box.disabled = entry.status is EntryStatus.FREE
        widgets = []
        if command is not None:
            title = Text(entry.name, style="bold")
            title.append(f"  {command.summary}  (protocol.md {command.spec})")
            widgets.append(Static(title))
            if command.effect:
                widgets.append(Static(f"{MARK_EFFECT} {command.effect}: asks for confirmation", classes="note"))
            if command.requires:
                widgets.append(Static(f"Send {command.requires} first", classes="note"))
        else:
            widgets.append(Static(Text(f"{entry.name}  not in the catalogue: free form", style="bold")))
        if free:
            values = free_prefill
            if values is None and command is not None:  # Free form chosen before: start from the defaults
                values = {arg.name: default_text(arg) for arg in command.args if default_text(arg)}
            values = values or {}
            line = " ".join(f"{key}={value}" for key, value in values.items())
            widgets.append(Horizontal(Label("args"), Input(line, placeholder="key=value ...", id="free-line",
                                                           compact=True), classes="field"))
        else:
            for arg in command.args:
                widgets.append(Horizontal(Label(arg.name), self._field(arg), classes="field"))
                widgets.append(Static("", id=f"err-{arg.name}", classes="error"))
            if not command.args:
                widgets.append(Static("No argument"))
        await form.mount_all(widgets)
        self._update_send()

    @staticmethod
    def _field(arg):
        if arg.type == "enum":
            values = arg.params["values"]
            default = arg.default if arg.default in values else values[0]
            return Select([(value, value) for value in values], value=default, allow_blank=False,
                          id=f"arg-{arg.name}", compact=True)
        return Input(default_text(arg), placeholder=hint(arg), id=f"arg-{arg.name}", compact=True)

    def _typed_values(self) -> dict:
        """Texts of the typed fields shown now, empty ones left out."""
        values = {}
        if self.current is None or self.current.command is None:
            return values
        for arg in self.current.command.args:
            found = self.query(f"#arg-{arg.name}")
            if not found:
                continue
            value = str(found.first().value).strip()
            if value:
                values[arg.name] = value
        return values

    # Send

    @on(Button.Pressed, "#send")
    @on(Input.Submitted)  # Enter in a field sends, as the button does
    def _send(self) -> None:
        entry = self.current
        if entry is None or not self.enabled:
            return
        for error in self.query(".error"):
            error.update("")
        free = bool(self.query("#free-line"))
        try:
            if free:
                args = parse_free(self.query_one("#free-line", Input).value)
            else:
                args = self.catalog.check(entry.name, self._typed_values())
        except ArgumentError as error:
            target = self.query(f"#err-{error.arg}")
            if target and not free:
                target.first().update(f"{error.arg}: {error.message}")
                self._set_error("Not sent: check the field above")
            else:
                self._set_error(f"Not sent: {error.arg}: {error.message}")
            return
        effect = entry.command.effect if entry.command is not None else None
        self.post_message(self.Send(entry.name, args, effect, free))

    def _set_error(self, text: str) -> None:
        self.query_one("#form-error", Static).update(text)

    def _update_send(self) -> None:
        self.query_one("#send", Button).disabled = not self.enabled or self.current is None
