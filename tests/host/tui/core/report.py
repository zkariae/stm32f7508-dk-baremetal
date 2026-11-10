"""Markdown and HTML report of a run, rebuilt from its folder (C4).

build(folder) reads the run folder written by core/runner.py (README.md
section 4.3) and export(folder) writes report.md and report.html next to it.
The report gives (section 4.4) the verdict, the totals, one line per test
with its outcome of tests/protocol.md section 7.3, the banner of the first
session on the board (the image under test; the unit tests of the fake
firmware log banners too, but no session line), the Git
commit and the bench.yaml used, the timeouts that differ from section 8.1,
and for each failure the last request and the records received for it
(section 8.4).

  - events.jsonl is always read again; the totals are counted with Totals,
    as junit.xml counts. A line cut by a kill is skipped and named.
  - run.json gives the kind, the selection, the commit and the verdict. A
    run killed before its end has no verdict there: the report is then
    rebuilt from events.jsonl and marked INTERRUPTED, never PASS.
  - A test started without any report did not run to its end: it is listed
    as not finished and not counted.
  - The last request of a failure is its last TX line, with the RX lines
    after it; a scenario step has no TX line in events.jsonl, its label is
    the request.
  - Timeouts: the startup and response values of the bench.yaml copied in
    the folder, against 5 s and 2 s. A timeout changed in the code of a test
    (test_protocol_recovery.py) is not in the folder and is not shown.

The page is one file: no script, no external resource, every text escaped.
Command line, for a run killed with the TUI (no port, no board):

    python3 tests/host/tui/core/report.py work/hil-results/<run>

No Textual import.

Version: 1.0
Date: 10/11/2026
Author: Z. BEN-AKKA
History:
  1.0  10/11/2026  Initial version.
"""

import argparse
import html
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):  # Run as a script: core/ is then not on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from core.runner import Totals  # noqa: E402

PROTOCOL_TIMEOUTS = {"startup": 5.0, "response": 2.0}  # tests/protocol.md section 8.1, HELLO and CAPS
SESSION_STARTED = "session started: "  # adapters/board.py, one line per session on the board
INTERRUPTED = "INTERRUPTED"
NOT_FINISHED = "NOT_FINISHED"
MAX_RECORDS = 20  # Records shown per failure
OK_OUTCOMES = ("PASS", "SKIPPED")
KIND_TITLES = {"pytest": "pytest", "rx_check": "UART RX T1-T8", "scenario": "Scenario"}
EXIT_USAGE = 2


@dataclass
class TestLine:
    """One test: its outcome is the hil_outcome of its first failed phase, else PASS or SKIPPED."""

    nodeid: str
    label: str = ""
    outcome: str = NOT_FINISHED
    duration: float = 0.0
    message: str = ""
    finished: bool = False


@dataclass
class Failure:
    nodeid: str
    outcome: str
    message: str
    request: str | None
    records: list


@dataclass
class Report:
    folder: Path
    kind: str = "pytest"
    selection: list = field(default_factory=list)
    verdict: str = INTERRUPTED
    rebuilt: bool = False  # run.json had no verdict: the run was killed
    exitstatus: int | None = None
    forced: bool = False
    totals: dict = field(default_factory=dict)
    started: float | None = None
    ended: float | None = None
    commit: str = ""
    bench: str = ""
    banner: str = ""
    overrides: list = field(default_factory=list)  # (name, value, protocol value)
    tests: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    bad_lines: list = field(default_factory=list)  # Line numbers of events.jsonl that are not JSON

    @property
    def title(self) -> str:
        what = " ".join(Path(item).name if self.kind == "scenario" else item for item in self.selection)
        return f"{KIND_TITLES.get(self.kind, self.kind)}: {what or 'whole suite'}"

    @property
    def outcomes(self) -> Counter:
        return Counter(test.outcome for test in self.tests)


# Build

class ReportError(Exception):
    """The folder is not a run folder."""


