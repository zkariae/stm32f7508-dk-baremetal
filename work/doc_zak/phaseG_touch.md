<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       work/doc_zak/phaseG_touch.md
\brief      Phase G: touch panel, 10-touch-paint run in place and HIL touch commands.

\author     Z. BEN-AKKA
\version    1.3
\date       23/11/2026

\details
  Reference document of phase G. It records the frozen acceptance criteria,
  the verified hardware values with their sources, the design choices, the
  working rules and the ordered sub-steps, so that the work can be resumed
  without any other context. Progress is tracked by the GitHub issues of
  section 6, not in this file.

\section phaseG_touch_md_version_history Version history
| Version | Date       | Author      | Description                              |
|:-------:|:----------:|:------------|:-----------------------------------------|
| 1.0     | 18/11/2026 | Z. BEN-AKKA | Initial version.                         |
| 1.1     | 19/11/2026 | Z. BEN-AKKA | Lot 2 paused for phase H; lot 1 proofs.  |
| 1.2     | 20/11/2026 | Z. BEN-AKKA | Lot 2 resumed and delivered: TD_STATUS fix, LCD_CIRCLE, LCD_LINE, accuracy and drawing tests; lot 2 proofs; release plan. |
| 1.3     | 23/11/2026 | Z. BEN-AKKA | TUI run options, scenario cleanup and the TUI proofs; release plan checked again. |
****************************
-->

# Phase G — touch panel

## 1. Purpose

Phase G adds the capacitive touch panel of the STM32F7508-DK, bare-metal at
register level (no HAL, no CMSIS):

- a generic polled I2C driver and an FT5336 touch controller driver;
- `10-touch-paint`, an application that draws with a finger, executed in
  place from the QSPI flash behind the 08 bootloader;
- two HIL commands, `TOUCH_ID` and `TOUCH_READ` (protocol 1.3 → 1.4), with
  their host tests and a TUI scenario.

**History of the scope.**

- 18/11/2026: nothing under `tests/` was to change in phase G, because a
  phase H moves the host side of the bench (`tests/host/hil`, the
  `hil_events` plugin, the TUI) to its own repository. Lot 2 was paused.
- 19/11/2026: before the merge to develop, the developer resumed lot 2, so
  that the touch part is tested on the bench. The phase H session confirmed
  that there is no overlap: it changes nothing in this repository before
  phase G is in develop, and never changes `tests/protocol.md`, the firmware,
  the root `Makefile`, the content of `commands.yaml`, `test_protocol_caps.py`
  or `expected.py`.
- 20/11/2026: the developer added, still in protocol 1.4, two drawing
  commands, `LCD_CIRCLE` and `LCD_LINE`, and three operator tests built on
  them: touch accuracy on random targets, free drawing as in the Paint, and
  the drawing colour chosen by name (`tests/host/config/colors.yaml`).
- 23/11/2026: the developer added the operator tests to the TUI: an Options
  window for the run options (operator, drawing colour, target seed) and the
  operator instructions on the progress line (G26). A `TEST_DRAW` entry in
  the Commands tab was proposed and dropped. Two scenarios added with G26,
  `lcd_drawing` and `touch_targets`, were removed the same day:
  `touch_targets` failed on the board and both repeated pytest tests;
  `touch_check` now asks the operator only once (G27).

Phase G delivers `v0.6.0` with both lots: `hil-bench` becomes
`fw=1.4.0 proto=1.4`, with 20 commands.

Out of scope, proposed only on request: touch interrupt (EXTI), a Paint
variant in internal flash, text font, SDRAM, DMA2D, audio codec, TUI issues
#25, #27, #28 and #89.

## 2. Acceptance criteria

The criteria are frozen. No criterion is added without an explicit decision
of the developer. The proofs are in section 10.

