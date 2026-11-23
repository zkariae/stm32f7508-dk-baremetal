// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/i2c/i2c.h
\brief      Polled I2C master, 7-bit addresses.

\author     Z. BEN-AKKA
\version    1.0
\date       18/11/2026

\details
  Each I2C controller is described by an I2c structure (instance, clocks,
  timing and SCL/SDA pins), defined by the board. No interrupt: every wait
  polls a status flag a bounded number of times, so SysTick is not needed.
  I2cInit configures the pins as open-drain alternate function without
  internal pull-up: the board has external pull-ups on SCL and SDA.

\section i2c_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 18/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef I2C_H
#define I2C_H

#include <stdint.h>

/// An I2C controller and its two pins.
typedef struct {
  uint32_t base;           ///< I2C base address (I2Cx_BASE).
  volatile uint32_t *enr;  ///< RCC enable register of the I2C (&RCC_APB1ENR).
  uint32_t enr_bit;        ///< Enable bit in that register.
  volatile uint32_t *rstr; ///< RCC reset register of the I2C (&RCC_APB1RSTR).
  uint32_t rst_bit;        ///< Reset bit in that register.
  uint32_t sel_mask;       ///< Kernel clock field in RCC_DCKCFGR2.
  uint32_t sel_value;      ///< Kernel clock value written in that field.
  uint32_t kernel_hsi;     ///< Nonzero: the kernel clock is HSI, started by I2cInit.
  uint32_t timingr;        ///< TIMINGR value for that kernel clock and bus speed.
  uint32_t scl_port;       ///< SCL pin port base address.
  uint32_t scl_pin;        ///< SCL pin number.
  uint32_t sda_port;       ///< SDA pin port base address.
  uint32_t sda_pin;        ///< SDA pin number.
  uint32_t af;             ///< Alternate function of both pins.
} I2c;

/*!
\brief  Reset and enable the I2C, then configure its clock, timing and pins.
\details When kernel_hsi is nonzero, HSI is switched on and HSIRDY is waited
         for: HSI is on at reset, but an application may have stopped it.
\param  i2c  I2C to configure.
\return SUCCESS, or TIMEOUT if HSI does not become ready in time.
*/
int I2cInit(const I2c *i2c);

/*!
\brief  Read registers of a device: write the register address, then read
        len bytes after a repeated start, with a STOP at the end.
\param  i2c    I2C configured by I2cInit().
\param  addr7  7-bit device address.
\param  reg    First register to read; the device advances it after each byte.
\param  data   Output buffer of len bytes; valid on SUCCESS only.
\param  len    Number of bytes, 1 to 255.
\return SUCCESS; TIMEOUT if the device answers with a NACK or a wait passes its
        limit; FAILURE on a bus error or a lost arbitration, or if len is 0 or
        above 255.
*/
int I2cReadReg(const I2c *i2c, uint8_t addr7, uint8_t reg, uint8_t *data, uint32_t len);

#endif
