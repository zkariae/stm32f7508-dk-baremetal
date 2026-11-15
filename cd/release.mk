# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       cd/release.mk
# \brief      Release manifest: the delivered application and its images.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       15/11/2026
#
# \details
#   Names the one application a release delivers (cd/README.md section 5.1),
#   and gives the CD scripts what they need to know about it. Not included
#   by the root Makefile: it is read after it, from the repository root,
#     make -f Makefile -f cd/release.mk <target>
#   so that the images, their order and their memories come from the
#   Makefile (<app>_IMAGES, <image>_MEMORY, <image>_BIN), and the address and
#   OpenOCD options from the board (MEMORY_<m>_ADDR, MEMORY_<m>_OPENOCD).
#   Nothing is written twice. RELEASE_APP can be set on the command line to
#   check another application; a test image or an unknown name is an error.
#     release-app        print the delivered application
#     release-build      build its images
#     release-bins       print the paths of its binaries, in flashing order
#     release-manifest   print images.txt: one line per image, in flashing order
#
# \section cd_release_mk_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 15/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

####################################################################
# Delivered application
####################################################################

RELEASE_APP := 07-lcd-logo

# Any application of dev/apps/, never a test image (hil-bench, uart-diag)
RELEASE_APPS := $(SINGLE) $(MULTI)

ifeq ($(strip $(RELEASE_APPS)),)
$(error cd/release.mk is read after the root Makefile: make -f Makefile -f cd/release.mk <target>)
endif
ifneq ($(words $(RELEASE_APP)),1)
$(error RELEASE_APP must name one application, got "$(RELEASE_APP)")
endif
ifeq ($(filter $(RELEASE_APP),$(RELEASE_APPS)),)
$(error RELEASE_APP=$(RELEASE_APP) is not a deliverable application: one of $(RELEASE_APPS))
endif

# In flashing order: the QSPI application before its bootloader
RELEASE_IMAGES := $($(RELEASE_APP)_IMAGES)

####################################################################
# Targets
####################################################################

# One line of images.txt. $(1): image
release_line = $(1) images/$(1).bin $($(1)_MEMORY) $(MEMORY_$($(1)_MEMORY)_ADDR) $(MEMORY_$($(1)_MEMORY)_OPENOCD)

.PHONY: release-app
release-app:
	@echo $(RELEASE_APP)

.PHONY: release-build
release-build: $(RELEASE_APP)

.PHONY: release-bins
release-bins:
	@printf '%s\n' $(foreach i,$(RELEASE_IMAGES),$($(i)_BIN))

# The OpenOCD options are the rest of the line: flash.sh and flash.bat read
# the first four fields, then pass what is left to openocd
.PHONY: release-manifest
release-manifest:
	@printf '%s\n' '# image file memory address openocd-options' $(foreach i,$(RELEASE_IMAGES),'$(call release_line,$(i))')