| # | Criterion | Proof | Type | Status (20/11/2026) |
|:-:|:--|:--|:--|:--|
| C1 | Generic I2C driver, every wait bounded | Each hardware wait returns `TIMEOUT` past its limit (code review); `I2cInit` sets HSION and waits for HSIRDY with a limit; C2 passes | Automatic | Met |
| C2 | FT5336 identified | `TOUCH_ID` returns `chip_id=0x51`, also when sent right after a reset, HELLO and CAPS (before 300 ms) | Automatic (Jenkins) | Met |
| C3 | Untouched screen gives no point | `TOUCH_READ` returns `points=0` before and after `LCD_INIT`. **Fails if somebody touches the screen during a Jenkins build** | Automatic | Met |
| C4 | Rejected requests change nothing | An extra argument gives `INVALID_ARGUMENT`; then `TOUCH_READ` still returns `points=0` and `TOUCH_ID` still `0x51` | Automatic | Met |
| C5 | Axis directions | Top-left corner: x < 60 and y < 60. Top-right corner: x > 420 and y < 60. Always x ≤ 479 and y ≤ 271. Two corners, since one corner does not detect swapped axes. Proved by the operator test of `test_touch.py` (`HIL_OPERATOR=1`, waits at most 10 s for `points=1`) and by the TUI scenario `touch_check.yaml` | Operator | Met |
| C6 | Paint run in place | After `make 10-touch-paint-flash`: the stroke appears under the finger over the whole surface (four corners and centre), without gaps when the finger moves fast; the colour bar changes the colour; the clear area clears the screen; the console shows `boot: jumping` | Operator | Met |
| C7 | No regression | HIL suite **246 passed, 8 skipped (254 collected)**; Jenkins check green on every pull request; the sha256 of the other images unchanged by each change that does not target them. The total was 222 passed, 2 skipped before the additions of 20/11/2026, decided by the developer | Automatic | Met |
| C8 | Memory | `hil-bench` below 64 KB of internal flash; `10-touch-paint-app` below offset `0x00FF0000` of the QSPI flash (test area); framebuffer in internal SRAM | Automatic (`make <image>-size`) | Met |

The tests added on 20/11/2026 (accuracy, drawing, colour) are operator
tests of C5 and C6 on the bench: they add no criterion, and neither do the
TUI run options of 23/11/2026. `touch_check.yaml`, named in C5, checks the
number of points; the position is checked by the operator tests.

## 3. Constraints

| Constraint | Consequence |
|:--|:--|
| A Jenkins build flashes `hil-bench` into the internal flash, over the 08 bootloader | To see the Paint again: `make 10-touch-paint-flash`. Every board check of the Paint starts with it |
| 08, 09, 07-lcd-logo-xip and 10-touch-paint all put their application at `0x90000000` | Flashing one overwrites the others |
| Code executed from the QSPI flash cannot use the QUADSPI in indirect mode | `touch` and `i2c` do not depend on `qspi`; the Paint never reconfigures the QUADSPI |
| I2C3 is shared with the WM8994 audio codec (address 0x1A), not driven by the firmware | The address is a parameter of each transfer; `BUSY` is waited for with a limit before a START; NACK, BERR and ARLO are reported |
| The FT5336 reset is tied to NRST (section 5) | Every MCU reset (flash, `make reset`, `make reset-sw`) restarts its 200 ms start time |
| 20 command names make three CAPS pages (8 + 7 + 5, whatever the request ID) | `test_protocol_caps.py` follows `next` for any number of pages (G14) |
| TUI `expect` values are compared for equality only | Coordinate limits are checked by the operator tests; the scenario checks `points=1` and asks the operator |
| `TOUCH_READ` with the screen untouched must give 0 point | **Keep your hands off the screen during a Jenkins build** |
| The board and its port serve Jenkins and the developer in turn | Before a check by hand, read `fw=` and `build=` in the banner; keep the TUI, miniterm and minicom closed during a build. A miniterm left open on `/dev/ttyACM0` while Jenkins flashed made the ST-LINK port come back as `/dev/ttyACM1`, and the T1–T8 stage failed twice on 20/11/2026: quit miniterm with Ctrl-], then re-attach the probe |
| A run with `--no-flash` uses the firmware already on the board | `BUILD_MISMATCH` stops it if the build ID differs from the repository: flash first (`make hil-bench-flash`) |

## 4. Architecture

