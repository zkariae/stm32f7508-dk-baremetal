# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       Makefile
# \brief      Build, flash and document project images for a board.
#
# \author     Z. BEN-AKKA
# \version    1.8
# \date       22/10/2026
#
# \details
#   Says what to build: the applications, their sources, modules and
#   memories, and the project-wide compiler options. It also declares the
#   two test images: hil-bench, the HIL protocol firmware from
#   tests/firmware/hil_bench/, and uart-diag, the UART driver diagnostic from
#   tests/firmware/uart_diag/. How to build and program the images is the
#   board's: $(BOARD)/board.mk provides the toolchain, the memories and the
#   recipes (board_compile, board_link, board_flash...) that the rules below
#   only call. Applications and test images are declared as images; the rules
#   for every image come from the IMAGE template. Both test images link the
#   shared GPIO, UART and LED modules. hil-bench also gets hil_build.h, the
#   git revision it was built from, for its readiness banner.
#     make 01-blink            build one application
#     make 01-blink-flash      build and flash it with the ST-LINK
#     make BOARD=<name> ...    build for another board folder
#     make help                everything else
#
# \section root_makefile_version_history Version history
# | Version | Date       | Author      | Description                                                 |
# |:-------:|:----------:|:------------|:------------------------------------------------------------|
# | 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                                            |
# | 1.1     | 11/10/2026 | Z. BEN-AKKA | dev/ and board folders; BOARD selects the board.            |
# | 1.2     | 11/10/2026 | Z. BEN-AKKA | Applications and build rules here, the board in board.mk.   |
# | 1.3     | 11/10/2026 | Z. BEN-AKKA | Recipes come from board.mk; this file only calls them.      |
# | 1.4     | 14/10/2026 | Z.BEN-AKKA  | Add the HIL bench firmware image.                           |
# | 1.5     | 16/10/2026 | Z. BEN-AKKA | Link GPIO and UART modules into the HIL bench image.        |
# | 1.6     | 21/10/2026 | Z. BEN-AKKA | Link the LED module into the HIL bench image for T7.        |
# | 1.7     | 22/10/2026 | Z. BEN-AKKA | Add the uart-diag image for the UART RX checks.             |
# | 1.8     | 22/10/2026 | Z. BEN-AKKA | Generate the hil-bench build ID from the git revision.      |
# ****************************
# */

####################################################################
# Board
####################################################################

# Board to build for: a board folder (submodule) at the repository root
BOARD     ?= stm32f7508-dk
BOARD_DIR := $(BOARD)

DEV      := dev
APPS_DIR := $(DEV)/apps
TOOLS    := $(DEV)/tools
BUILD    := work/build/$(BOARD)

# Project-wide compiler options, added to the board's (CPU, -I for mcu.h and
# board.h): warnings, optimisation, the drivers, header dependency tracking
PROJECT_CFLAGS := -Wall -Wextra -O2 -g3 -I$(DEV)/common -MMD -MP

ifeq ($(wildcard $(BOARD_DIR)/board.mk),)
$(error $(BOARD_DIR)/board.mk not found: run "git submodule update --init", or set BOARD)
endif
include $(BOARD_DIR)/board.mk

.DEFAULT_GOAL := help

####################################################################
# Applications
####################################################################

# One image each, named after the application. <image>_MODULES lists the
# dev/common/<module>/<module>.c files it links, on top of the board sources.
# <image>_MEMORY picks one of the board's memories (default: the board's).
SINGLE := 01-blink 02-clock 03-uart 04-lcd-backlight 05-lcd-init 06-lcd-layer 07-lcd-logo
$(foreach a,$(SINGLE),$(eval $(a)_IMAGES := $(a)))
$(foreach a,$(SINGLE),$(eval $(a)_SRCS := $(APPS_DIR)/$(a)/main.c))

01-blink_MODULES         := delay gpio led
02-clock_MODULES         := delay gpio led rcc
03-uart_MODULES          := delay gpio led rcc uart
04-lcd-backlight_MODULES := delay gpio led rcc uart
05-lcd-init_MODULES      := delay gpio ltdc rcc uart
06-lcd-layer_MODULES     := delay fb gpio ltdc rcc uart
07-lcd-logo_MODULES      := delay fb gpio ltdc rcc uart

# Hardware-in-the-loop bench firmware
hil-bench_IMAGES := hil-bench
hil-bench_SRCS   := tests/firmware/hil_bench/main.c
hil-bench_MODULES := gpio uart led
hil-bench_CFLAGS  := -I$(BUILD)/hil-bench

# UART driver diagnostic: raw echo and RX error markers (uart_rx_check.py T1-T8)
uart-diag_IMAGES  := uart-diag
uart-diag_SRCS    := tests/firmware/uart_diag/main.c
uart-diag_MODULES := gpio uart led

