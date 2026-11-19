<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       work/doc_zak/phaseG_touch.md
\brief      Phase G: touch panel, 10-touch-paint run in place and HIL touch commands.

\author     Z. BEN-AKKA
\version    1.1
\date       19/11/2026

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

**Scope change (18/11/2026).** Nothing under `tests/` changes in phase G: a
phase H moves the host side of the bench (`tests/host/hil`, the `hil_events`
plugin, the TUI) to its own repository, and changes there would conflict
with that move. Lot 1 (drivers and Paint) is delivered; lot 2 (protocol 1.4,
`TOUCH_ID` and `TOUCH_READ`, host tests, CAPS test, TUI scenario, and the
`hil-bench` Makefile lines for `i2c` and `touch`) is paused until the
developer decides otherwise.

Phase G delivers `v0.6.0` with lot 1 only: `hil-bench` stays
`fw=1.3.0 proto=1.3`.

Out of scope, proposed only on request: touch interrupt (EXTI), a Paint
variant in internal flash, text font, SDRAM, DMA2D, audio codec, TUI issues
#25, #27, #28 and #89.

## 2. Acceptance criteria

The criteria are frozen. No criterion is added without an explicit decision
of the developer. The status column records the scope change of section 1;
the proofs are in section 10.

| # | Criterion | Proof | Type | Status (19/11/2026) |
|:-:|:--|:--|:--|:--|
| C1 | Generic I2C driver, every wait bounded | Each hardware wait returns `TIMEOUT` past its limit (code review); `I2cInit` sets HSION and waits for HSIRDY with a limit; C2 passes | Automatic | Met; C2 passes through the Paint |
| C2 | FT5336 identified | `TOUCH_ID` returns `chip_id=0x51`, also when sent right after a reset, HELLO and CAPS (before 300 ms) | Automatic (Jenkins) | Met by the Paint console (`touch: chip_id=0x51`); the `TOUCH_ID` part is paused |
| C3 | Untouched screen gives no point | `TOUCH_READ` returns `points=0` before and after `LCD_INIT`. **Fails if somebody touches the screen during a Jenkins build** | Automatic | Paused (lot 2) |
| C4 | Rejected requests change nothing | An extra argument gives `INVALID_ARGUMENT`; then `TOUCH_READ` still returns `points=0` and `TOUCH_ID` still `0x51` | Automatic | Paused (lot 2) |
| C5 | Axis directions | Top-left corner: x < 60 and y < 60. Top-right corner: x > 420 and y < 60. Always x ≤ 479 and y ≤ 271. Two corners, since one corner does not detect swapped axes. Proved by the operator test of `test_touch.py` (`HIL_OPERATOR=1`, waits at most 10 s for `points=1`) and by the TUI scenario `touch_check.yaml` | Operator | Met with the Paint console (`touch: x=… y=…`); the test and the scenario are paused |
| C6 | Paint run in place | After `make 10-touch-paint-flash`: the stroke appears under the finger over the whole surface (four corners and centre), without gaps when the finger moves fast; the colour bar changes the colour; the clear area clears the screen; the console shows `boot: jumping` | Operator | Met |
| C7 | No regression | HIL suite 222 passed, 2 skipped (224 collected); Jenkins check green on every pull request; in lot 1, the sha256 of the other images unchanged | Automatic | Met with 216 passed (lot 1 adds no test) |
| C8 | Memory | `hil-bench` below 64 KB of internal flash; `10-touch-paint-app` below offset `0x00FF0000` of the QSPI flash (test area); framebuffer in internal SRAM | Automatic (`make <image>-size`) | Met; `hil-bench` unchanged |

## 3. Constraints

