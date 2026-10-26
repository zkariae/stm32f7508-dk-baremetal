"""pytest plugin: bench configuration, log file and the board session fixture.

Loaded by tests/host/hil/conftest.py. Options:
  --bench-config FILE  bench configuration (default: tests/host/config/bench.yaml)
  --port PORT          serial port (default: serial.port in the bench configuration)
  --no-flash           test the image already on the board
The pytest log file goes to <results_dir>/pytest.log unless --log-file is
given. The board fixture is shared by the whole session: it flashes the
image, opens the port, waits for the readiness banner, then checks HELLO and
CAPS, so every test starts from an identified board (protocol.md section 3.4).

Version: 1.0
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
"""

import logging
import time
from pathlib import Path

import pytest
import yaml

from adapters.board import Board
from adapters.programmer import Programmer
from adapters.serial_adapter import SerialAdapter

HIL_DIR = Path(__file__).resolve().parents[1]
HOST_DIR = HIL_DIR.parent
REPO_ROOT = HOST_DIR.parents[1]
DEFAULT_CONFIG = HOST_DIR / "config" / "bench.yaml"
SUPPORTED_SCHEMA = 1

BENCH_KEY = pytest.StashKey[dict]()

log = logging.getLogger("hil.fixtures")


def pytest_addoption(parser):
    group = parser.getgroup("hil", "HIL bench")
    group.addoption("--bench-config", type=Path, default=DEFAULT_CONFIG, help="bench configuration file")
    group.addoption("--port", default=None, help="serial port (default: serial.port in the bench configuration)")
    group.addoption("--no-flash", action="store_true", help="test the image already on the board")


def load_bench_config(path: Path) -> dict:
    """Load the bench configuration; a missing key is a usage error."""
    try:
        with Path(path).open(encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        if not isinstance(config, dict) or config.get("schema_version") != SUPPORTED_SCHEMA:
            raise ValueError(f"schema_version must be {SUPPORTED_SCHEMA}")
        for section, keys in {
            "serial": ("port", "baudrate", "bytesize", "parity", "stopbits", "flow_control"),
            "timeouts": ("startup", "response", "make"),
            "delays": ("port_open_settle",),
            "hardware": ("board", "firmware_target", "reset_target"),
            "firmware": ("expected_build", "accept_build_mismatch"),
        }.items():
            missing = [key for key in keys if key not in config.get(section, {})]
            if missing:
                raise ValueError(f"missing {section}.{', '.join(missing)}")
        if "results_dir" not in config:
            raise ValueError("missing results_dir")
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise pytest.UsageError(f"bench configuration {path}: {error}") from None
    return config


def pytest_configure(config):
    bench = load_bench_config(config.getoption("bench_config"))
    config.stash[BENCH_KEY] = bench
    if not config.getoption("log_file", None):
        results = REPO_ROOT / bench["results_dir"]
        results.mkdir(parents=True, exist_ok=True)
        config.option.log_file = str(results / "pytest.log")  # Read by the logging plugin, configured last


@pytest.fixture(scope="session")
def bench_config(pytestconfig) -> dict:
    """The bench configuration of this run."""
    return pytestconfig.stash[BENCH_KEY]


def _expected_build(bench: dict, programmer: Programmer) -> str | None:
    """Build the firmware must report: the flashed image's for auto, else the configured value."""
    expected = bench["firmware"]["expected_build"]
    if expected == "auto":
        expected = programmer.build_id()
        if expected is None:
            log.warning("expected_build auto: no hil_build.h, build not checked")
    return None if expected is None else str(expected)


@pytest.fixture(scope="session")
def board(pytestconfig, bench_config) -> Board:
    """An identified board: flashed (unless --no-flash), banner received, HELLO and CAPS checked."""
    hardware = bench_config["hardware"]
    timeouts = bench_config["timeouts"]
    settle = bench_config["delays"]["port_open_settle"]

    programmer = Programmer(REPO_ROOT, hardware["board"], hardware["firmware_target"], hardware["reset_target"],
                            timeouts["make"])
    if not pytestconfig.getoption("no_flash"):
        programmer.flash()

    with SerialAdapter.open(bench_config["serial"], timeouts["response"], pytestconfig.getoption("port")) as adapter:
        time.sleep(settle)  # Let the serial adapter settle after opening
        hil_board = Board(adapter, programmer, timeouts["startup"], settle,
                          _expected_build(bench_config, programmer),
                          bench_config["firmware"]["accept_build_mismatch"])
        hil_board.start_session()
        hil_board.identify()
        hil_board.capabilities()
        yield hil_board
