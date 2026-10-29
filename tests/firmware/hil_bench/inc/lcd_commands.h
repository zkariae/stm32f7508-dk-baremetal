// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/inc/lcd_commands.h
\brief      GPIO_CONFIG and LCD commands of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.0
\date       29/10/2026

\details
  Implements protocol.md sections 6.11 to 6.19. The handlers have the
  CommandRun signature of commands.h and are listed in its table.

\section lcd_commands_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 29/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef LCD_COMMANDS_H
#define LCD_COMMANDS_H

#include <stdint.h>

#include "commands.h"

/// GPIO_CONFIG: mode, alternate function and level of one pin (section 6.11).
const char *GpioConfigCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_INIT: bring up the panel with a black frame (section 6.13).
const char *LcdInitCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_CLOCK: PLLSAI state and pixel clock (section 6.14).
const char *LcdClockCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_TIMING: panel timings decoded from the LTDC (section 6.15).
const char *LcdTimingCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_LAYER: configuration of LTDC layer 1 (section 6.16).
const char *LcdLayerCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_SCAN: frames scanned and FIFO underrun during a window (section 6.17).
const char *LcdScanCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_FILL: set every framebuffer pixel to one colour (section 6.18).
const char *LcdFillCmd(const CommandArg *args, uint32_t count, Record *result);

/// LCD_PIXEL: read one framebuffer pixel (section 6.19).
const char *LcdPixelCmd(const CommandArg *args, uint32_t count, Record *result);

#endif /* LCD_COMMANDS_H */
