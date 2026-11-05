#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       build.sh
# \brief      Run the CI checks that need no board.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       03/11/2026
#
# \details
#   Build stage of the Jenkins pipeline (ci/README.md section 4), also run by
#   hand before pushing a branch. Builds every image, checks the C format,
#   runs the host unit tests against the fake firmware and collects the HIL
#   tests without running them. Stops at the first failing check with a
#   non-zero exit code.
#
#     ci/scripts/build.sh           keep work/build/ from previous builds
#     ci/scripts/build.sh --clean   run make clean first (Jenkins)
#
#   Can be run from any folder: it moves to the repository root.
#
# \section build_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 03/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ "${1:-}" == "--clean" ]]; then
  echo "build.sh: make clean"
  make clean
fi

echo "build.sh: make all"
make all

echo "build.sh: format check"
dev/scripts/format_cxx.sh --check

# Adapters against the fake firmware (tests/host/hil/unit), no board
echo "build.sh: unit tests"
python3 -m pytest tests/host/hil -m unit -q

# Imports every test file and expands the parametrize lists, runs nothing
echo "build.sh: test collection"
python3 -m pytest tests/host/hil --collect-only -q

echo "build.sh: all checks passed"
