# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       cd/docker/Dockerfile
# \brief      Flasher image: OpenOCD and the files of one release.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       16/11/2026
#
# \details
#   Image ghcr.io/zkariae/stm32f7508-dk-flasher (cd/README.md section 5.5).
#   The build context is the release folder written by package.sh, which
#   holds only the delivered files, so no .dockerignore is needed; this file
#   is given with -f from outside that folder:
#     docker build -f cd/docker/Dockerfile --build-arg VERSION=X.Y.Z \
#       -t ghcr.io/zkariae/stm32f7508-dk-flasher:X.Y.Z \
#       work/release/stm32f7508-dk-baremetal-release-vX.Y.Z
#   The entry point is flash.sh: its options follow the image name.
#     docker run --rm -it --device /dev/bus/usb <image> [--yes] [--dry-run]
#   OpenOCD is the Ubuntu 22.04 package, 0.11.0, the version of the CI;
#   flash.sh refuses anything older.
#
# \section dockerfile_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 16/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

FROM ubuntu:22.04

# X.Y.Z of the release-vX.Y.Z tag, given by the CD job
ARG VERSION=unknown

# source links the GHCR package to the repository
LABEL org.opencontainers.image.source="https://github.com/zkariae/stm32f7508-dk-baremetal" \
      org.opencontainers.image.description="Flash a release of stm32f7508-dk-baremetal to the STM32F7508-DK" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends openocd \
 && rm -rf /var/lib/apt/lists/*

COPY . /release
WORKDIR /release

ENTRYPOINT ["/release/flash.sh"]