BOOT_MODULES := boot delay gpio led qspi uart

# 08: a bootloader in internal flash, and 01-blink, unchanged, relinked to
# run from QSPI. Listed application first: that is the flashing order.
08-custombootloader_IMAGES       := 08-custombootloader-app 08-custombootloader-boot
08-custombootloader-boot_SRCS    := $(APPS_DIR)/08-custombootloader/main.c
08-custombootloader-boot_MODULES := $(BOOT_MODULES)
08-custombootloader-app_SRCS     := $(APPS_DIR)/01-blink/main.c
08-custombootloader-app_MODULES  := $(01-blink_MODULES)
08-custombootloader-app_MEMORY   := qspi

# 09: the same pair, but the bootloader compiles in the SHA-256 of the
# application and refuses anything else (see the end of this file)
09-securebootloader_IMAGES       := 09-securebootloader-app 09-securebootloader-boot
09-securebootloader-boot_SRCS    := $(APPS_DIR)/09-securebootloader/main.c \
                                    $(APPS_DIR)/09-securebootloader/sha256.c
09-securebootloader-boot_MODULES := $(BOOT_MODULES)
09-securebootloader-boot_CFLAGS  := -I$(BUILD)/09-securebootloader-boot
09-securebootloader-app_SRCS     := $(APPS_DIR)/01-blink/main.c
09-securebootloader-app_MODULES  := $(01-blink_MODULES)
09-securebootloader-app_MEMORY   := qspi

MULTI  := 08-custombootloader 09-securebootloader
APPS   := $(SINGLE) $(MULTI) hil-bench uart-diag
IMAGES := $(foreach a,$(APPS),$($(a)_IMAGES))

####################################################################
# Templates
####################################################################

# All sources of image $(1): board sources, its own files, its common modules
image_srcs = $(BOARD_SRCS) $($(1)_SRCS) $(foreach m,$($(1)_MODULES),$(DEV)/common/$(m)/$(m).c)

# $(1) = image. Every recipe is the board's, given the memory the image lives in.
define IMAGE
$(1)_MEMORY   ?= $(BOARD_DEFAULT_MEMORY)
$(1)_LDSCRIPT  = $$(MEMORY_$$($(1)_MEMORY)_LDSCRIPT)
$(1)_OUT      := $(BUILD)/$(1)
$(1)_ELF      := $(BUILD)/$(1)/$(1).elf
$(1)_BIN      := $(BUILD)/$(1)/$(1).bin
$(1)_OBJS     := $(patsubst %.c,$(BUILD)/$(1)/%.o,$(notdir $(call image_srcs,$(1))))

$(BUILD)/$(1):
	mkdir -p $$@

$$($(1)_ELF): $$($(1)_OBJS) $$($(1)_LDSCRIPT)
	$$(call board_link,$$@,$$($(1)_OBJS),$$($(1)_MEMORY),$(BUILD)/$(1)/$(1).map)
	$$(call board_size,$$@)

$$($(1)_BIN): $$($(1)_ELF)
	$$(call board_bin,$$@,$$<)

-include $$($(1)_OBJS:.o=.d)

.PHONY: $(1)
$(1): $$($(1)_BIN)

.PHONY: $(1)-flash
$(1)-flash: $$($(1)_BIN)
	$$(call board_flash,$$<,$$($(1)_MEMORY))

.PHONY: $(1)-clean
$(1)-clean:
	rm -rf $(BUILD)/$(1)

.PHONY: $(1)-size
$(1)-size: $$($(1)_ELF)
	$$(call board_size,$$<)

.PHONY: $(1)-disasm
$(1)-disasm: $$($(1)_ELF)
	$$(call board_disasm,$$<)

.PHONY: $(1)-sections
$(1)-sections: $$($(1)_ELF)
	$$(call board_sections,$$<)

# Only memories the board can program over USB get a DFU target
ifeq ($$(MEMORY_$$($(1)_MEMORY)_DFU),yes)
.PHONY: $(1)-dfu
$(1)-dfu: $$($(1)_BIN)
	$$(call board_dfu,$$<,$$($(1)_MEMORY))
endif
endef

# $(1) = image, $(2) = source file
define OBJECT
$(BUILD)/$(1)/$(patsubst %.c,%.o,$(notdir $(2))): $(2) | $(BUILD)/$(1)
	$$(call board_compile,$$@,$$<,$$($(1)_CFLAGS))
endef

# $(1) = application made of several images, flashed in the order listed
define GROUP
.PHONY: $(1)
$(1): $($(1)_IMAGES)

.PHONY: $(1)-flash
$(1)-flash: $(1)
	$(foreach i,$($(1)_IMAGES),$$(MAKE) --no-print-directory $(i)-flash &&) true