| Constraint | Consequence |
|:--|:--|
| A Jenkins build flashes `hil-bench` into the internal flash, over the 08 bootloader | To see the Paint again: `make 10-touch-paint-flash`. Every board check of the Paint starts with it |
| 08, 09, 07-lcd-logo-xip and 10-touch-paint all put their application at `0x90000000` | Flashing one overwrites the others |
| Code executed from the QSPI flash cannot use the QUADSPI in indirect mode | `touch` and `i2c` do not depend on `qspi`; the Paint never reconfigures the QUADSPI |
| I2C3 is shared with the WM8994 audio codec (address 0x1A), not driven by the firmware | The address is a parameter of each transfer; `BUSY` is waited for with a limit before a START; NACK, BERR and ARLO are reported |
| The FT5336 reset is tied to NRST (section 5) | Every MCU reset (flash, `make reset`, `make reset-sw`) restarts its 200 ms start time |
| 18 command names make three CAPS pages (8 + 7 + 3, whatever the request ID) | Lot 2: `test_protocol_caps.py` follows `next` for any number of pages, merged before the new commands |
| TUI `expect` values are compared for equality only | Lot 2: coordinate limits are checked by the operator test; the scenario checks `points=1` and asks the operator |
| `TOUCH_READ` with the screen untouched must give 0 point | Lot 2: **keep your hands off the screen during a Jenkins build** |
| The board and its port serve Jenkins and the developer in turn | Before a check by hand, read `fw=` and `build=` in the banner; keep the TUI, miniterm and minicom closed during a build |

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
tests/firmware/hil_bench/    Paused (lot 2)
├── inc/hil_protocol.h       Names, keys, 300 ms limit, proto 1.4, fw 1.4.0
├── inc/touch_commands.h
├── touch_commands.c         TOUCH_ID and TOUCH_READ
└── commands.c               Command table: 18 names
tests/host/                  Paused (lot 2)
├── config/commands.yaml     Touch group: TOUCH_ID, TOUCH_READ
├── hil/cases/expected.py    COMMANDS, TOUCH_CHIP_ID, screen size
├── hil/cases/test_touch.py  Marker touch
└── tui/scenarios/touch_check.yaml
```

Design choices:

| Item | Choice | Reason |
|:--|:--|:--|
| I2C kernel clock | HSI, 16 MHz (`I2C3SEL` = 10) | The same `TIMINGR` in `hil-bench`, including its HSI fallback, and in the Paint |
| Bus speed | 100 kHz, standard mode | Within the FT5336 range (10 to 400 kHz) |
| `TIMINGR` | `0x30420F13`: PRESC 3, SCLDEL 4, SDADEL 2, SCLH 0x0F, SCLL 0x13 | RM0385 table for 16 MHz, 100 kHz |
| Start time | The Paint waits until 300 ms after its start (`SysTickMs()`) before the chip ID. Lot 2: `TOUCH_ID` and `TOUCH_READ` wait the same way | 200 ms minimum (Tpon, Trsi) plus a margin; nothing waits at startup, the banner is unchanged |
| I2C init | Paint: at start. Lot 2: at the first touch command; HSION set, HSIRDY waited for with a limit | `main.c` of `hil-bench` unchanged |
| Axes | Screen x = FT5336 Y register, screen y = FT5336 X register, no inversion, no scaling | ST BSP (`TS_SWAP_XY`); proved by C5 |
| `TOUCH_ID` result (lot 2) | `chip_id=0x<2 hexadecimal digits>` | `id` is a reserved key; the host compares with 0x51, as for `QSPI_ID` |
| `TOUCH_READ` result (lot 2) | `points=<0..5>`, then `x=<n> y=<n>` of point 1 when `points` ≥ 1 | Short line; multi-touch out of scope |
| Error codes | Driver: NACK or a wait past its limit gives `TIMEOUT`; BERR, ARLO, `TD_STATUS` above 5 give `FAILURE`. Lot 2: `DEVICE_TIMEOUT` and `DEVICE_ERROR` | `DEVICE_TIMEOUT` only when the chip does not answer |
| Paint strokes | Successive points joined with FbCircle, one circle every 2 px | No gaps when the finger moves fast |

Sizes measured on 19/11/2026: `10-touch-paint-app` text 4300 bytes from
`0x90000000` (8 KB estimated); `10-touch-paint-boot` is the 08 bootloader,
text 2709 bytes, same sha256 as `08-custombootloader-boot`; `hil-bench`
unchanged, text 10736 bytes. Framebuffer 480 × 272 RGB565 = 261120 bytes in
the 256 KB SRAM (`.framebuffer`, NOLOAD); `.data`, `.bss` and the stack
in DTCM. The 08 bootloader enables the I-cache before the jump; the D-cache
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
| X and Y swapped, no inversion, no scaling at address 0x70 | ST `32f746gdiscovery-bsp`, `stm32746g_discovery_ts.c` (`TS_SWAP_XY`, `BSP_TS_GetState`) |

The FocalTech datasheet v0.6 has no register map; the ST driver is the
register reference. Not verified: the I-cache size (not needed) and the
FT5336 report rate (the Paint polls every 10 ms).

## 6. Issues and labels

The labels of `tests/host/tui/README.md` section 6 apply.

| Lot | Issue | Sub-steps |
|:--|:--|:--|
| 1. I2C and touch drivers, 10-touch-paint run in place | #99 | G2 to G13, proofs |
| 2. TOUCH_ID and TOUCH_READ, protocol 1.4 | #100, label `paused` | G14 to G23 |

Each pull request carries its label and `Refs #n`. `Closes #n` acts only on
the default branch: each lot issue is closed by hand with a comment. #100
stays open while lot 2 is paused.

