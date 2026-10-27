"""pytest root configuration of the HIL protocol tests.

Loads the board fixtures plugin, which adds the --bench-config, --port and
--no-flash options and the board session fixture. pyproject.toml puts this
folder on the import path, so the plugin and the adapters import from here.

Version: 1.0
Date: 26/10/2026
Author: Z. BEN-AKKA
History:
  1.0  26/10/2026  Initial version.
"""

pytest_plugins = ["fixtures.board_fixtures"]