```text
stm32f7508-dk/ (submodule)
├── mcu.h                    I2C3, RCC_DCKCFGR2, HSIRDY registers
├── board.h                  BOARD_I2C_TOUCH, FT5336_ADDR 0x38, TOUCH_INT_PIN (PI13, declared only)
└── board.c                  I2C3 descriptor: PH7/PH8 AF4, HSI kernel clock
dev/common/
├── i2c/i2c.c, i2c.h         Generic polled I2C, bounded waits, hardware as a parameter
└── touch/touch.c, touch.h   FT5336: chip ID, number of points, X/Y in the 480x272 frame
dev/apps/10-touch-paint/
├── main.c                   FbCircle brush, colour bar, clear area
└── README.md                Build, flash and manual checks
tests/protocol.md            Protocol 1.4: sections 6.20 to 6.24
tests/firmware/hil_bench/
├── inc/hil_protocol.h       Names, keys, limits, 300 ms start time, proto 1.4, fw 1.4.0
├── inc/touch_commands.h
├── touch_commands.c         TOUCH_ID and TOUCH_READ
├── inc/lcd_commands.h
├── lcd_commands.c           LCD commands, now with LCD_CIRCLE and LCD_LINE
└── commands.c               Command table: 20 names
tests/host/
├── config/commands.yaml     Touch group; LCD_CIRCLE and LCD_LINE in the LCD group
├── config/colors.yaml       Colour names, French aliases, RGB565 values of the Paint
├── config/run_options.yaml  Run options of the TUI: operator, drawing colour, target seed
├── hil/pyproject.toml       Marker touch
├── hil/cases/expected.py    COMMANDS, TOUCH_CHIP_ID, TOUCH_MAX_POINTS, radius limits
├── hil/cases/test_lcd.py    LCD_CIRCLE and LCD_LINE cases
├── hil/cases/test_touch.py  Touch cases; operator tests: corners, accuracy, drawing
├── hil/cases/test_protocol_caps.py  CAPS pages followed through next
├── tui/tests/test_catalog.py LCD_CIRCLE and LCD_LINE require LCD_INIT
├── tui/core/run_options.py  Options checked, environment of a pytest run
├── tui/ui/options_screen.py Options window of the Tests tab
└── tui/scenarios/touch_check.yaml
```

Design choices:

| Item | Choice | Reason |
|:--|:--|:--|
| I2C kernel clock | HSI, 16 MHz (`I2C3SEL` = 10) | The same `TIMINGR` in `hil-bench`, including its HSI fallback, and in the Paint |
| Bus speed | 100 kHz, standard mode | Within the FT5336 range (10 to 400 kHz) |
| `TIMINGR` | `0x30420F13`: PRESC 3, SCLDEL 4, SDADEL 2, SCLH 0x0F, SCLL 0x13 | RM0385 table for 16 MHz, 100 kHz |
| Start time | The Paint, `TOUCH_ID` and `TOUCH_READ` wait until 300 ms after the start of the firmware (`SysTickMs()`) before any access | 200 ms minimum (Tpon, Trsi) plus a margin; nothing waits at startup, the banner is unchanged |
| I2C init | Paint: at start. `hil-bench`: at the first touch command; HSION set, HSIRDY waited for with a limit | `main.c` of `hil-bench` unchanged |
| Axes | Screen x = FT5336 Y register, screen y = FT5336 X register, no inversion, no scaling | ST BSP (`TS_SWAP_XY`); proved by C5 |
| `TOUCH_ID` result | `chip_id=0x<2 hexadecimal digits>` | `id` is a reserved key; the host compares with 0x51, as for `QSPI_ID` |
| `TOUCH_READ` result | `points=<0..5>`, then `x=<n> y=<n>` of point 1 when `points` ≥ 1 | Short line; multi-touch out of scope |
| Number of points | Bits 3:0 of `TD_STATUS`; a value above 5 is no touch and gives 0 points (protocol section 6.20) | The FT5336 reports values above 5 when nothing is touched; the ST driver reads them as 0. Found on the board on 20/11/2026: `TOUCH_READ` answered `DEVICE_ERROR` on every call |
| Error codes | Driver: NACK or a wait past its limit gives `TIMEOUT`; BERR and ARLO give `FAILURE`. Protocol: `DEVICE_TIMEOUT` and `DEVICE_ERROR` | `DEVICE_TIMEOUT` only when the chip does not answer |
| Paint strokes | Successive points joined with FbCircle, one circle every 2 px | No gaps when the finger moves fast |
| `LCD_CIRCLE` | Disc of radius 1 to 100, clipped to the screen (section 6.23) | Targets of the accuracy test |
| `LCD_LINE` | Discs every 2 px from one end to the other, as `stroke()` of the Paint; radius 1 to 20 (section 6.24) | One serial exchange per touched point: drawing from the host with one `LCD_CIRCLE` per disc was too slow. Radius 20 at most keeps a stroke across the screen far within the 2 s timeout. From radius 2 the stroke has no gap; with radius 1 a slanted stroke is dotted (simulated on 3000 random segments) |
| Drawing colour | `HIL_DRAW_COLOR`: a name or French alias of `colors.yaml`, or `0x` and 1 to 4 digits; black by default; white refused | An environment variable reaches pytest from the TUI too; white would be invisible on the white screen |
| TUI run options | Listed in `run_options.yaml` only: the TUI code names no variable. A value equal to its default is not sent, and the variable is removed from the environment of the run | A run uses exactly what the Options line of the Tests tab shows; `run.json` and the report keep it |
| Operator instructions | Logger `hil.operator`, shown in bold on the progress line of the TUI until the test ends | In the monitor they were lost among the TX and RX lines of the `TOUCH_READ` polling |

