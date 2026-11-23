<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       dev/apps/10-touch-paint/README.md
\brief      10-touch-paint: finger painting with the FT5336 touch panel.

\author     Z. BEN-AKKA
\version    1.0
\date       19/11/2026

\details
  How to build, flash and check the application. Acceptance criteria, design
  choices and hardware sources are in work/doc_zak/phaseG_touch.md.

\section touch_paint_readme_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 19/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
-->

# 10-touch-paint

## Purpose

Paint with a finger on the 480 × 272 LCD of the STM32F7508-DK. The
application polls the FT5336 touch controller on I2C3 (`dev/common/i2c`,
`dev/common/touch`) and runs in place from the QSPI flash, behind the
08 bootloader. Criteria C2, C5 and C6 of phase G are checked with it; see
[phaseG_touch.md](../../../work/doc_zak/phaseG_touch.md).

## Build and flash

```sh
make 10-touch-paint          # builds 10-touch-paint-app and 10-touch-paint-boot
make 10-touch-paint-flash    # app to the QSPI flash (0x90000000), then the 08 bootloader
```

Console (one program on the port at a time):

```sh
python3 -m serial.tools.miniterm /dev/ttyACM0 115200 --eol CRLF --echo
```

## Expected console output

```text
boot: 08-custombootloader
boot: QSPI id 0x0018BA20
boot: app SP 0x<stack top>, PC 0x<reset handler>
boot: jumping

touch paint
touch: chip_id=0x51
touch: x=<n> y=<n>        one line each time a finger touches the screen
```

`touch: I2C init error` or `touch: chip_id error` stops the application.
`touch: read error` is printed once per series of failed reads; painting
resumes when the reads succeed again.

## Screen

| Area | Position | Action on touch down |
|:--|:--|:--|
| Colour swatches | y 0–31, x 0–383, 8 × 48 px | Select the colour; a white mark shows it |
| Clear area (grey) | y 0–31, x 384–479 | Clear the canvas |
| Canvas (white) | y 32–271 | Paint with a brush of radius 4 px |

The first colour, black, is selected at start. Circles every 2 px join two
successive points, so a fast stroke has no gaps.

## Checks

| Criterion | What to do | Expected |
|:--|:--|:--|
| C2 | Read the console after the reset | `touch: chip_id=0x51` |
| C5 | Touch the top-left corner, then the top-right corner | Top left: x < 60 and y < 60. Top right: x > 420 and y < 60. Every line: x ≤ 479 and y ≤ 271 |
| C6 | Paint in the four corners of the canvas and in its centre, then draw fast; touch a swatch; touch the clear area | The stroke appears under the finger without gaps; the colour changes; the canvas becomes white |

## Limits

- Only the first point is read: no multi-touch.
- Polled every 10 ms, without the INT line (PI13); the FT5336 report rate is
  NOT VERIFIED.
- The FT5336 reset is the MCU NRST: the application waits until 300 ms after
  its start before reading the chip ID (200 ms needed).
- The D-cache stays off; the 08 bootloader enables the I-cache.
