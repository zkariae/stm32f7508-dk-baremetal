"""Entry point of the HIL bench TUI (C1).

Runs from any folder:

    python3 tests/host/tui/hil_tui.py
    python3 tests/host/tui/hil_tui.py --port /dev/ttyACM1
    python3 tests/host/tui/hil_tui.py --bench my_bench.yaml --catalog my_commands.yaml

--port overrides the port of bench.yaml; --bench and --catalog default to
tests/host/config/bench.yaml and tests/host/config/commands.yaml. A missing
Textual, an unusable bench.yaml or an invalid catalogue stops here with one
line on stderr and exit code 2, before the screen opens. A busy or missing
port is not an error at this level: the TUI opens DISCONNECTED and says what
to do.

Version: 1.0
Date: 09/11/2026
Author: Z. BEN-AKKA
History:
  1.0  09/11/2026  Initial version.
"""

import argparse
import sys
from pathlib import Path

_TUI_DIR = Path(__file__).resolve().parent
if str(_TUI_DIR) not in sys.path:
    sys.path.insert(0, str(_TUI_DIR))  # core/ and ui/, whatever the current folder

TEXTUAL_VERSION = "8.2.8"
EXIT_USAGE = 2


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="hil_tui.py", description="TUI of the HIL bench")
    parser.add_argument("--port", help="serial port, instead of the one of bench.yaml")
    parser.add_argument("--bench", type=Path, help="bench configuration (default tests/host/config/bench.yaml)")
    parser.add_argument("--catalog", type=Path,
                        help="command catalogue (default tests/host/config/commands.yaml)")
    return parser.parse_args(argv)


def fail(message: str) -> int:
    print(f"hil_tui.py: {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        import textual  # noqa: F401  Checked first, for a clear message
    except ImportError:
        return fail(f"Textual is missing: python3 -m pip install --user textual=={TEXTUAL_VERSION}")

    from core.catalog import CatalogError, load
    from core.session import SessionError, load_bench
    from ui.app import HilApp

    try:
        bench = load_bench(args.bench)
    except SessionError as error:
        return fail(str(error))  # Already names the file
    try:
        catalog = load(args.catalog)
    except CatalogError as error:
        return fail(f"catalogue: {error}")
    HilApp(bench, catalog, port=args.port).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
