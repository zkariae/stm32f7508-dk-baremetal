<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       work/doc_zak/phaseI_text.md
\brief      Phase I: text on the LCD, 11-text-console run in place and the HIL text command.

\author     Z. BEN-AKKA
\version    1.2
\date       26/11/2026

\details
  Reference document of phase I. It records the frozen acceptance criteria,
  the design choices, the verified values with their sources, the working
  rules and the ordered sub-steps, so that the work can be resumed without
  any other context. Progress is tracked by the GitHub issues of section 6,
  not in this file.

\section phaseI_text_md_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 24/11/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 25/11/2026 | Z. BEN-AKKA | Lot 1 proofs; decisions A to C; verified values.    |
| 1.2     | 26/11/2026 | Z. BEN-AKKA | Lot 2 proofs; decision D; text type of the TUI.     |
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
tests/host/tui/                  Catalogue type `text`: form and its tests
```

Design choices of 24/11/2026, completed by decisions A to C (section 9.1):

| Item | Choice | Reason |
|:--|:--|:--|
| Application | `11-text-console`, images `11-text-console-app` (QSPI) and `11-text-console-boot` (08 bootloader) | Same form as 10-touch-paint |
| Cell and screen | 8 × 16: 60 columns × 17 lines | 480 × 272 |
| Font | JetBrains Mono v2.304 Regular, 13 px, baseline 13, converted by `ttf2c.py`; the `.ttf` stays in `work/fonts/`, outside git | Free font; no binary in the repository (decision B) |
| 1-bit rendering | Threshold 128 of the smooth rendering | The FreeType monochrome rendering merges `"` (decision B) |
| Generated headers | `OFL-1.1`, without `\version` and `\date` | License of the font; a date would break C2 |
| Formats | 1 bit and 4 bits per pixel in the module; the application uses 4 bits (decision C) | Same duration; smoother |
| Glyphs of the application | Copied from QSPI to DTCM at start (decision C) | Four times faster to draw (section 10.1) |
| 4-bit blending | The background is a parameter: a table of 16 colours is computed once per colour pair. The 1-bit format uses its two ends. Level l of each RGB565 component is `(background * (15 - l) + colour * l + 7) / 15`, without gamma correction | The framebuffer is never read; same code path and tests for both |
| Terminal | Common module; the circular grid and its size are given by the caller; received bytes only change the grid | Testable on the PC; a line feed costs no pixel |
| Rendering | Redraw only the cells that changed, at most one line between two reads of the queue, 256 events per read at most (decision C). A copy by 32-bit words is faster per scroll, but the scrolls would have to be counted | Line feeds received together cost one drawing |
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
| While a wrap waits (validated at I12) | Backspace erases the 60th character; tab has no effect; CR and LF cancel the wait |
| End of a series of errors (validated at I12) | The next received byte, even ignored |

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

The TUI has a new catalogue type, `text` (decided on 25/11/2026, it replaces
the plan of 24/11/2026 without new TUI code): the operator types printable
ASCII, spaces kept, and the TUI sends it in hexadecimal (`wire_text` in
`core/catalog.py`). The free form shows the hexadecimal. The `data` field of
`LCD_TEXT` in `commands.yaml` has this type, with the default value `Hello`.

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

Verified since 24/11/2026:

| Item | Result |
|:--|:--|
| UART reception by interrupt from the QSPI flash, behind the bootloader | Works, no handler in RAM (decision A, section 10.1) |
| Durations: cell, full screen, 32-bit copy, font in QSPI or DTCM | Measured at I15 (section 10.1) |
| JetBrains Mono | v2.304, published on 14/01/2023, `https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip`, sha256 `6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf`; `JetBrainsMono-Regular.ttf` sha256 `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f` |
| License | OFL 1.1, no reserved font name declared; `OFL.txt` copied unmodified. A delivered binary comes with it |
| 8 × 16 cell | No glyph cut, empty or identical among the 95, checked by `ttf2c.py` |
| Duration of `test_text.py` on the board | About 40 s: its 44 `LCD_TEXT` requests from 11:16:14 to 11:16:54 in `work/hil-results/pytest.log` of 26/11/2026 |

