<!-- SPDX-License-Identifier: MIT -->
<!-- Doxygen main page (Z. BEN-AKKA, 11/10/2026); images live in dev/docs/images. -->

# STM32F7508-DK bare-metal {#mainpage}

C firmware for the STM32F7508-DK discovery board (STM32F750N8, Cortex-M7),
written at register level: no HAL, no CMSIS, no CubeMX.

\image html architecture.svg "Firmware layers"

## Applications

| Application            | What it shows                                                  |
|:-----------------------|:---------------------------------------------------------------|
| 01-blink               | GPIO output, busy-wait delay                                   |
| 02-clock               | 216 MHz PLL with over-drive, SysTick                           |
| 03-uart                | USART1 console on the ST-LINK virtual COM port                 |
| 04-lcd-backlight       | LCD panel and backlight power-up                               |
| 05-lcd-init            | LTDC timings and background colour                             |
| 06-lcd-layer           | RGB565 framebuffer on LTDC layer 1                             |
| 07-lcd-logo            | Palette-indexed logo with alpha fade-in                        |
| 08-custombootloader    | Bootloader running an application in place from QSPI flash     |
| 09-securebootloader    | Same, starting the application only if its SHA-256 matches     |

## Shared code

The repository has two sides:

- **dev/**: what does not depend on the board.
  - `apps/`: the applications above, one `main.c` each.
  - `common/`: generic drivers (`gpio`, `led`, `uart`, `rcc`, `delay`, `ltdc`,
    `fb`, `qspi`, `boot`), the hardware they drive is a parameter;
    `defines.h` holds the project-wide return codes.
  - `scripts/`, `tools/`, `docs/`: formatting, documentation, host tools.
- **`stm32f7508-dk/`** (one folder per board, a Git submodule): everything
  specific to that board, with its own
  `Makefile`.
  - `mcu.h`: registers and bit fields of the microcontroller (RM0385).
  - `board.h`, `board.c`: pins, LCD panel, QSPI flash, and the descriptors
    passed to the drivers (`BOARD_LED_LD1`, `BOARD_UART_VCP`...).
  - `startup.c`, `linker/`: vector table, reset handler, memory layout.

## Build

```sh
make 01-blink            # build one application
make 01-blink-flash      # build and flash it with the ST-LINK
make documentation       # this documentation, in work/doc/html
make BOARD=<name> ...    # build for another board folder
```
