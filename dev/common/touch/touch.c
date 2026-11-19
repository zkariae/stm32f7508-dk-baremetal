// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/touch/touch.c
\brief      FT5336 capacitive touch controller, polled over I2C.

\author     Z. BEN-AKKA
\version    1.0
\date       18/11/2026

\details
  API documented in touch.h.

\section touch_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 18/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "touch/touch.h"

#include <stdint.h>

#include "defines.h"
#include "i2c/i2c.h"

/* FT5336 registers (ST stm32-ft5336 driver, commit 8edacf0) */
#define FT5336_REG_TD_STATUS 0x02U ///< Number of points in bits 3:0; point 1 follows.
#define FT5336_REG_CHIP_ID   0xA8U
#define FT5336_TD_MASK       0x0FU

/// TD_STATUS, then P1_XH, P1_XL, P1_YH, P1_YL (0x03-0x06).
#define TOUCH_READ_LEN 5U

/*!
\brief  Build a 12-bit coordinate: bits 3:0 of the high byte, then the low byte.
\details The other bits of the high byte (event flag, touch ID) are ignored.
\param  high  P1_XH or P1_YH.
\param  low   P1_XL or P1_YL.
\return Coordinate, 0 to 4095.
*/
static uint16_t ft5336_coord(uint8_t high, uint8_t low)
{
  return (uint16_t)(((high & 0x0FU) << 8) | low);
}

int TouchInit(const I2c *i2c)
{
  return I2cInit(i2c);
}

int TouchReadId(const I2c *i2c, uint8_t addr7, uint8_t *id)
{
  uint8_t value;
  int rc = I2cReadReg(i2c, addr7, FT5336_REG_CHIP_ID, &value, 1);

  if (rc == SUCCESS) {
    *id = value;
  }
  return rc;
}

int TouchRead(const I2c *i2c, uint8_t addr7, uint32_t *points, TouchPoint *p1)
{
  uint8_t buf[TOUCH_READ_LEN];
  // One transfer, so the number of points and the coordinates belong together
  int rc = I2cReadReg(i2c, addr7, FT5336_REG_TD_STATUS, buf, TOUCH_READ_LEN);
  uint32_t n;

  if (rc != SUCCESS) {
    return rc;
  }
  n = buf[0] & FT5336_TD_MASK;
  if (n > TOUCH_MAX_POINTS) {
    return FAILURE;
  }
  if (n >= 1U) {
    // Screen x is the Y register, screen y the X register (ST BSP, TS_SWAP_XY)
    p1->x = ft5336_coord(buf[3], buf[4]);
    p1->y = ft5336_coord(buf[1], buf[2]);
  }
  *points = n;
  return SUCCESS;
}
