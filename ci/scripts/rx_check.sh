#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       rx_check.sh
# \brief      Run the UART T1-T8 checks on the board.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       03/11/2026
#
# \details
#   UART T1-T8 stage of the Jenkins pipeline (ci/README.md section 4), also
#   run by hand with the board connected. Flashes the uart-diag image, resets
#   the board, then runs tests/host/rx_check/uart_rx_check.py. Returns its
#   exit code: 0 all passed, 1 a test failed, 2 configuration or serial error.
#
#     ci/scripts/rx_check.sh                   T1-T8, port from bench.yaml (Jenkins)
#     ci/scripts/rx_check.sh --only T1 T3      arguments go to uart_rx_check.py
#
#   Can be run from any folder: it moves to the repository root.
#
# \section rx_check_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 03/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# uart_rx_check.py does not flash: the board may still run hil-bench
echo "rx_check.sh: make uart-diag-flash"
make uart-diag-flash

echo "rx_check.sh: make reset"
make reset

echo "rx_check.sh: T1-T8"
python3 tests/host/rx_check/uart_rx_check.py "$@"

echo "rx_check.sh: all checks passed"
