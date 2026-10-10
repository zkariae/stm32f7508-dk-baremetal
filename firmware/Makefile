# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       firmware/Makefile
# \brief      The only Makefile for everything that runs on the board.
#
# \author     Z. BEN-AKKA
# \version    1.1
# \date       10/10/2026
#
# \details
#   Each application is declared as one or more images (sources, linker
#   script, load address, OpenOCD config); the rules for every image come
#   from the IMAGE template. Run from firmware/ or from the repository root.
#     make 01-blink          build one application
#     make 01-blink-flash    build and flash it with the ST-LINK
#     make help              everything else
#
# \section firmware_makefile_version_history Version history
# | Version | Date       | Author      | Description                                                   |
# |:-------:|:----------:|:------------|:--------------------------------------------------------------|
# | 1.0     | 29/08/2026 | Z. BEN-AKKA | Initial version.                                              |
# | 1.1     | 10/10/2026 | Z. BEN-AKKA | Single Makefile, build.mk merged; header per Contributing.md. |
# ****************************
# */

TOOLS := ../tools
BUILD := ../work/build

.DEFAULT_GOAL := help

####################################################################
# Toolchain
####################################################################

CC      = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
SIZE    = arm-none-eabi-size
OBJDUMP = arm-none-eabi-objdump

# -mfloat-abi=soft is explicit on purpose: the M7 has an FPU, but we never
# enable the coprocessor, so any VFP instruction would fault immediately.
ARCH    = -mcpu=cortex-m7 -mthumb -mfloat-abi=soft

CFLAGS  = $(ARCH)
CFLAGS += -Wall -Wextra -O2 -g3
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -nostdlib -ffreestanding
CFLAGS += -I. -Icommon
CFLAGS += -MMD -MP          # track headers: editing defines.h rebuilds what uses it

LDFLAGS  = $(ARCH)
LDFLAGS += -nostdlib -Wl,--gc-sections

####################################################################
# Defaults: linked for the internal flash, flashed by the ST-LINK
####################################################################

OPENOCD_INTERNAL := -f interface/stlink.cfg -f target/stm32f7x.cfg

# The board config adds OpenOCD's stmqspi flash bank at 0x90000000 and sets
# up the QSPI pins on reset-init; target/stm32f7x.cfg alone only knows the
# internal flash
OPENOCD_QSPI     := -f board/stm32f746g-disco.cfg

DEFAULT_LDSCRIPT := linker/internal-flash.ld
DEFAULT_ADDR     := 0x08000000
DEFAULT_OPENOCD  := $(OPENOCD_INTERNAL)

####################################################################
# Applications
####################################################################

# One image each, named after the application. <image>_MODULES lists the
# common/<module>/<module>.c files it links, on top of common/startup.c.
SINGLE := 01-blink 02-clock 03-uart 04-lcd-backlight 05-lcd-init 06-lcd-layer 07-lcd-logo
$(foreach a,$(SINGLE),$(eval $(a)_IMAGES := $(a)))
$(foreach a,$(SINGLE),$(eval $(a)_SRCS := $(a)/main.c))

# board/ holds what is specific to the STM32F7508-DK; it needs delay and gpio.
01-blink_MODULES         := board delay gpio led
02-clock_MODULES         := board delay gpio led rcc
03-uart_MODULES          := board delay gpio led rcc uart
04-lcd-backlight_MODULES := board delay gpio led rcc uart
05-lcd-init_MODULES      := board delay gpio ltdc rcc uart
06-lcd-layer_MODULES     := board delay fb gpio ltdc rcc uart
07-lcd-logo_MODULES      := board delay fb gpio ltdc rcc uart

BOOT_MODULES := board boot delay gpio led qspi uart

# 08: a bootloader in internal flash, and 01-blink, unchanged, relinked to
# run from QSPI. Listed application first: that is the flashing order.
08-custombootloader_IMAGES      := 08-custombootloader-app 08-custombootloader-boot
08-custombootloader-boot_SRCS   := 08-custombootloader/main.c
08-custombootloader-boot_MODULES := $(BOOT_MODULES)
08-custombootloader-app_SRCS    := 01-blink/main.c
08-custombootloader-app_MODULES := $(01-blink_MODULES)
08-custombootloader-app_LDSCRIPT := linker/qspi.ld
08-custombootloader-app_ADDR    := 0x90000000
08-custombootloader-app_OPENOCD := $(OPENOCD_QSPI)