.PHONY: $(1)-clean
$(1)-clean: $(addsuffix -clean,$($(1)_IMAGES))

.PHONY: $(1)-dfu
$(1)-dfu: $(1)-boot-dfu
endef

$(foreach i,$(IMAGES),$(eval $(call IMAGE,$(i))))
$(foreach i,$(IMAGES),$(foreach s,$(call image_srcs,$(i)),$(eval $(call OBJECT,$(i),$(s)))))
$(foreach a,$(MULTI),$(eval $(call GROUP,$(a))))

####################################################################
# 09: the bootloader pins the application's hash
####################################################################

# Change the application, and this header, then the bootloader, are rebuilt
APP_HASH := $(BUILD)/09-securebootloader-boot/app_hash.h

$(BUILD)/09-securebootloader-boot/main.o: $(APP_HASH)

$(APP_HASH): $(09-securebootloader-app_BIN) $(TOOLS)/fwhash.py | $(BUILD)/09-securebootloader-boot
	python3 $(TOOLS)/fwhash.py $< > $@.tmp
	mv $@.tmp $@

# 01-blink's DelayCycles(1000000) puts 1000000 in a literal pool. A quarter
# of it is a working blink, four times faster, that nobody signed off.
TAMPERED := $(BUILD)/09-securebootloader-app/tampered.bin

.PHONY: 09-securebootloader-tamper
09-securebootloader-tamper: 09-securebootloader
	python3 $(TOOLS)/tamper.py $(09-securebootloader-app_BIN) $(TAMPERED) 0x000f4240 0x0003d090
	$(call board_flash,$(TAMPERED),qspi)

####################################################################
# HIL bench: the build ID of the readiness banner
####################################################################

# protocol.md section 4.1: abbreviated commit, with -dirty when tracked files
# differ from it; unknown outside a git checkout
HIL_REV   := $(shell git rev-parse --short=7 HEAD 2>/dev/null)
HIL_BUILD := $(if $(HIL_REV),$(HIL_REV)$(shell git diff --quiet HEAD -- 2>/dev/null || echo -dirty),unknown)
HIL_BUILD_H := $(BUILD)/hil-bench/hil_build.h

$(BUILD)/hil-bench/main.o: $(HIL_BUILD_H)

# Checked on every make, rewritten only when the ID changes: an unchanged
# tree rebuilds nothing
$(HIL_BUILD_H): FORCE | $(BUILD)/hil-bench
	@echo '#define HIL_BUILD_ID "$(HIL_BUILD)"' > $@.tmp
	@if cmp -s $@.tmp $@; then rm $@.tmp; else mv $@.tmp $@; fi

.PHONY: FORCE
FORCE:

####################################################################
# Everything at once
####################################################################

.PHONY: all
all: $(APPS)

.PHONY: clean
clean:
	rm -rf $(BUILD)

.PHONY: list
list:
	@for a in $(APPS); do echo "  $$a"; done

.PHONY: reset
reset:
	$(call board_reset)

####################################################################
# Repository
####################################################################

# Make the documentation from board perspective
.PHONY: documentation
documentation:
	@rm -rf work/doc
	@mkdir -p work/doc
	@doxygen ./dev/scripts/Doxyfile
	@echo "work/doc/html/index.html ($$(wc -l < work/doc/doxygen.warnings) warning lines in work/doc/doxygen.warnings)"

# Format source files
.PHONY: format
format:
	@bash -c "dev/scripts/format_cxx.sh"

.PHONY: help
help:
	@echo "Usage: make [BOARD=<name>] <target>"
	@echo ""
	@echo "Per application (01-blink ... 09-securebootloader):"
	@echo "  <app>                build it"
	@echo "  <app>-flash          build and flash with the ST-LINK"
	@echo "  <app>-dfu            build and flash the internal-flash image over USB DFU"
	@echo "  <app>-clean          remove its build outputs"
	@echo ""
	@echo "Per image (an application, or 08/09's <app>-boot and <app>-app):"
	@echo "  <image>-size         flash and RAM usage"
	@echo "  <image>-disasm       disassembly"
	@echo "  <image>-sections     section addresses"
	@echo ""
	@echo "Also:"
	@echo "  all                  build every application"
	@echo "  clean                remove work/build/$(BOARD)"
	@echo "  list                 list applications"
	@echo "  reset                reset the board"
	@echo "  09-securebootloader-tamper   flash a modified application the bootloader must refuse"
	@echo "  documentation        HTML documentation in work/doc/html (doxygen)"
	@echo "  format               format the sources (dev/scripts/format_cxx.sh)"
	@echo ""
	@echo "Board: $(BOARD) ($(BOARD_DIR)/board.mk), memories: $(BOARD_MEMORIES)"
	@echo "Applications: $(APPS)"