Sizes measured on 20/11/2026: `hil-bench` text 12645 bytes (10736 before
phase G); `10-touch-paint-app` text 4300 bytes from `0x90000000`;
`10-touch-paint-boot` is the 08 bootloader, text 2709 bytes, same sha256 as
`08-custombootloader-boot`. Framebuffer 480 × 272 RGB565 = 261120 bytes in
the 256 KB SRAM (`.framebuffer`, NOLOAD); `.data`, `.bss` and the stack in
DTCM. The 08 bootloader enables the I-cache before the jump; the D-cache
stays off.

## 5. Sources

The ST documents are not in the repository: they are read from
`work/doc/ref/`, ignored by git (`/work/*` in `.gitignore`). Pages are PDF
pages.

| Value | Source |
|:--|:--|
| PH7 = I2C3_SCL (ball N13), PH8 = I2C3_SDA (ball P14) | UM2470 Rev 2, Table 12 (I/O assignment), p. 33; MB1191 C-03 schematic, p. 3 (nets `PH7` = `AUDIO_SCL` = `LCD_SCL`, `PH8` = `AUDIO_SDA` = `LCD_SDA`) |
| PH7 and PH8 on AF4 | DS12535 (STM32F750x8 datasheet) Rev 2, Table 12 (alternate function mapping), p. 76–77 |
| `LCD_INT` = PI13 (ball G3) | UM2470 Rev 2, Table 12, p. 30; MB1191 p. 3 |
| Touch address `01110000` (0x70 in 8 bits, 0x38 in 7 bits) | MB1191 p. 14 ("Default I2C Address : 01110000"); ST BSP `TS_I2C_ADDRESS 0x70` |
| Touch panel connector U19: RESET pin 37, INT 38, SCL 39, SDA 40 | MB1191 p. 14 |
| FT5336 reset tied to NRST | MB1191 p. 14 (pin 37 on `LCD_RST`) and p. 3 (`LCD_RST` = `DCMI_NRST` = `NRST`, ball J1, pull-up R34 10K) |
| I2C3 pull-ups: R62 (SCL), R61 (SDA), 2K7 1 % | MB1191 p. 3; other end on the net of R34, R46 and R54, expected 3V3 (to check on the drawing) |
| On I2C3: WM8994 and touch panel only. Camera (`DCMI_SDA`/`DCMI_SCL`), CN2 and Arduino on I2C1 (PB9/PB8) | MB1191 p. 3; UM2470 Rev 2, Table 3 (CN2), p. 21. UM2470 section 4.8, p. 17 says the codec bus is shared with the camera and CN2: the schematic is followed |
| `TIMINGR` for 100 kHz at 16 MHz: PRESC 0x3, SCLL 0x13, SCLH 0xF, SDADEL 0x2, SCLDEL 0x4 | RM0385 Rev 9, Table 187, p. 978 |
| `I2C_TIMINGR` fields: PRESC 31:28, SCLDEL 23:20, SDADEL 19:16, SCLH 15:8, SCLL 7:0; written with PE = 0 | RM0385 Rev 9, section 30.9.5, p. 1002 |
| I2C register offsets and bits (CR1, CR2, TIMINGR, ISR, ICR, RXDR, TXDR) | RM0385 Rev 9, Table 196, p. 1009 |
| Controller mode: NACK sends a STOP by itself; AUTOEND = 0 sets TC for a RESTART | RM0385 Rev 9, section 30.4.9, p. 970 and p. 974 |
| Software reset: PE low for at least three APB cycles | RM0385 Rev 9, section 30.4.6, p. 955 |
| `RCC_APB1RSTR` at offset 0x20 | RM0385 Rev 9, section 5.3.7, p. 159 |
| `RCC_DCKCFGR2` at offset 0x90, reset value 0; `I2C3SEL` bits 21:20, 10 = HSI | RM0385 Rev 9, section 5.3.26, p. 195–196 |
| `RCC_CR` reset value 0x0000 XX83 (HSION set); HSION and HSIRDY | RM0385 Rev 9, p. 145 and p. 147. `RccInit216MHz` never clears HSION (`dev/common/rcc/rcc.c`) |
| I2C3 base 0x4000 5C00; I2C3RST bit 23 of `RCC_APB1RSTR`; I2C3EN bit 23 of `RCC_APB1ENR` | RM0385 Rev 9, p. 73, p. 160, p. 169 |
| Tpon ≥ 200 ms, Trsi ≥ 200 ms | FocalTech FT5336GQQ datasheet v0.6, section 3.5, Table 3-5 |
| SCL frequency 10 to 400 kHz | FT5336GQQ v0.6, Table 2-2 |
| Chip ID register 0xA8 = 0x51; `TD_STATUS` 0x02, mask 0x0F, at most 5 points; point 1 at 0x03–0x06 (12-bit positions); 200 ms wait before access | ST `stm32-ft5336` component, commit `8edacf0` used by STM32CubeF7 `Drivers/BSP/Components/ft5336` (same code as tag v1.0.2): `ft5336.h`, `ft5336.c` |
| A `TD_STATUS` count above `FT5336_MAX_DETECTABLE_TOUCH` (5) is set to zero ("If invalid number of touch detected, set it to zero") | ST `stm32-ft5336`, commit `8edacf0`, `ft5336.c`, `ft5336_TS_DetectTouch` |
| X and Y swapped, no inversion, no scaling at address 0x70 | ST `32f746gdiscovery-bsp`, `stm32746g_discovery_ts.c` (`TS_SWAP_XY`, `BSP_TS_GetState`) |
| Colour values of `colors.yaml` | `palette[]`, `WHITE` and `GREY` of `dev/apps/10-touch-paint/main.c` |