## 7. Working rules

The rules of `ci/README.md` section 9 apply, with these additions:

- One file per sub-branch `phaseG-touch/<task>`, made from the integration
  branch just merged. Pull requests pass one at a time.
- Lot 2 only, when it resumes: two deliberate exceptions, each one
  sub-branch with one commit per file, so that no check goes red:
  - A: `hil_protocol.h` and `commands.yaml`, because `ci/scripts/build.sh`
    compares their command names in both directions;
  - B: `commands.c` and `expected.py`, because the HIL stage compares CAPS
    with `expected.py`.
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

Tag `v0.6.0` closes lot 1 of phase G once C1, C2 (Paint), C5 to C8 are met,
with `hil-bench` unchanged (`fw=1.3.0 proto=1.3`):
`phaseG-touch/integration` → `develop` → `main`, then `main` → `develop`.
Before each release pull request,
`git log --oneline origin/<source>..origin/<target>` must be empty.

## 9. Sub-steps

One file per sub-step, in this order. "HIL" is the expected total of
`python3 -m pytest tests/host/hil` on the board after the sub-step.

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
| G24 | `work/doc_zak/phaseG_touch.md` (scope change and proofs), moved after G13 | 1 | — | 216 | This version |
| G14 | `tests/host/hil/cases/test_protocol_caps.py` | 2 | C7 | — | Paused |
| G15 | `tests/protocol.md` | 2 | C2 to C4 | — | Paused |
| G16 | `tests/firmware/hil_bench/inc/hil_protocol.h` and `tests/host/config/commands.yaml` (exception A) | 2 | C2, C3 | — | Paused |
| G17 | `tests/firmware/hil_bench/inc/touch_commands.h` | 2 | C2, C3 | — | Paused |
| G18 | `tests/firmware/hil_bench/touch_commands.c` | 2 | C1 to C4 | — | Paused |
| G19 | `Makefile` (hil-bench) | 2 | C8 | — | Paused |
| G20 | `tests/firmware/hil_bench/commands.c` and `tests/host/hil/cases/expected.py` (exception B) | 2 | C2, C7 | — | Paused |
| G21 | `tests/host/hil/pyproject.toml` (marker `touch`) | 2 | C7 | — | Paused |
| G22 | `tests/host/hil/cases/test_touch.py` | 2 | C2 to C5 | — | Paused |
| G23 | `tests/host/tui/scenarios/touch_check.yaml` | 2 | C5 | — | Paused |

## 10. Proofs

Lot 1, recorded on 19/11/2026. Board checks were made by the developer
after `make 10-touch-paint-flash` and a reset with B2.

| # | Proof | Result |
|:-:|:--|:--|
| C1 | Code review of `dev/common/i2c/i2c.c` (#104) | Every flag wait, the `BUSY` wait, the STOPF wait of the recovery and the HSIRDY wait of `I2cInit` stop after `I2C_POLL_TIMEOUT` (1,000,000 polls) and return `TIMEOUT`; C2 passes |
| C2 | Paint console after a reset | `touch: chip_id=0x51` |
| C5 | Paint console, `touch: x=… y=…` on each touch down | Top left: `x=1 y=1`, `x=15 y=7`, `x=7 y=21` (x < 60, y < 60). Top right: `x=476 y=25`, `x=479 y=29`, `x=479 y=35` (x > 420, y < 60). Bottom right: `x=477 y=263`, `x=479 y=269`. Bottom left: `x=22 y=270`, `x=1 y=271`. Highest values over all lines: x = 479, y = 271 |
| C6 | Paint on the board | Console `boot: 08-custombootloader`, `boot: QSPI id 0x0018BA20`, `boot: app SP 0x20010000, PC 0x900000DD`, `boot: jumping`, `touch paint`. Strokes under the finger over the whole canvas without gaps; colour selection and clear area work (developer's check) |
| C7 | Required check `continuous-integration/jenkins/pr-merge` | SUCCESS on #101 to #104 and #106 to #111 (HIL 216 passed). The sha256 of the 14 existing images other than `hil-bench` are unchanged from G2 to G13 |
| C8 | `make 10-touch-paint-app-size` | Text 4300 bytes from `0x90000000`, far below offset `0x00FF0000`; framebuffer in `.framebuffer` (SRAM, NOLOAD); `hil-bench` unchanged (text 10736 bytes) |

Observation: one `touch: read error` right after `touch: chip_id=0x51`,
after a reset with B2; the next reads succeed. Probable cause, not
verified: the FT5336 answers its chip ID at 300 ms before its first touch
report is ready. Not blocking.