def build(folder: Path | str) -> Report:
    folder = Path(folder)
    events_path = folder / "events.jsonl"
    if not events_path.is_file():
        raise ReportError(f"{folder}: no events.jsonl, not a run folder")
    meta = _read_meta(folder / "run.json")
    report = Report(folder=folder, kind=meta.get("kind", "pytest"), selection=list(meta.get("selection") or []),
                    started=meta.get("started"), ended=meta.get("ended"), commit=meta.get("commit", ""),
                    bench=meta.get("bench", ""), exitstatus=meta.get("exitstatus"),
                    forced=bool(meta.get("forced", False)))
    events = _read_events(events_path, report.bad_lines)
    totals, tests, logs = Totals(), {}, {}
    for event in events:
        kind, nodeid = event.get("event"), event.get("nodeid")
        if kind == "test_start" and nodeid:
            tests.setdefault(nodeid, TestLine(nodeid, label=str(event.get("label", ""))))
        elif kind == "report" and nodeid:
            totals.add(event)
            _add_phase(tests.setdefault(nodeid, TestLine(nodeid)), event)
        elif kind == "log":
            text = str(event.get("text", ""))
            if nodeid:
                logs.setdefault(nodeid, []).append(text)
            if not report.banner and event.get("logger") == "hil.board" and text.startswith(SESSION_STARTED):
                report.banner = text[len(SESSION_STARTED):]
        elif kind == "session_end" and report.exitstatus is None:
            report.exitstatus = event.get("exitstatus")
    if report.started is None and events:
        report.started = events[0].get("t")
    if report.ended is None and events:
        report.ended = events[-1].get("t")
    report.totals = totals.counts()
    report.tests = list(tests.values())
    report.failures = [_failure(test, logs.get(test.nodeid, [])) for test in report.tests
                       if test.finished and test.outcome not in OK_OUTCOMES]
    report.verdict = meta.get("verdict") or INTERRUPTED
    report.rebuilt = not meta.get("verdict")
    report.overrides = _overrides(folder / "bench.yaml")
    return report


def _read_meta(path: Path) -> dict:
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # Killed before run.json was written, or cut while written
    return meta if isinstance(meta, dict) else {}


def _read_events(path: Path, bad_lines: list) -> list:
    events = []
    with open(path, encoding="utf-8", errors="replace") as stream:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                bad_lines.append(number)  # Cut by a kill while written
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _add_phase(test: TestLine, event: dict) -> None:
    test.finished = True
    test.duration += float(event.get("duration") or 0.0)
    outcome = str(event.get("hil_outcome") or "BENCH_ERROR")
    # The first failed phase decides; a skip only replaces a pass
    message = str(event.get("message") or "")
    if test.outcome in (NOT_FINISHED, "PASS") or (test.outcome == "SKIPPED" and outcome not in OK_OUTCOMES):
        test.outcome = outcome
        test.message = message
    elif outcome not in OK_OUTCOMES:  # A later failed phase (teardown) is counted as an error: name it too
        test.message += f"; {event.get('when', '')}: {outcome} {message}".rstrip()


def _failure(test: TestLine, lines: list) -> Failure:
    last = max((index for index, text in enumerate(lines) if text.startswith("TX  ")), default=None)
    if last is None:
        request, records = (test.label or None), []
    else:
        request = lines[last][len("TX  "):]
        records = [text[len("RX  "):] for text in lines[last + 1:] if text.startswith("RX  ")]
    return Failure(test.nodeid, test.outcome, test.message, request, records[:MAX_RECORDS])


def _overrides(path: Path) -> list:
    try:
        bench = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        timeouts = bench.get("timeouts") or {}
    except (OSError, yaml.YAMLError, AttributeError):
        return []
    found = []
    for name, protocol in PROTOCOL_TIMEOUTS.items():
        value = timeouts.get(name)
        try:
            if value is not None and float(value) != protocol:
                found.append((name, float(value), protocol))
        except (TypeError, ValueError):
            found.append((name, value, protocol))
    return found


# Text

def _when(moment: float | None) -> str:
    if moment is None:
        return "not recorded"
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(moment))


def _length(report: Report) -> str:
    if report.started is None or report.ended is None:
        return "not recorded"
    return f"{report.ended - report.started:.1f} s"


def _summary(report: Report) -> list:
    """(label, value) rows of the head table."""
    return [("Verdict", report.verdict), ("Run", report.title), ("Folder", str(report.folder)),
            ("Started", _when(report.started)), ("Duration", _length(report)),
            ("Exit status", "not recorded" if report.exitstatus is None else str(report.exitstatus)),
            ("Git commit", report.commit or "not recorded"), ("bench.yaml", report.bench or "not recorded"),
            ("Banner", report.banner or "not recorded")]


