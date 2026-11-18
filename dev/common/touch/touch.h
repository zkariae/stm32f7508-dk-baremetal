// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/touch/touch.h
\brief      FT5336 capacitive touch controller, polled over I2C.

\author     Z. BEN-AKKA
\version    1.0
\date       18/11/2026

\details
  The I2C bus and the 7-bit address are parameters (BOARD_I2C_TOUCH,
  FT5336_ADDR on the STM32F7508-DK). No interrupt: the application polls.
  The FT5336 answers 200 ms after its reset (FT5336GQQ v0.6, Table 3-5); the
  application waits for it, the driver never waits.
  Coordinates are those of the 480x272 screen: screen x is the FT5336 Y
  register, screen y its X register, without inversion or scaling (ST BSP,
  TS_SWAP_XY).

\section touch_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 18/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef TOUCH_H
#define TOUCH_H

#include <stdint.h>

#include "i2c/i2c.h"

#define FT5336_CHIP_ID   0x51 ///< Value of the chip ID register 0xA8 (ST ft5336 driver).
#define TOUCH_MAX_POINTS 5U   ///< Highest number of points the FT5336 reports.

/// One touch point in screen coordinates.
typedef struct {
  uint16_t x; ///< Column, 0 at the left.
  uint16_t y; ///< Line, 0 at the top.
} TouchPoint;

/*!
\brief  Configure the I2C bus of the touch controller (I2cInit()).
\param  i2c  I2C the controller is on.
\return SUCCESS, or TIMEOUT if the I2C kernel clock does not start.
*/
int TouchInit(const I2c *i2c);

/*!
\brief  Read the chip ID register (0xA8); FT5336_CHIP_ID is expected.
\param  i2c    I2C configured by TouchInit().
\param  addr7  7-bit address of the controller.
\param  id     Output: chip ID; set on SUCCESS only.
\return SUCCESS; TIMEOUT on a NACK or a wait past its limit; FAILURE on a bus
        error or a lost arbitration.
*/
int TouchReadId(const I2c *i2c, uint8_t addr7, uint8_t *id);

/*!
\brief  Read the number of points and the first point, in one transfer.
\param  i2c     I2C configured by TouchInit().
\param  addr7   7-bit address of the controller.
\param  points  Output: number of points, 0 to TOUCH_MAX_POINTS; set on SUCCESS only.
\param  p1      Output: first point; set on SUCCESS when points is at least 1.
\return SUCCESS; TIMEOUT on a NACK or a wait past its limit; FAILURE on a bus
        error, a lost arbitration, or a number of points above TOUCH_MAX_POINTS.
*/
int TouchRead(const I2c *i2c, uint8_t addr7, uint32_t *points, TouchPoint *p1);

#endif
