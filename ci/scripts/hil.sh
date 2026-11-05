#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       hil.sh
# \brief      Run the HIL protocol tests on the board.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       03/11/2026
#
# \details
#   HIL stage of the Jenkins pipeline (ci/README.md section 4), also run by
#   hand with the board connected. Runs the pytest suite of tests/host/hil,
#   whose session flashes hil-bench and resets the board, and writes the
#   JUnit report work/hil-results/junit.xml. Returns the pytest exit code.
#
#     ci/scripts/hil.sh                      every test (Jenkins)
#     ci/scripts/hil.sh -m smoke --no-flash  arguments go to pytest
#
#   Can be run from any folder: it moves to the repository root.
#
# \section hil_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 03/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# No make hil-bench-flash here: the pytest session flashes and resets the board
echo "hil.sh: HIL tests"
python3 -m pytest tests/host/hil --junitxml=work/hil-results/junit.xml "$@"

echo "hil.sh: all checks passed"