def _notes(report: Report) -> list:
    notes = []
    if report.rebuilt:
        notes.append("Rebuilt from events.jsonl: the run ended before writing its verdict (killed).")
    if report.verdict == INTERRUPTED:
        notes.append("Interrupted: only the tests that ran are counted.")
    if report.forced:
        notes.append("Stop forced during a flash: the board image is unknown.")
    unfinished = [test.nodeid for test in report.tests if not test.finished]
    if unfinished:
        notes.append(f"Not finished, not counted: {', '.join(unfinished)}.")
    if report.bad_lines:
        notes.append(f"events.jsonl lines skipped (not JSON): {', '.join(map(str, report.bad_lines))}.")
    return notes


def _timeouts(report: Report) -> list:
    if not report.overrides:
        return ["None: startup 5 s and response 2 s of tests/protocol.md section 8.1."]
    return [f"{name}: {value} s (protocol {protocol} s)" for name, value, protocol in report.overrides]


TIMEOUTS_LIMIT = "Timeouts changed in the code of a test are not recorded in the run folder."


def _md(text) -> str:
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def to_markdown(report: Report) -> str:
    lines = [f"# Test report: {report.title}", "", "| | |", "|:--|:--|"]
    lines += [f"| {label} | {_md(value)} |" for label, value in _summary(report)]
    lines.append("")
    lines += [f"> {note}" for note in _notes(report)]
    lines += ["", "## Totals", "", "| Tests | Passed | Failed | Errors | Skipped |", "|--:|--:|--:|--:|--:|"]
    totals = report.totals
    lines.append(" | ".join(["", *(str(totals.get(key, 0)) for key in ("tests", "passed", "failed", "errors",
                                                                       "skipped")), ""]).strip())
    outcomes = ", ".join(f"{outcome} {count}" for outcome, count in sorted(report.outcomes.items()))
    lines += ["", f"Outcomes: {outcomes or 'none'}", "", "## Timeouts", ""]
    lines += [f"- {line}" for line in _timeouts(report)] + ["", TIMEOUTS_LIMIT, "", "## Tests", ""]
    if report.tests:
        lines += ["| # | Test | Outcome | Duration | Message |", "|--:|:--|:--|--:|:--|"]
        for number, test in enumerate(report.tests, start=1):
            name = test.nodeid + (f" ({test.label})" if test.label else "")
            lines.append(f"| {number} | {_md(name)} | {test.outcome} | {test.duration:.2f} s | {_md(test.message)} |")
    else:
        lines.append("No test ran.")
    lines += ["", "## Failures", ""]
    if not report.failures:
        lines.append("None.")
    for failure in report.failures:
        lines += [f"### {failure.nodeid}: {failure.outcome}", ""]
        if failure.message:
            lines += [failure.message, ""]
        lines += [f"Last request: `{failure.request}`" if failure.request else "Last request: none recorded", ""]
        if failure.records:
            lines += ["```", *failure.records, "```", ""]
        elif failure.request:
            lines += ["No record received for it.", ""]
    return "\n".join(lines).rstrip() + "\n"


CSS = """
:root { --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0; --head: #f6f8fa;
        --pass: #1a7f37; --fail: #cf222e; --skip: #9a6700; --stop: #8250df; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #3d444d; --head: #151b23;
          --pass: #3fb950; --fail: #f85149; --skip: #d29922; --stop: #ab7df8; }
}
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 1100px; padding: 16px;
       font: 14px/1.5 system-ui, sans-serif; }
h1 { font-size: 22px; } h2 { font-size: 18px; margin-top: 28px; } h3 { font-size: 15px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border: 1px solid var(--line); padding: 4px 8px; text-align: left; vertical-align: top;
         overflow-wrap: anywhere; }
th { background: var(--head); }
td.num { text-align: right; white-space: nowrap; }
.PASS { color: var(--pass); font-weight: 600; } .SKIPPED { color: var(--skip); font-weight: 600; }
.INTERRUPTED, .NOT_FINISHED { color: var(--stop); font-weight: 600; }
.bad { color: var(--fail); font-weight: 600; }
.note { border-left: 4px solid var(--stop); padding: 4px 10px; margin: 6px 0; background: var(--head); }
.muted { color: var(--muted); }
pre { background: var(--head); border: 1px solid var(--line); padding: 8px; overflow-x: auto; }
code { font-family: ui-monospace, monospace; }
"""


