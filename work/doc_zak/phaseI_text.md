<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       work/doc_zak/phaseI_text.md
\brief      Phase I: text on the LCD, 11-text-console run in place and the HIL text command.

\author     Z. BEN-AKKA
\version    1.0
\date       24/11/2026

\details
  Reference document of phase I. It records the frozen acceptance criteria,
  the design choices, the verified values with their sources, the working
  rules and the ordered sub-steps, so that the work can be resumed without
  any other context. Progress is tracked by the GitHub issues of section 6,
  not in this file.

\section phaseI_text_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 24/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
-->

# Phase I — text on the LCD

## 1. Purpose

Phase I shows text on the 480 × 272 LCD of the STM32F7508-DK, bare-metal at
register level (no HAL, no CMSIS, no C library):

- **lot 1, `dev/`:** a font converter (`ttf2c.py`), three modules (`font`,
  `text`, `terminal`) and `11-text-console`, a small terminal executed in
  place from the QSPI flash behind the 08 bootloader, that shows what
  arrives on the ST-LINK UART;
- **lot 2, `tests/`:** one HIL command, `LCD_TEXT` (protocol 1.4 → 1.5), with
  its host tests.

Lot 1 can be delivered without lot 2: `hil-bench` then stays
`fw=1.4.0 proto=1.4`.

Out of scope: echo on the UART, ANSI colours, status line on the screen,
touch keyboard, live values, static demonstration.

## 2. Acceptance criteria

The criteria are frozen since 24/11/2026. No criterion is added without an
explicit decision of the developer. The proofs are in section 10.

| # | Criterion | Proof | Lot |
|:-:|:--|:--|:-:|
| C1 | The 95 characters are displayed correctly in both formats | Character sheet of `main.c` 1.1 on the board, by eye; check of the generated headers | 1 |
| C2 | `ttf2c.py` is reproducible | Same font file, same options, same Pillow and FreeType versions (written in the header, without a date): same sha256 | 1 |
| C3 | Wrap at 60 columns, scroll at 17 lines | By eye, known text; a line of 60 characters followed by CRLF leaves no empty line | 1 |
| C4 | Editing: backspace, tab, CR, LF, CRLF, form feed, cursor | The behaviour table of section 4, with a miniterm "send / expected" table | 1 |
| C5 | No byte lost at 115200 baud without a pause | Two single writes of 8192 bytes, lines of 60 columns, then LF only: `bytes=8192`, every error counter at 0, `ms` close to 711 (8192 × 10 bits / 115200); the end of the text is complete on the screen | 1 |
| C6 | Every wait added by phase I is bounded; bytes that cannot be displayed and UART errors are handled without blocking | Code review and trial. `UartPutc`, `UartFlush` and `DelayMs` already exist without a limit and are not changed | 1 |
| C7 | No regression | Lot 1: HIL 246 passed, 8 skipped (254 collected); sha256 of the 16 other images unchanged; `11-text-console-boot` identical to `08-custombootloader-boot`; Jenkins check green | 1 |
| C8 | Memory | `make 11-text-console-app-size` below QSPI offset `0x00FF0000`; framebuffer in SRAM; `.data`, `.bss` and the stack in DTCM | 1 |
| C9 | `LCD_TEXT` draws the glyphs of the generated headers in both formats, and nothing outside the cells | pytest, pixels read back with `LCD_PIXEL` | 2 |
| C10 | A rejected request changes no pixel | pytest | 2 |
| C11 | `CAPS` returns 21 names in 3 pages; `LCD_TEXT` has its form in the TUI | pytest, TUI | 2 |
| C12 | `hil-bench` below 64 KB of internal flash; suites green; T1–T8 unchanged | Size, Jenkins | 2 |

## 3. Constraints

