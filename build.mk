ROOT   ?= ..
COMMON ?= $(ROOT)/common
BUILD  ?= work

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
CFLAGS += -I$(COMMON)

LDFLAGS  = $(ARCH)
LDFLAGS += -T $(COMMON)/linker.ld -nostdlib
LDFLAGS += -Wl,--gc-sections -Wl,-Map=$(BUILD)/$(TARGET).map

# startup.c comes from common/, application sources from the current folder
ALL_SRCS = $(COMMON)/startup.c $(SRCS)
OBJS     = $(addprefix $(BUILD)/,$(notdir $(ALL_SRCS:.c=.o)))

ELF = $(BUILD)/$(TARGET).elf
BIN = $(BUILD)/$(TARGET).bin

.DEFAULT_GOAL := all

####################################################################
# Build
####################################################################

.PHONY: all
all: $(BIN)  ## Build the firmware (default)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: $(COMMON)/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(ELF): $(OBJS) $(COMMON)/linker.ld
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	@echo
	$(SIZE) $@

$(BIN): $(ELF)
	$(OBJCOPY) -O binary $< $@

####################################################################
# Board
####################################################################

.PHONY: flash
flash: $(BIN)  ## Flash the board with OpenOCD
	sudo openocd -f interface/stlink.cfg -f target/stm32f7x.cfg \
	  -c "program $(BIN) 0x08000000 verify reset exit"

.PHONY: reset
reset:  ## Reset the board without reflashing
	sudo openocd -f interface/stlink.cfg -f target/stm32f7x.cfg \
	  -c "init; reset; exit"

####################################################################
# Inspection
####################################################################

.PHONY: size
size: $(ELF)  ## Show flash and RAM usage
	$(SIZE) $(ELF)

.PHONY: disasm
disasm: $(ELF)  ## Disassemble the firmware
	$(OBJDUMP) -d $(ELF)

.PHONY: sections
sections: $(ELF)  ## List sections and their addresses
	$(OBJDUMP) -h $(ELF)

####################################################################
# Housekeeping
####################################################################

.PHONY: clean
clean:  ## Remove everything in work/
	rm -rf $(BUILD)

.PHONY: help
help:  ## Show this help
	@echo "$(TARGET) — targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'