NOT VERIFIED on 26/11/2026:

| Item | Checked at |
|:--|:--|
| Cause of the stray reception at the first opening of the port after a flash (section 10.1) | — |
| Why both formats take the same time (assumed: `text.c` reads one glyph byte per pixel) | — |

## 6. Issues and labels

| Issue | Content |
|:--|:--|
| #134, `enhancement` | Lot 1: I1 to I19, C1 to C8 |
| #135, `enhancement` | Lot 2: TE1 to TE8 and TA1 to TA5, C9 to C12; `paused` removed on 25/11/2026 (decision D) |
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
  in this order: `hil_protocol.h`, `commands.c`, `commands.yaml`,
  `expected.py`, `test_catalog.py`, because `test_catalog.py` and CAPS tie the
  names.
- Exceptions, validated on 25/11/2026: one pull request for I6 to I9 (#143) and
  one for I10 to I18 (#144), from stacked sub-branches, one file per commit.
- The developer runs every check on the board. A check counts as passed once
  its output has been pasted or its run folder has been read.
- I2 and I3 are checked together on the board: `main.c` first in the history,
  since the image of the `Makefile` needs it.
- Reference of C7: `work/phaseI_ref.sha256` (outside git), the 16 images
  other than `hil-bench` at `a851989`. Check: `make clean` (the objects do not
  depend on the `Makefile`), `make all`, then
  `sha256sum -c --quiet work/phaseI_ref.sha256`.
- At the start of each sub-step, `git fetch --prune` and
  `git log --oneline origin/phaseI-text/integration..origin/develop`.
- PC checks compile the real sources with gcc in a folder outside the
  repository.

## 8. Release

Decision D, taken on 25/11/2026: phase H part 2 (#105) had not started, so
lot 2 comes now, before it. Release `v0.7.0`, both lots,
`fw=1.5.0 proto=1.5`. TE0 was not needed: develop had not moved since
`a851989`. The other two situations considered at I19:

| Situation after I19 | Order | Release |
|:--|:--|:--|
| Part 2 in progress | Lot 1 alone; lot 2 after phase H is in develop (TE0) | `v0.7.0`, `fw=1.4.0 proto=1.4`; lot 2 in a later tag |
| Phase H already in develop | Lot 2 after TE0 | `v0.8.0` if `v0.7.0` is taken |

The phase H session was told before TE1, including the new TUI type `text`.
It works in a separate repository and has not changed `tests/`. It is still
to receive the rules of the `text` type, the merge commit and the HIL and TUI
totals once lot 2 is in develop. Answer of the phase H session on 24/11/2026:
no date, part 2 starts after the `v0.1.0` tag of `hil-host`; the place of
the `LCD_AFTER_INIT` check after part 2 is not decided.

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
| **A** | Decision, taken on 24/11/2026 | Reception from the QSPI flash proved; no handler in RAM; copy duration known | C5 |
| I4 | `dev/tools/ttf2c.py` | Converter, with a PNG preview | C2 |
| **B** | Decision, taken on 25/11/2026 | 8 × 16 rendering (Regular 13 px, threshold 128) and license accepted by the developer | C1 |
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
| **C** | Decision, taken on 25/11/2026 | 4 bits, glyphs in DTCM, changed cells redrawn, one line at most per turn | — |
| I16 | `dev/apps/11-text-console/main.c` 1.2 | UART to LCD terminal | C3 to C6 |
| I17 | `dev/apps/11-text-console/README.md` | Build, flash, checks | — |
| I18 | `dev/docs/mainpage.md` | Application and modules | — |
| I19 | `work/doc_zak/phaseI_text.md` 1.1 | Lot 1 proofs | — |

### 9.2 Lot 2

| # | File | Content | Criteria |
|:-:|:--|:--|:--|
| **D** | Decision, taken on 25/11/2026 | Lot 2 before phase H part 2 (section 8) | — |
| TE0 | Synchronisation of develop | Not needed (section 8) | C12 |
| TE1 | `tests/protocol.md` 1.14 | `LCD_TEXT`, section 6.25; future commands in 6.26 | C9, C10 |
| TE2 | `tests/firmware/hil_bench/inc/hil_protocol.h` 1.9 | Protocol 1.5, fw 1.5.0, keys and limits | C11 |
| TE3 | `tests/firmware/hil_bench/inc/lcd_commands.h` 1.3 | Handler declaration | C9 |
| TE4 | `Makefile` 1.19 | Modules `font text` in `hil-bench` | C7, C12 |
| TE5 | `tests/firmware/hil_bench/lcd_commands.c` 1.3 | Handler | C9, C10 |
| TA1 | `tests/host/tui/core/catalog.py` 1.1 | Type `text`: printable ASCII, sent in hexadecimal | C11 |
| TA2 | `tests/host/tui/ui/commands_pane.py` 1.1 | Form of the `text` type; free line in hexadecimal | C11 |
| TA3 | `tests/host/tui/tests/test_catalog.py` 1.3 | 15 cases for the `text` type | C11 |
| TA4 | `tests/host/tui/tests/test_ui_commands.py` 1.3 | 9 cases for the form | C11 |
| TA5 | `tests/host/tui/README.md` 1.3 | Type `text` documented | — |
| TE6 | `hil_protocol.h` 1.10, `commands.c` 1.7, `commands.yaml` 1.4, `expected.py` 1.7, `test_catalog.py` 1.4 | Name everywhere (exception, 5 commits) | C11 |
| TE7 | `tests/host/hil/cases/test_text.py` 1.0 | Marker `lcd`; 44 cases | C9, C10 |
| TE8 | `work/doc_zak/phaseI_text.md` 1.2 | Lot 2 proofs | — |

`test_text.py` (44 cases): `BUSY` before `LCD_INIT` (1); five glyphs (space,
`@`, `W`, `g`, `~`) in both formats, with the neighbouring pixels (10); the
blending with light on dark and dark on light (2); a string of three
characters in both formats (2); the longest request, 20 characters (1);
clipping on the right, at the bottom and in the corner (3); lowercase
hexadecimal accepted (1); rejected requests, each one with the framebuffer
checked unchanged (24). The colours are screen `0x07E0`, text `0xFD20` and
background `0x0411`, at (101, 57). The expected pixels come from the generated
headers: the test proves the drawing, C1 and C2 prove the font.

HIL total after lot 2: 298 collected (256 on the board and 42 unit), 290
passed and 8 skipped on the board without `HIL_OPERATOR`. After phase H, about
256 (estimate, NOT VERIFIED). TUI: 377 passed without the board; 25 tests that
need the board were not run.

## 10. Proofs

### 10.1 Lot 1

Recorded on 25/11/2026, integration branch at `4fbeb1b`
(`11-text-console-app.bin` sha256 `db808c1d…`, the image of the I16 checks).
Board checks were made by the developer after `make 11-text-console-flash` and a
reset. "Reported by the developer" means that no output was copied.

| # | Proof | Result |
|:-:|:--|:--|
| C1 | Character sheet of `main.c` 1.1 on the board; the same sheet drawn on the PC by the real modules | Screen conform, both formats, right and bottom edges included (developer's check, by eye) |
| C1 | Both headers decoded by a separate script and compared with Pillow; `text.c` against an independent reference (sanitizers on) | 0 wrong pixel; 0 error in 200048 cases, 12 wrong variants of `text.c` detected |
| C2 | `ttf2c.py` run several times, in other folders, and with `FREETYPE_PROPERTIES` set | Same sha256: 1 bit `8cc0a4d2…`, 4 bits `34835fef…` (Pillow 12.2.0, FreeType 2.14.3). Without the tool, that variable changes 12 and 31 pixels |
| C3 | Console on the board: 60 characters, Enter, `y`; 20 Enters | Screen conform, no empty line, scroll (developer's check, by eye) |
| C4 | Console on the board: CR LF, form feed, backspace, tab, `é` | Screen conform (developer's check, by eye) |
| C3, C4 | `terminal.c` on the PC (sanitizers on) | 48 written cases and 45027 random states, 0 difference with an independent model; 29 wrong variants detected |
| C5 | Probe `main.c` 1.0: two single writes of 8192 bytes (output copied) | Characters: `rx: bytes=8192 ms=717 fe=0 ne=0 ore=0 ovf=0 sum=0x0009EDD0`; LF: the same with `sum=0x00014000`. 12 repeats reported by the developer |
| C5 | Console `main.c` 1.2: form feed and 8191 bytes in lines of 60 columns, then 8192 LF, one write each (output copied on 25/11/2026) | Twice `rx: bytes=8192 ms=712 fe=0 ne=0 ore=0 ovf=0`. Screen conform (developer's check, by eye) |
| C6 | Review of `text.c`, `terminal.c`, `main.c` 1.2 | Every added loop is bounded by the grid, the cell, 17 lines or 256 events; only the main loop is endless. Not displayable bytes and UART errors have a bounded path |
| C6 | The real loop replayed on the PC at 115200 baud with the durations of I15 (interrupts not counted) | 18 scenarios, up to 65536 bytes: 0 wrong pixel, 0 lost, longest turn 594 µs, queue at most 7 of 256 |
| C7 | `make clean`, `make all`, `sha256sum -c` after each sub-step that changes code or the `Makefile` | 16 of 16 images unchanged, also at `4fbeb1b`; `11-text-console-boot` identical to `08-custombootloader-boot` (`17cca139…`) |
| C7 | Required check `continuous-integration/jenkins/pr-merge` | SUCCESS on #137 to #139 and #141 to #144. The HIL counts (246 passed, 8 skipped expected) and T1–T8 were not copied (NOT VERIFIED) |
| C8 | `make 11-text-console-app-size`, `objdump -h` at `4fbeb1b` | Text 11172 bytes from `0x90000000`, far below offset `0x00FF0000`; no `.data`; `.bss` of 10890 bytes from `0x20000000` (DTCM), stack at the top of the DTCM; `.framebuffer` at `0x20010000` (SRAM, NOLOAD). Only the 4-bit font is in the image |

Durations of I15, copied from the board, three resets (the first one below, the
others within 2 µs; 216 MHz, LTDC reading the framebuffer):

| Measure | Duration |
|:--|--:|
| Palette of 16 colours | 8 µs |
| 1020 cells, 1 bit, glyphs in QSPI / DTCM | 36646 µs / 9239 µs |
| 1020 cells, 4 bits, glyphs in QSPI / DTCM | 36632 µs / 9230 µs |
| One line of 60 cells, 4 bits, glyphs in QSPI | 2157 µs |
| Comparison of the 1020 cells (`changed=0`) | 237 µs |
| Line feed that scrolls, form feed (grid) | 5 µs, 18 µs |
| Scroll by a copy of 32-bit words | 2679 µs |
| LTDC FIFO underrun | 0 |

C5 is checked again with these commands, with miniterm closed; expected
`rx: bytes=8192 ms=<close to 711> fe=0 ne=0 ore=0 ovf=0` twice, the lines `0116`
to `0132` (the last one is `0132 GH`), then an empty screen with the cursor at
the bottom left:

```sh
python3 -c "import serial; d=b''.join(b'%04d '%i+bytes(33+(i+k)%94 for k in range(55))+b'\r\n' for i in range(133))[:8192]; p=serial.Serial('/dev/ttyACM0',115200,timeout=3); p.reset_input_buffer(); p.write(b'\f'+d[:-1]); p.flush(); print(p.readline())"
```

```sh
python3 -c "import serial; p=serial.Serial('/dev/ttyACM0',115200,timeout=3); p.reset_input_buffer(); p.write(b'\n'*8192); p.flush(); print(p.readline())"
```

Observations:

- Stray reception at the first opening of the port after a flash, without any
  byte sent: `bytes=1 fe=1 sum=0xFA` at I2, `bytes=3 ms=1 sum=0x1C2` without error
  at I3. It looks like a character at a lower baud rate sent when the port is
  opened (NOT VERIFIED). With the console, the opening before the C5 check received
  nothing in 3 s; the flash before it was not copied.
- Jenkins on 24/11/2026: first `pr-merge` build of #139 in error at 15:10 UTC,
  green at 15:23; the `branch` build (not required) of the same commit in error
  at 21:45. Causes not read. The `branch` build of #143 was still pending on
  25/11/2026.
- Programs of the PC checks: outside the repository, not kept.

### 10.2 Lot 2

Recorded on 26/11/2026, lot 2 at `d860891` (TE7), stacked on the integration
branch `a036014`, local commits not pushed yet. The board ran `hil-bench`
`build=812ea4e fw=1.5.0 proto=1.5` (TE6), the same firmware as at TE7: TE7
only adds a host test. The developer flashed and ran every board check.

| # | Proof | Result |
|:-:|:--|:--|
| C9, C10 | `LcdTextCmd` and `text.c` compiled on the PC against an independent model (sanitizers on) | 0 difference in 3000 requests; 34 of 34 wrong variants detected |
| C9, C10 | `test_text.py` replayed against the whole `hil-bench` compiled for the PC (simulated registers, virtual port, reset by signal) | 44 passed; 34 of 34 wrong variants of `lcd_commands.c` and `text.c` detected, and the one equivalent variant not detected, as intended |
| C9, C10 | `pytest` on the board, whole suite | "All passed" (reported by the developer). `work/hil-results/pytest.log`, 11:15:45 to 11:16:55: the 44 requests of `test_text.py` sent and answered; the counts are not in the log (NOT VERIFIED) |
| C11 | `CAPS` of the board, in the same log | `total=21`, third page from `start=15`: `LCD_PIXEL,LCD_CIRCLE,LCD_LINE,LCD_TEXT,TOUCH_ID,TOUCH_READ` |
| C11 | `CAPS` of the PC build for IDs 1, 99 and 65535 | 21 names, pages 8 + 7 + 6; longest lines 122, 126 and 108 bytes, within 128 |
| C11 | `LCD_TEXT` with miniterm and in the TUI on the board (TE6) | Conform (reported by the developer, no output copied) |
| C11 | TUI tests without the board | 377 passed, 25 board tests not run; 21 of 21 wrong variants detected by TA3, 11 of 11 by TA4 |
| C12 | Size of `hil-bench`, at TE6 and again at `d860891` | Text 21180 bytes, 32 % of the 64 KB of internal flash (12645 bytes before phase I) |
| C12 | `make clean`, `make all`, `sha256sum -c` at `d860891` | 16 of 16 other images unchanged |
| C12 | Required check `continuous-integration/jenkins/pr-merge` (suites, T1–T8) | Not run yet: lot 2 has no pull request (NOT VERIFIED) |

Observations:

- The first TUI trial at TE6 showed `LCD_TEXT` "not in the catalogue": the
  TUI had been started from the phase H folder. Started again from the
  phase I folder, the form was conform.
- The replay of TE7 first found three holes: a background longer than six
  digits, and the `font` and `bg` keys renamed. Three cases were added,
  then every variant was detected.
- The miniterm output of TE2 and TE6 and the pytest summary lines were not
  copied.
- Programs of the PC checks: outside the repository, not kept.