| Constraint | Consequence |
|:--|:--|
| One framebuffer (261120 bytes) fits in the 256 KB SRAM | No double buffer: the screen is redrawn cell by cell |
| The UART RX queue holds 256 events: about 22 ms at 115200 baud without a pause | The main loop must come back to the queue well before 22 ms, whatever it draws |
| Once the queue overflows, `uart.c` drops every byte until the queue is empty | The queue must never fill; a full queue loses a burst, not one byte |
| One byte lasts 86.8 µs, 18750 cycles at 216 MHz | A pixel copy at each line feed cannot be assumed to keep up: it is measured (decision C) |
| The application may change HCLK but must not reconfigure the QUADSPI, its divider or its pins | No `qspi` module; `QUADSPI_CR` never written |
| `USART_BRR` can only be written with UE = 0, and the bootloader leaves the USART enabled | The application stops the USART before `UartInit` (issue #136 for the driver) |
| The D-cache stays off; the 08 bootloader enables the I-cache | The LTDC and the CPU see the same pixels |
| A Jenkins build flashes `hil-bench` over the 08 bootloader | Every board check of the application starts with `make 11-text-console-flash` |
| 08, 09, 07-lcd-logo-xip, 10-touch-paint and 11-text-console all put their application at `0x90000000` | Flashing one overwrites the others |
| A protocol value contains neither a space nor `=`; a line is 128 bytes at most | `LCD_TEXT` carries its text in hexadecimal |
| `make documentation` removes `work/doc`, including `work/doc/ref` | Not run in this phase without a copy |
| The board and its port serve Jenkins and the developer in turn | During a build, TUI and miniterm closed, screen not touched |

## 4. Architecture

```text
dev/tools/ttf2c.py               TTF to C header, 1 bit or 4 bits per pixel (Pillow)
dev/common/font/
├── OFL.txt                      License of the font
├── mono_8x16_1bpp.h             Generated, ASCII 32 to 126, 1520 bytes
├── mono_8x16_4bpp.h             Generated, ASCII 32 to 126, 6080 bytes
└── font.h, font.c               Font descriptor and the two fonts
dev/common/text/text.h, text.c   Glyph drawing into a framebuffer, built on fb (fb unchanged)
dev/common/terminal/
└── terminal.h, terminal.c       Character grid and editing; no UART, no framebuffer
dev/apps/11-text-console/
├── main.c                       UART to terminal to LCD
└── README.md                    Build, flash and manual checks
tests/protocol.md                Protocol 1.5: section 6.25
tests/firmware/hil_bench/        LCD_TEXT handler, names, keys and limits
tests/host/                      commands.yaml, expected.py, cases/test_text.py, catalogue check
```

Design choices of 24/11/2026:

| Item | Choice | Reason |
|:--|:--|:--|
| Application | `11-text-console`, images `11-text-console-app` (QSPI) and `11-text-console-boot` (08 bootloader) | Same form as 10-touch-paint |
| Cell and screen | 8 × 16: 60 columns × 17 lines | 480 × 272 |
| Font | JetBrains Mono, converted by `ttf2c.py`; the `.ttf` stays in `work/fonts/`, outside git | Free font; no binary in the repository |
| Formats | 1 bit and 4 bits per pixel in the module; the application uses one (decision C) | Size against smoothness |
| 4-bit blending | The background is a parameter: a table of 16 colours is computed once per colour pair. The 1-bit format uses its two ends | The framebuffer is never read; same code path and tests for both |
| Terminal | Common module; the grid and its size are given by the caller; received bytes only change the grid | Testable on the PC; a line feed costs no pixel |
| Rendering | Proposed: redraw only the cells that changed, at most one line between two reads of the queue. Compared on measurements with a copy by 32-bit words, with or without grouped line feeds | Decision C |
| Counters | 1 s after the last byte, one line on the UART: `rx: bytes= ms= fe= ne= ore= ovf=` | Proof of C5; not an echo |
| USART | Stopped (UE = 0) by the application before `UartInit` | RM0385, section 5 |
| Measuring code | In `main.c` 1.0 and 1.1, removed in 1.2 | Each measurement keeps its code in the history |

Behaviour of the terminal (C4):

| Input | Behaviour |
|:--|:--|
| 0x20 to 0x7E | Character at the cursor |
| 60th character of a line | The wrap waits for the next character: CRLF after 60 characters gives one line break |
| CR | Column 0, nothing erased |
| LF | Column 0 of the next line; the screen scrolls on the last line. CRLF is one line break |
| 0x08, 0x7F | Erases the previous character; stops at column 0 |
| Tab | Next multiple of 8, nothing erased; stops at column 59 |
| Form feed (Ctrl-L) | Empty screen, cursor at the top left |
| Other byte below 0x20 | Ignored |
| Byte from 0x80 | `?` in inverted colours |
| UART error or full queue | `!` on red, once per series of errors |
| Cursor | Fixed line at the bottom of the cell |

`LCD_TEXT` (lot 2, specified in `tests/protocol.md` section 6.25 before any
code):

```text
CMD id=22 command=LCD_TEXT x=0 y=0 font=4bpp color=0xFFFF bg=0x0000 data=48656C6C6F
RESULT id=22 status=OK
END id=22
```

| Item | Choice |
|:--|:--|
| `data` | 1 to 20 bytes, each 0x20 to 0x7E, two hexadecimal digits per byte; longest request line 120 bytes |
| `font` | `1bpp` or `4bpp` |
| `color`, `bg` | RGB565, as in section 6.12 |
| Edges | Text clipped to the framebuffer, no wrap |
| Errors | `BUSY` before `LCD_INIT`; `INVALID_ARGUMENT`, no pixel changed |
| Blending | Formula and rounding are normative, so that the host computes the expected pixels by itself |
| `CAPS` | After `LCD_LINE`: 21 names, pages 8 + 7 + 6 (algorithm of `commands.c` replayed for IDs 1, 99 and 65535) |

The catalogue types `int`, `enum`, `color` and `hexdata` are enough: no new
TUI code.

## 5. Sources

The ST documents are read from `work/doc/ref/`, ignored by git.

| Value | Source |
|:--|:--|
| `USART_BRR` written only with UE = 0 | RM0385 Rev 9, section 31.8.4, p. 1062 |
| RX queue, events, counters, drop until empty | `dev/common/uart/uart.c` 1.5, `uart.h` 1.4 |
| `USART1_IRQHandler` at IRQ 37; RX on PB7, AF7 | `startup.c` 1.6; `board.c` |
| I-cache enabled, VTOR set, QUADSPI left memory-mapped at HCLK / 2 | `08-custombootloader/main.c` 1.7, `boot.c` 1.1 |
| Cycle counter unlocked with `DWT_LAR` on the Cortex-M7 | `mcu.h`; used by `uart_diag/main.c` |
| DTCM and SRAM layout, 16 KB of stack at least | `linker/qspi.ld` 1.2 |
| `--eol CRLF` on Enter, backspace sent as 0x08, upload in blocks of 1024 bytes, each drained | pyserial 3.5, `miniterm.py` |
| Host tools: gcc 10.3.1, Pillow 12.2.0, FreeType 2.14.3 | Checked on 24/11/2026 |
| `hil-bench` text 12645 bytes before phase I | `phaseG_touch.md` section 4 |

NOT VERIFIED on 24/11/2026:

| Item | Checked at |
|:--|:--|
| UART reception by interrupt from the QSPI flash, behind the bootloader | Decision A |
| Durations: cell, full screen, 32-bit copy, font in QSPI or DTCM | Decisions A and C |
| Version, URL, sha256 and license of JetBrains Mono (OFL 1.1 expected; reserved font name to check). The generated headers are expected to be `OFL-1.1`, not MIT | Decision B |
| 8 × 16 cell: no glyph cut (descenders, braces, `@`, `W`) | Decision B |
| Duration of the pixel read-back in `test_text.py` | TE7 |

## 6. Issues and labels

| Issue | Content |
|:--|:--|
| #134, `enhancement` | Lot 1: I1 to I19, C1 to C8 |
| #135, `enhancement` and `paused` | Lot 2: TE0 to TE8, C9 to C12; `paused` until decision D |
| #136, `bug` | `UartInit` writes `USART_BRR` with the USART enabled |

Each pull request carries its label and `Refs #n`. Each lot issue is closed
by hand with a comment, after the tag.

## 7. Working rules

The rules of `ci/README.md` section 9 apply, with these additions:

- One file per sub-branch `phaseI-text/<task>`, made from the integration
  branch just merged. Pull requests pass one at a time; the developer merges.
- The plan of each sub-step is validated before its sub-branch exists. The
  result is shown before the commit.
- Exception, validated: TE6 is one sub-branch with five commits, one per file
  (`hil_protocol.h`, `commands.yaml`, `commands.c`, `expected.py`,
  `test_catalog.py`), because `test_catalog.py` and CAPS tie the names.
- The developer runs every check on the board. A check counts as passed once
  its output has been pasted or its run folder has been read.
- I2 and I3 are checked together on the board: `main.c` first in the history,
  since the image of the `Makefile` needs it.
- Reference of C7: `work/phaseI_ref.sha256` (outside git), the 16 images
  other than `hil-bench` at `a851989`. Check: `make all`, then
  `sha256sum -c --quiet work/phaseI_ref.sha256`.
- At the start of each sub-step, `git fetch --prune` and
  `git log --oneline origin/phaseI-text/integration..origin/develop`.
- PC checks compile the real sources with gcc in a folder outside the
  repository.

## 8. Release

| Situation after I19 (decision D) | Order | Release |
|:--|:--|:--|
| Phase H part 2 (#105) not started | Lot 2 now; the phase H session is told before TE1 | `v0.7.0`, both lots, `fw=1.5.0 proto=1.5` |
| Part 2 in progress | Lot 1 alone; lot 2 after phase H is in develop (TE0) | `v0.7.0`, `fw=1.4.0 proto=1.4`; lot 2 in a later tag |
| Phase H already in develop | Lot 2 after TE0 | `v0.8.0` if `v0.7.0` is taken |

Lot 2 is never merged into develop while phase H part 2 is in progress: its board
total (H4) is re-based on develop at the start of part 2. Answer of the
phase H session on 24/11/2026: no date, part 2 starts after the `v0.1.0` tag
of `hil-host`; the place of the `LCD_AFTER_INIT` check after part 2 is not
decided.

The tags are read again just before the release. Steps, each at the
developer's request: integration → `develop`, `develop` → `main`, annotated
tag on the merge commit of `main`, issues closed by hand, `main` → `develop`.

## 9. Sub-steps

One file per sub-step, in this order. Every commit compiles.

### 9.1 Lot 1

| # | File | Content | Criteria |
|:-:|:--|:--|:--|
| I0 | — | Integration branch pushed, issues, sha256 reference | C7 |
| I1 | `work/doc_zak/phaseI_text.md` 1.0 | This document | — |
| I2 | `dev/apps/11-text-console/main.c` 1.0 | Probe: interrupt RX from QSPI, counters, framebuffer copy measured | C5 |
| I3 | `Makefile` | `11-text-console` in `MULTI` | C7, C8 |
| **A** | Decision | Reception from the QSPI flash proved; copy duration known | C5 |
| I4 | `dev/tools/ttf2c.py` | Converter, with a PNG preview | C2 |
| **B** | Decision | 8 × 16 rendering and license accepted by the developer | C1 |
| I5 | `dev/common/font/OFL.txt` | License | — |
| I6 | `dev/common/font/mono_8x16_1bpp.h` | Generated | C1, C2 |
| I7 | `dev/common/font/mono_8x16_4bpp.h` | Generated | C1, C2 |
| I8 | `dev/common/font/font.h` | Font descriptor | C1 |
| I9 | `dev/common/font/font.c` | The two fonts | C1 |
| I10 | `dev/common/text/text.h` | Drawing API | C1 |
| I11 | `dev/common/text/text.c` | Drawing, both formats, clipping | C1 |
| I12 | `dev/common/terminal/terminal.h` | Terminal API | C3, C4 |
| I13 | `dev/common/terminal/terminal.c` | Grid and editing, checked on the PC | C3, C4 |
| I14 | `Makefile` | Modules `font text terminal` in 11-text-console | C7 |
| I15 | `dev/apps/11-text-console/main.c` 1.1 | Character sheet, rendering measured | C1 |
| **C** | Decision | Scrolling and format chosen on the measurements | — |
| I16 | `dev/apps/11-text-console/main.c` 1.2 | UART to LCD terminal | C3 to C6 |
| I17 | `dev/apps/11-text-console/README.md` | Build, flash, checks | — |
| I18 | `dev/docs/mainpage.md` | Application and modules | — |
| I19 | `work/doc_zak/phaseI_text.md` 1.1 | Lot 1 proofs | — |

### 9.2 Lot 2

| # | File | Content | Criteria |
|:-:|:--|:--|:--|
| **D** | Decision | Before or after phase H part 2 (section 8) | — |
| TE0 | Synchronisation of develop | Only after phase H | C12 |
| TE1 | `tests/protocol.md` 1.14 | `LCD_TEXT`, section 6.25; future commands in 6.26 | C9, C10 |
| TE2 | `tests/firmware/hil_bench/inc/hil_protocol.h` | Protocol 1.5, fw 1.5.0, keys and limits | C11 |
| TE3 | `tests/firmware/hil_bench/inc/lcd_commands.h` | Handler declaration | C9 |
| TE4 | `Makefile` | Modules `font text` in `hil-bench` | C7, C12 |
| TE5 | `tests/firmware/hil_bench/lcd_commands.c` | Handler | C9, C10 |
| TE6 | `hil_protocol.h`, `commands.yaml`, `commands.c`, `expected.py`, `test_catalog.py` | Name everywhere (exception, 5 commits). After phase H: the file that took over the `LCD_AFTER_INIT` check | C11 |
| TE7 | `tests/host/hil/cases/test_text.py` | Marker `lcd`; about 25 cases | C9, C10 |
| TE8 | `work/doc_zak/phaseI_text.md` | Lot 2 proofs | — |

`test_text.py`: `BUSY` before `LCD_INIT` (1), five glyphs (space, `@`, `W`,
`g`, `{`) in both formats with the neighbouring pixels (10), a string of three
characters in both formats (2), clipping on the right and at the bottom (2),
rejected requests (10). The expected pixels come from the generated headers:
the test proves the drawing, C1 and C2 prove the font.

HIL total after lot 2, to be counted again: about 279 collected (237 on the
board and 42 unit) before phase H, about 237 after it.

## 10. Proofs

None yet. Lot 1 at I19, lot 2 at TE8.
