"""Build, flash and reset the board through the repository Makefile.

The recipes stay in the Makefile and the board's board.mk: this module only
runs make <firmware>-flash, make <reset> and make <reset-sw>. A failing or
hanging make call raises ProgrammingFailure (protocol.md section 7.3). On the
hil.programmer logger, each make command is logged at INFO (shown live with
pytest --log-cli-level=INFO) and its output at DEBUG (log file only).
build_id() reads the hil_build.h of the image, the build the readiness banner
reports.

Version: 1.2
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
  1.1  26/10/2026  Log each make command at INFO for live display.
  1.2  26/10/2026  Add the software reset (make reset-sw).
"""

import logging
import re
import subprocess
from pathlib import Path

from adapters.outcomes import ProgrammingFailure

OUTPUT_TAIL_LINES = 15  # make output lines kept in a failure message

log = logging.getLogger("hil.programmer")


class Programmer:
    """make targets of one firmware image."""

    def __init__(self, repo_root: Path, board: str, firmware_target: str, reset_target: str, timeout: float,
                 reset_sw_target: str | None = None):
        self.repo_root = Path(repo_root)
        self.board = board
        self.firmware_target = firmware_target
        self.reset_target = reset_target
        self.timeout = timeout
        self.reset_sw_target = reset_sw_target  # None: no software reset on this bench

    def flash(self) -> None:
        """Build the image if needed and program it; the board then boots it."""
        self._make(f"{self.firmware_target}-flash")

    def reset(self) -> None:
        """Reset the board without reprogramming it."""
        self._make(self.reset_target)

    def reset_sw(self) -> None:
        """Software reset (SYSRESETREQ): the banner then reports reset=SW."""
        if self.reset_sw_target is None:
            raise ProgrammingFailure("no software reset target in the bench configuration")
        self._make(self.reset_sw_target)

    def build_id(self) -> str | None:
        """HIL_BUILD_ID of the last build of the image, or None if it was never built."""
        header = self.repo_root / "work" / "build" / self.board / self.firmware_target / "hil_build.h"
        if not header.is_file():
            return None
        match = re.search(r'#define HIL_BUILD_ID "([^"]*)"', header.read_text(encoding="ascii"))
        return match.group(1) if match else None

    def _make(self, target: str) -> None:
        command = ["make", "--no-print-directory", "-C", str(self.repo_root), target]
        log.info("RUN make %s", target)
        log.debug("RUN %s", " ".join(command))
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            raise ProgrammingFailure(f"make {target} did not finish within {self.timeout} s") from None
        except OSError as error:
            raise ProgrammingFailure(f"make {target} could not start: {error}") from None
        output = (done.stdout + done.stderr).strip()
        for line in output.splitlines():
            log.debug("make %s: %s", target, line)
        if done.returncode != 0:
            tail = "\n".join(output.splitlines()[-OUTPUT_TAIL_LINES:])
            raise ProgrammingFailure(f"make {target} failed (exit {done.returncode}):\n{tail}")
