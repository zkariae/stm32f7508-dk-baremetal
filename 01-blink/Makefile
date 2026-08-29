TARGET  = blink
BUILD   = work

CC      = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
SIZE    = arm-none-eabi-size

# -mfloat-abi=soft is explicit on purpose: the M7 has an FPU, but we never
# enable the coprocessor, so any VFP instruction would fault immediately.
CFLAGS  = -mcpu=cortex-m7 -mthumb -mfloat-abi=soft
CFLAGS += -Wall -Wextra -O2 -g3
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -nostdlib -ffreestanding

LDFLAGS  = -mcpu=cortex-m7 -mthumb -mfloat-abi=soft
LDFLAGS += -T linker.ld -nostdlib
LDFLAGS += -Wl,--gc-sections -Wl,-Map=$(BUILD)/$(TARGET).map

SRCS = startup.c main.c
OBJS = $(addprefix $(BUILD)/,$(SRCS:.c=.o))

ELF = $(BUILD)/$(TARGET).elf
BIN = $(BUILD)/$(TARGET).bin

all: $(BIN) ## Build the firmware (default)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(ELF): $(OBJS)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	$(SIZE) $@

$(BIN): $(ELF)
	$(OBJCOPY) -O binary $< $@

flash: $(BIN) ## Flash the board with OpenOCD
	sudo openocd -f interface/stlink.cfg -f target/stm32f7x.cfg \
	  -c "program $(BIN) 0x08000000 verify reset exit"

clean: ## Remove everything in work/
	rm -rf $(BUILD)


help:  ## Show this help
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

.PHONY: all clean flash help
