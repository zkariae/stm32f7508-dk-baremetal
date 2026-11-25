<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       dev/apps/11-text-console/README.md
\brief      11-text-console: the text received on the UART, shown on the LCD.

\author     Z. BEN-AKKA
\version    1.0
\date       25/11/2026

\details
  How to build, flash and use the application. Acceptance criteria, design
  choices and sources are in work/doc_zak/phaseI_text.md.

\section text_console_readme_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 25/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
-->

# 11-text-console

## Purpose

Show on the 480 × 272 LCD of the STM32F7508-DK the text received on the
ST-LINK UART: a terminal of 60 columns and 17 lines. The application runs in
place from the QSPI flash, behind the 08 bootloader. It uses `dev/common/font`
(glyphs), `dev/common/text` (drawing) and `dev/common/terminal` (character
grid). The acceptance criteria of phase I are in
[phaseI_text.md](../../../work/doc_zak/phaseI_text.md).

## Build and flash

```sh
make 11-text-console          # builds 11-text-console-app and 11-text-console-boot
make 11-text-console-flash    # app to the QSPI flash (0x90000000), then the 08 bootloader
```

Console (one program on the port at a time):

```sh
python3 -m serial.tools.miniterm /dev/ttyACM0 115200 --eol CRLF
```

## Expected console output

```text
boot: 08-custombootloader
boot: QSPI id 0x0018BA20
boot: app SP 0x<stack top>, PC 0x<reset handler>
boot: jumping

text console: 60 x 17
rx: bytes=<n> ms=<n> fe=0 ne=0 ore=0 ovf=0    1 s after the last byte of a reception
```

`text console: clock error` or `text console: pixel clock error` stops the
application. The `rx:` line is a report, the text is not echoed:

| Field | Meaning |
|:--|:--|
| `bytes` | Bytes read since the previous report |
| `ms` | Time from the first event to the last |
| `fe`, `ne`, `ore` | Framing, noise and overrun errors |
| `ovf` | Bytes lost because the reception queue was full |

## Screen

| Received | Shown |
|:--|:--|
| 0x20 to 0x7E | The character at the cursor |
| 60th character of a line | The wrap waits for the next character: CR LF after it gives one line break |
| CR | Column 0, nothing erased |
| LF | Column 0 of the next line; the screen scrolls on the last line |
| Backspace (0x08, 0x7F) | Erases the previous character; stops at column 0 |
| Tab | Next multiple of 8, nothing erased; stops at column 59; no effect while a wrap waits |
| Ctrl-L (form feed) | Empty screen, cursor at the top left |
| Other byte below 0x20 | Nothing |
| 0x80 to 0xFF | `?`, black on white |
| UART error or full queue | `!`, white on red, once per series of errors |

The cursor is a fixed line at the bottom of its cell.

## Font

JetBrains Mono v2.304, Regular, 13 px in 8 × 16 cells, 4 bits per pixel. The
headers of `dev/common/font` are generated, not edited. The `.ttf` is not in the
repository: it comes from the
[v2.304 archive](https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip),
unpacked here in `work/fonts/JetBrainsMono-2.304/`:

```sh
python3 dev/tools/ttf2c.py work/fonts/JetBrainsMono-2.304/JetBrainsMono-Regular.ttf \
    --bpp 4 --name mono_8x16_4bpp --license dev/common/font/OFL.txt \
    --out dev/common/font/mono_8x16_4bpp.h
```

The glyphs are under the SIL Open Font License 1.1, not under the MIT license
of the code: a binary given to someone else comes with
[OFL.txt](../../common/font/OFL.txt).

## Drawing durations

Measured on the board on 25/11/2026 with version 1.1 of `main.c`, CPU at
216 MHz, the LTDC reading the framebuffer; one block is 1 ms.

```text
Full screen, 4 bits, glyphs in QSPI   █████████████████████████████████████  36.63 ms
Full screen, 1 bit,  glyphs in QSPI   █████████████████████████████████████  36.65 ms
Full screen, 4 bits, glyphs in DTCM   █████████   9.23 ms   chosen
Full screen, 1 bit,  glyphs in DTCM   █████████   9.24 ms
Scroll by a 32-bit copy               ███         2.68 ms
One line,    4 bits, glyphs in QSPI   ██          2.16 ms
Comparison of the 1020 cells                      0.24 ms
```

The 4-bit glyphs are therefore copied to DTCM at start, and only the cells
that changed are drawn, at most one line between two reads of the queue. The
format does not change the duration. A byte arrives every 0.087 ms at
115200 baud and the queue holds 256 events, about 22 ms.

## Limits

- ASCII only: an accented letter gives two `?` (UTF-8). No ANSI sequence: the
  left arrow key shows `[D`.
- No echo on the UART, and the lines that leave the screen are not kept.
- During a continuous text the screen skips lines, then catches up after the
  last byte.
- Once the queue is full, `dev/common/uart` drops every byte until it is empty.
- A stray reception was seen twice at the first opening of the port after a
  flash; it can show a character or `!`. Its cause is NOT VERIFIED.
- The bootloader leaves the USART enabled: the application stops it before
  `UartInit` (RM0385 Rev 9, p. 1062). The driver is the subject of issue #136.
- The applications run from QSPI share the address 0x90000000: flashing one
  overwrites the others.
- The D-cache stays off; the 08 bootloader enables the I-cache.