The FocalTech datasheet v0.6 has no register map; the ST driver is the
register reference. Not verified: the I-cache size (not needed) and the
FT5336 report rate (the Paint polls every 10 ms).

## 6. Issues and labels

The labels of `tests/host/tui/README.md` section 6 apply.

| Lot | Issue | Sub-steps |
|:--|:--|:--|
| 1. I2C and touch drivers, 10-touch-paint run in place | #99 | G2 to G13, proofs (G24) |
| 2. TOUCH_ID and TOUCH_READ, protocol 1.4, drawing commands and tests | #100 (label `paused` removed on 19/11/2026) | G14 to G23j, TUI (G26, G27), proofs (G25, G28) |

Each pull request carries its label and `Refs #n`. `Closes #n` acts only on
the default branch: each lot issue is closed by hand with a comment, after
the tag (section 8).

## 7. Working rules

The rules of `ci/README.md` section 9 apply, with these additions:

- One file per sub-branch `phaseG-touch/<task>`, made from the integration
  branch just merged. Pull requests pass one at a time.
- Exceptions, each one sub-branch with one commit per file, so that no check
  goes red. `tests/host/tui/tests/test_catalog.py` ties the `HIL_CMD_*`
  names of `hil_protocol.h` to `commands.yaml` in both directions, and
  `commands.yaml` to `COMMANDS` of `expected.py`; the HIL stage compares CAPS
  with `expected.py`. As applied:
  - G20 (#123): `hil_protocol.h` names, `commands.yaml`, `commands.c`,
    `expected.py`, four commits;
  - G23 to G23j (#126), at the developer's request: one branch,
    `phaseG-touch/touch-accuracy`, 24 commits, committed only after the
    board checks;
  - G26 (#127, 15 commits) and G27 (#128, 3 commits): one branch each, one
    commit per file.
- A board check counts as passed once its run folder (`work/hil-results/`)
  has been read, not before.
- A fix found on the board goes through the same order: specification
  first, then the code (G19a to G19d).
- Submodule: a branch in `stm32f7508-dk`, merged locally into its `main`
  with `--no-ff`, pushed, then deleted; no pull request there. The pointer
  is then committed in this repository on a sub-branch, with its pull
  request. `board.h` and `board.c` shared one pointer, so that a
  declaration never came without its definition.
- At the start of each sub-step, `git fetch --prune` and
  `git log --oneline origin/phaseG-touch/integration..origin/develop`; if
  develop moved, it comes in through a synchronisation sub-branch.
- Shared files (root `Makefile`, `ci/`, `.gitignore`, `commands.yaml`,
  `mcu.h`, `board.h`, `board.c`) are compared with develop, or with the
  submodule's `origin/main`, before any change.
- A pull request that only changes `work/doc_zak/**` or `*.md` skips the
  board stages (`ci/README.md` section 4.1).

## 8. Release

Tag `v0.6.0` closes phase G once C1 to C8 are met, with `hil-bench`
`fw=1.4.0 proto=1.4`. Before each release pull request,
`git log --oneline origin/<source>..origin/<target>` must be empty.

| Step | Action |
|:--|:--|
| R0 | `origin/develop` checked: still `a49c55c` on 23/11/2026, nothing to synchronise |
| R1 | Pull request `phaseG-touch/integration` → `develop`; Jenkins: 246 passed, 8 skipped |
| R2 | Pull request `develop` → `main` |
| R3 | Annotated tag `v0.6.0` "Touch panel and paint app" on the merge commit of `main`, pushed; issues #99 and #100 closed by hand with a comment |
| R4 | Pull request `main` → `develop`, so that develop holds the merge commit; then the phase H session is told that develop moved |

## 9. Sub-steps

One file per sub-step, in this order, except the exceptions of section 7.
"HIL" is the total of `python3 -m pytest tests/host/hil` on the board after
the sub-step.

| # | File | Lot | Criteria | HIL | Status |
|:-:|:--|:-:|:--|:--|:--|
| G0 | Branch `phaseG-touch/integration` | — | — | 216 | Done |
| G1 | `work/doc_zak/phaseG_touch.md` | — | — | 216 | Done, #101 |
| G2 | `stm32f7508-dk/mcu.h` (submodule) | 1 | C1 | — | Done, submodule `73be397` |
| G3 | Submodule pointer | 1 | C7 | 216 | Done, #102 |
| G4 | `dev/common/i2c/i2c.h` | 1 | C1 | 216 | Done, #103 |
| G5 | `dev/common/i2c/i2c.c` | 1 | C1 | 216 | Done, #104 |
| G6 | `stm32f7508-dk/board.h` (submodule) | 1 | C1 | — | Done, submodule `bcf7c73` |
| G7 | `stm32f7508-dk/board.c` (submodule) | 1 | C1 | — | Done, submodule `51bd1c3` |
| G8 | Submodule pointer | 1 | C7 | 216 | Done, #106 |
| G9 | `dev/common/touch/touch.h` | 1 | C2, C5 | 216 | Done, #107 |
| G10 | `dev/common/touch/touch.c` | 1 | C2, C5 | 216 | Done, #108 |
| G11 | `dev/apps/10-touch-paint/main.c` | 1 | C2, C5, C6 | 216 | Done, #109 |
| G12 | `dev/apps/10-touch-paint/README.md` | 1 | C6 | 216 | Done, #110 |
| G13 | `Makefile` (10-touch-paint) | 1 | C6, C8 | 216 | Done, #111 |
| G24 | `work/doc_zak/phaseG_touch.md` 1.1 (scope change, lot 1 proofs) | 1 | — | 216 | Done, #112 |
| G14 | `tests/host/hil/cases/test_protocol_caps.py` (pages through `next`) | 2 | C7 | 216 | Done, #113 |
| G15 | `tests/protocol.md` 1.10 (protocol 1.4, sections 6.20 to 6.22) | 2 | C2 to C4 | 216 | Done, #114 |
| G16 | `tests/firmware/hil_bench/inc/hil_protocol.h` (proto 1.4, fw 1.4.0, keys, start time) | 2 | C2, C3 | 216 | Done, #115 |
| G17 | `tests/firmware/hil_bench/inc/touch_commands.h` | 2 | C2, C3 | 216 | Done, #116 |
| G18 | `tests/firmware/hil_bench/touch_commands.c` | 2 | C1 to C4 | 216 | Done, #117 |
| G19 | `Makefile` (hil-bench: `i2c`, `touch`, `touch_commands.c`) | 2 | C8 | 216 | Done, #118 |
| G19a | `tests/protocol.md` 1.11 (count above 5 is no touch) | 2 | C3 | 216 | Done, #119 |
| G19b | `dev/common/touch/touch.h` 1.1 | 2 | C3 | 216 | Done, #120 |
| G19c | `dev/common/touch/touch.c` 1.1 | 2 | C3 | 216 | Done, #121 |
| G19d | `tests/firmware/hil_bench/touch_commands.c` 1.1 | 2 | — | 216 | Done, #122 |
| G20 | `hil_protocol.h`, `commands.yaml`, `commands.c`, `expected.py` (exception, 4 commits) | 2 | C2, C7 | 216 | Done, #123 |
| G21 | `tests/host/hil/pyproject.toml` (marker `touch`) | 2 | C7 | 216 | Done, #124 |
| G22 | `tests/host/hil/cases/test_touch.py` | 2 | C2 to C5 | 222 + 2 skipped | Done, #125 |
| G23 | `LCD_CIRCLE` (protocol 1.12 to firmware and tests), accuracy test, `touch_check.yaml` | 2 | C5, C7 | 234 + 7 skipped | Done, #126 |
| G23i | Drawing test, then `LCD_LINE` (protocol 1.13 to firmware and tests) | 2 | C6, C7 | 246 + 8 skipped | Done, #126 |
| G23j | `tests/host/config/colors.yaml`, `HIL_DRAW_COLOR` | 2 | C6 | 246 + 8 skipped | Done, #126 |
| G25 | `work/doc_zak/phaseG_touch.md` 1.2 (lot 2 proofs, release plan) | 2 | — | 246 + 8 skipped | Done, with G28 |
| G26 | TUI run options: `run_options.yaml`, `core/run_options.py`, `core/runner.py`, `core/report.py`, `ui/options_screen.py`, `ui/tests_pane.py`, `ui/app.py`, `test_touch.py` 1.5, their tests, `README.md`, `hil_tui.md`, two scenarios (removed by G27) | 2 | C5, C6 | 246 + 8 skipped | Done, #127 |
| G27 | `touch_targets.yaml` and `lcd_drawing.yaml` removed, `touch_check.yaml` 1.1 | 2 | C5 | 246 + 8 skipped | Done, #128 |
| G28 | `work/doc_zak/phaseG_touch.md` 1.3 (TUI proofs) | 2 | — | 246 + 8 skipped | This version |

## 10. Proofs

### 10.1 Lot 1

Recorded on 19/11/2026. Board checks were made by the developer after
`make 10-touch-paint-flash` and a reset with B2.

| # | Proof | Result |
|:-:|:--|:--|
| C1 | Code review of `dev/common/i2c/i2c.c` (#104) | Every flag wait, the `BUSY` wait, the STOPF wait of the recovery and the HSIRDY wait of `I2cInit` stop after `I2C_POLL_TIMEOUT` (1,000,000 polls) and return `TIMEOUT`; C2 passes |
| C2 | Paint console after a reset | `touch: chip_id=0x51` |
| C5 | Paint console, `touch: x=… y=…` on each touch down | Top left: `x=1 y=1`, `x=15 y=7`, `x=7 y=21` (x < 60, y < 60). Top right: `x=476 y=25`, `x=479 y=29`, `x=479 y=35` (x > 420, y < 60). Bottom right: `x=477 y=263`, `x=479 y=269`. Bottom left: `x=22 y=270`, `x=1 y=271`. Highest values over all lines: x = 479, y = 271 |
| C6 | Paint on the board | Console `boot: 08-custombootloader`, `boot: QSPI id 0x0018BA20`, `boot: app SP 0x20010000, PC 0x900000DD`, `boot: jumping`, `touch paint`. Strokes under the finger over the whole canvas without gaps; colour selection and clear area work (developer's check) |
| C7 | Required check `continuous-integration/jenkins/pr-merge` | SUCCESS on #101 to #104 and #106 to #111 (HIL 216 passed). The sha256 of the 14 existing images other than `hil-bench` are unchanged from G2 to G13 |
| C8 | `make 10-touch-paint-app-size` | Text 4300 bytes from `0x90000000`, far below offset `0x00FF0000`; framebuffer in `.framebuffer` (SRAM, NOLOAD); `hil-bench` unchanged (text 10736 bytes) |

Observation of 19/11/2026: one `touch: read error` right after
`touch: chip_id=0x51`, after a reset with B2. Explained on 20/11/2026: the
FT5336 reports a `TD_STATUS` count above 5 when nothing is touched, which
the driver rejected as `FAILURE` (see 10.2). After G19c the Paint shows no
read error (developer's check).

### 10.2 Lot 2

Recorded on 20/11/2026, `hil-bench` flashed from the branch under test.

| # | Proof | Result |
|:-:|:--|:--|
| C2 | miniterm after G20: `CMD id=4 command=TOUCH_ID`; pytest `test_touch_id`, `test_touch_id_after_reset` | `RESULT id=4 status=OK chip_id=0x51`; both tests passed (G22) |
| C3 | Board run of G20 before the fix | `TOUCH_READ` answered `status=ERR code=DEVICE_ERROR` on every call while `TOUCH_ID` answered `0x51`: a `TD_STATUS` count above 5 at rest. Fixed by G19a to G19d |
| C3 | miniterm after the fix, screen untouched; pytest `test_touch_read_untouched`, `test_touch_read_after_lcd_init` | `RESULT id=7 status=OK points=0`; both tests passed |
| C4 | miniterm: `CMD id=8 command=TOUCH_READ x=1`; pytest `test_touch_extra_argument` (2 cases) | `RESULT id=8 status=ERR code=INVALID_ARGUMENT`; both cases passed, state unchanged |
| C5 | miniterm, one finger on the screen; operator tests `test_touch_corner[top_left]` and `[top_right]` with `HIL_OPERATOR=1` | `RESULT id=6 status=OK points=1 x=443 y=238`; both corner tests passed. The corner coordinates of these runs were not copied (NON VÉRIFIÉ); those of 23/11/2026 are in 10.3 |
| C5 | Operator tests `test_touch_accuracy[target1..5]`: five black discs of radius 20 at random positions | 5 passed: each touched point inside its disc; the screen no longer flashes between targets; the last disc is erased |
| C6 | Operator test `test_touch_draw`, with `HIL_DRAW_COLOR=rouge`, then `0x07E0`, then `blanc` | Strokes follow the finger, in red then green, `1 passed` each; `blanc` refused before any drawing. With `LCD_LINE` (one exchange per point) the stroke follows the finger much faster than with one `LCD_CIRCLE` per disc (developer's check) |
| C7 | `python3 -m pytest tests/host/hil` on the board after #126 | 246 passed, 8 skipped (254 collected); the 8 skipped are the operator tests. Required check green on #113 to #126 (merged). TUI host tests: 291 passed, 24 deselected |
| C8 | `arm-none-eabi-size` of `hil-bench` | Text 12645 bytes, below 64 KB |

Jenkins incidents of 20/11/2026, not caused by the changes: the JDK update
of 09:22 stopped Jenkins from starting processes until it was restarted;
the ST-LINK port became `/dev/ttyACM1` (section 3); one TUI timing test
(`test_progress_box.py::test_auto_close_waits_until_on_top`) timed out once
under load and passed on the next run.

### 10.3 TUI

Recorded on 23/11/2026, read in the run folders `work/hil-results/20261123-*`
(`run.json`, `events.jsonl`). Repository commit: `b1a4725-dirty` before the
commits of G26, `8f2ee7e` from 11:04, `34c83b2-dirty` from 11:30, `d8bfb4c`
from 11:35. Each pytest run flashed `hil-bench` (`fw=1.4.0 proto=1.4`)
first.

| # | Proof | Result |
|:-:|:--|:--|
| C2 to C6 | Run `114016`: `cases/test_touch.py`, `HIL_OPERATOR=1 HIL_DRAW_COLOR=yellow HIL_TOUCH_SEED=194504` set in the Options window | **14 passed**, verdict PASS |
| C5 | Corners of this run | Top left `x=33 y=34`, top right `x=470 y=31` |
| C5 | Targets 1 to 5 of this run, centres (110, 134), (405, 77), (64, 205), (382, 142), (158, 35) | Distances 18.6, 12.2, 7.2, 3.6 and 11.3 px, radius 20: 5 inside |
| C5 | Seed 194504 replayed from run `113551` | Same five centres. In `113551`, targets 1 and 5 were outside (24.1 and 32.2 px) and passed at the same places in `114016`: most likely the gesture, not the panel |
| C5 | `touch_check` 1.1, runs `113021`, `113052`, `113106` | PASS, FAIL, PASS. The FAIL read `points=0` at the last step: most likely no finger on the screen (NON VÉRIFIÉ) |
| C6 | `test_touch_draw` in seven runs | All passed: black 443, 159 and 29 points, green 362 and 307, yellow 134 and 119; drawn points read back with `LCD_PIXEL` |
| C7 | `python3 -m pytest tests/host/tui`; `tests/host/hil -m unit`; collection | 351 passed, 24 deselected, with the files of #127 and again with those of #128; 42 passed and 254 collected on the merged code (`59a2bc9`). Required check green on #127 and #128 |

Runs that failed, all before the final run:

| Run | Failure |
|:--|:--|
| `103628`, `110507` | `touch_check` 1.0: `points` expected 1, got 0. It read once, the result within 46 to 154 ms after the answer (all these runs), so the finger had to stay on the screen while answering: replaced by 1.1 |
| `103643`, `103713`, `110532` | `touch_targets`, same message, most likely the same cause: removed by G27 |
| `105300` | Top left: no touch within 10 s; top right: `x=313 y=177`; target 4: 30.3 px |
| `105351` | Corners touched the other way round (`x=472 y=19` for top left, `x=1 y=34` for top right); target 1: 27.7 px |
| `105658` | Top left: `x=447 y=21`; top right passed |
| `113520` | Interrupted by the operator; top left: no touch within 10 s |

Not played in the TUI: Export (F4) of a run with options, a colour typed as
`0x07E0`, `blanc`, and red. Covered without the board: the report of run
`114016`, built by `core/report.py`, has the line `Run options
HIL_OPERATOR=1 HIL_DRAW_COLOR=yellow HIL_TOUCH_SEED=194504`; `0x07E0` gives
green and `blanc` is refused with "white is invisible on the white screen"
by the functions of `test_touch.py`; the typed field is tested by
`test_ui_options.py`. Red, `0x07E0` and `blanc` were played from a terminal
on 20/11/2026 (10.2).