# 09: the same pair, but the bootloader compiles in the SHA-256 of the
# application and refuses anything else (see the end of this file)
09-securebootloader_IMAGES      := 09-securebootloader-app 09-securebootloader-boot
09-securebootloader-boot_SRCS   := 09-securebootloader/main.c 09-securebootloader/sha256.c
09-securebootloader-boot_MODULES := $(BOOT_MODULES)
09-securebootloader-boot_CFLAGS := -I$(BUILD)/09-securebootloader-boot
09-securebootloader-app_SRCS    := 01-blink/main.c
09-securebootloader-app_MODULES := $(01-blink_MODULES)
09-securebootloader-app_LDSCRIPT := linker/qspi.ld
09-securebootloader-app_ADDR    := 0x90000000
09-securebootloader-app_OPENOCD := $(OPENOCD_QSPI)

MULTI  := 08-custombootloader 09-securebootloader
APPS   := $(SINGLE) $(MULTI)
IMAGES := $(foreach a,$(APPS),$($(a)_IMAGES))

####################################################################
# Templates
####################################################################

# All sources of image $(1): startup, its own files, its common modules
image_srcs = common/startup.c $($(1)_SRCS) $(foreach m,$($(1)_MODULES),common/$(m)/$(m).c)

# $(1) = image
define IMAGE
$(1)_OUT      := $(BUILD)/$(1)
$(1)_ELF      := $(BUILD)/$(1)/$(1).elf
$(1)_BIN      := $(BUILD)/$(1)/$(1).bin
$(1)_LDSCRIPT ?= $(DEFAULT_LDSCRIPT)
$(1)_ADDR     ?= $(DEFAULT_ADDR)
$(1)_OPENOCD  ?= $(DEFAULT_OPENOCD)
$(1)_OBJS     := $(patsubst %.c,$(BUILD)/$(1)/%.o,$(notdir $(call image_srcs,$(1))))

$(BUILD)/$(1):
	mkdir -p $$@

$$($(1)_ELF): $$($(1)_OBJS) $$($(1)_LDSCRIPT)
	$$(CC) $$($(1)_OBJS) $$(LDFLAGS) -T $$($(1)_LDSCRIPT) -Wl,-Map=$(BUILD)/$(1)/$(1).map -o $$@
	$$(SIZE) $$@

$$($(1)_BIN): $$($(1)_ELF)
	$$(OBJCOPY) -O binary $$< $$@

-include $$($(1)_OBJS:.o=.d)

.PHONY: $(1)
$(1): $$($(1)_BIN)

.PHONY: $(1)-flash
$(1)-flash: $$($(1)_BIN)
	sudo openocd $$($(1)_OPENOCD) -c "program $$< $$($(1)_ADDR) verify reset exit"

.PHONY: $(1)-clean
$(1)-clean:
	rm -rf $(BUILD)/$(1)

.PHONY: $(1)-size
$(1)-size: $$($(1)_ELF)
	$$(SIZE) $$<

.PHONY: $(1)-disasm
$(1)-disasm: $$($(1)_ELF)
	$$(OBJDUMP) -d $$<

.PHONY: $(1)-sections
$(1)-sections: $$($(1)_ELF)
	$$(OBJDUMP) -h $$<

# The ROM DFU only reaches the internal flash
ifeq ($$($(1)_ADDR),$(DEFAULT_ADDR))
.PHONY: $(1)-dfu
$(1)-dfu: $$($(1)_BIN)
	python3 $(TOOLS)/dfu.py --address $$($(1)_ADDR) $$<
endif
endef

# $(1) = image, $(2) = source file
define OBJECT
$(BUILD)/$(1)/$(patsubst %.c,%.o,$(notdir $(2))): $(2) | $(BUILD)/$(1)
	$$(CC) $$(CFLAGS) $$($(1)_CFLAGS) -c $$< -o $$@
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
	sudo openocd $(OPENOCD_QSPI) -c "program $(TAMPERED) 0x90000000 verify reset exit"

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
	sudo openocd $(OPENOCD_INTERNAL) -c "init; reset; exit"

.PHONY: help
help:
	@echo "Usage: make <target>"
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
	@echo "  clean                remove work/build"
	@echo "  list                 list applications"
	@echo "  reset                reset the board"
	@echo "  09-securebootloader-tamper   flash a modified application the bootloader must refuse"
	@echo ""
	@echo "Applications: $(APPS)"