def _cls(outcome: str) -> str:
    return outcome if outcome in ("PASS", "SKIPPED", INTERRUPTED, NOT_FINISHED) else "bad"


def to_html(report: Report) -> str:
    e = html.escape
    out = ["<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>Test report: {e(report.title)}</title>", f"<style>{CSS}</style>", "</head>", "<body>",
           f"<h1>Test report: {e(report.title)}</h1>", "<table>"]
    for label, value in _summary(report):
        cell = f'<span class="{_cls(value)}">{e(value)}</span>' if label == "Verdict" else e(value)
        out.append(f"<tr><th>{e(label)}</th><td>{cell}</td></tr>")
    out.append("</table>")
    out += [f'<p class="note">{e(note)}</p>' for note in _notes(report)]
    totals = report.totals
    out += ["<h2>Totals</h2>", "<table><tr><th>Tests</th><th>Passed</th><th>Failed</th><th>Errors</th>"
            "<th>Skipped</th></tr><tr>"]
    out += [f'<td class="num">{totals.get(key, 0)}</td>' for key in ("tests", "passed", "failed", "errors",
                                                                     "skipped")]
    out.append("</tr></table>")
    outcomes = ", ".join(f'<span class="{_cls(outcome)}">{e(outcome)}</span> {count}'
                         for outcome, count in sorted(report.outcomes.items()))
    out += [f"<p>Outcomes: {outcomes or 'none'}</p>", "<h2>Timeouts</h2>", "<ul>"]
    out += [f"<li>{e(line)}</li>" for line in _timeouts(report)]
    out += ["</ul>", f'<p class="muted">{e(TIMEOUTS_LIMIT)}</p>', "<h2>Tests</h2>"]
    if report.tests:
        out.append("<table><tr><th>#</th><th>Test</th><th>Outcome</th><th>Duration</th><th>Message</th></tr>")
        for number, test in enumerate(report.tests, start=1):
            label = f' <span class="muted">({e(test.label)})</span>' if test.label else ""
            out.append(f'<tr><td class="num">{number}</td><td><code>{e(test.nodeid)}</code>{label}</td>'
                       f'<td class="{_cls(test.outcome)}">{e(test.outcome)}</td>'
                       f'<td class="num">{test.duration:.2f} s</td><td>{e(test.message)}</td></tr>')
        out.append("</table>")
    else:
        out.append("<p>No test ran.</p>")
    out.append("<h2>Failures</h2>")
    if not report.failures:
        out.append("<p>None.</p>")
    for failure in report.failures:
        out.append(f'<h3><code>{e(failure.nodeid)}</code>: <span class="bad">{e(failure.outcome)}</span></h3>')
        if failure.message:
            out.append(f"<p>{e(failure.message)}</p>")
        out.append(f"<p>Last request: <code>{e(failure.request)}</code></p>" if failure.request
                   else "<p>Last request: none recorded</p>")
        if failure.records:
            out.append("<pre>" + e("\n".join(failure.records)) + "</pre>")
        elif failure.request:
            out.append("<p>No record received for it.</p>")
    out += ["</body>", "</html>"]
    return "\n".join(out) + "\n"


def export(folder: Path | str) -> tuple:
    """Write report.md and report.html in the run folder; returns their paths."""
    report = build(folder)
    markdown, page = report.folder / "report.md", report.folder / "report.html"
    markdown.write_text(to_markdown(report), encoding="utf-8")
    page.write_text(to_html(report), encoding="utf-8")
    return markdown, page


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write report.md and report.html of a run folder.")
    parser.add_argument("folder", type=Path, help="run folder, e.g. work/hil-results/<date-time>-<suite>")
    args = parser.parse_args(argv)
    try:
        paths = export(args.folder)
    except (ReportError, OSError) as error:
        print(f"report: {error}", file=sys.stderr)
        return EXIT_USAGE
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
