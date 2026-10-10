<!-- SPDX-License-Identifier: MIT -->
<!-- Doxygen main page (Z. BEN-AKKA, 10/10/2026); images live in docs/images. -->

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

The applications are built on `firmware/common`:

- **Generic drivers** (`gpio`, `led`, `uart`, `rcc`, `delay`, `ltdc`, `fb`,
  `qspi`, `boot`): the hardware they drive is a parameter.
- **Board support** (`board`): everything specific to the STM32F7508-DK.
- **defines.h**: every register, bit field and board pin, from RM0385.

## Build

```sh
make 01-blink            # build one application
make 01-blink-flash      # build and flash it with the ST-LINK
make documentation       # this documentation, in work/doc/html
```
