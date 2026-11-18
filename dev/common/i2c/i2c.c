// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/i2c/i2c.c
\brief      Polled I2C master, 7-bit addresses.

\author     Z. BEN-AKKA
\version    1.0
\date       18/11/2026

\details
  API documented in i2c.h.

\section i2c_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 18/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "i2c/i2c.h"

#include <stdint.h>

#include "defines.h"
#include "mcu.h"
#include "gpio/gpio.h"

/// Polls of a status flag before giving up: several ms at 216 MHz, one byte
/// takes 90 us at 100 kHz.
#define I2C_POLL_TIMEOUT 1000000U

/// Every flag cleared after a failed transfer.
#define I2C_ICR_ALL (I2C_ICR_NACKCF | I2C_ICR_STOPCF | I2C_ICR_BERRCF | I2C_ICR_ARLOCF)

/*!
\brief  Wait for an I2C_ISR flag, stopping early on an error.
\param  base  I2C base address.
\param  mask  Flag to wait for, such as I2C_ISR_TXIS.
\return SUCCESS; TIMEOUT on a NACK or past the limit; FAILURE on a bus error
        or a lost arbitration.
*/
static int i2c_wait_flag(uint32_t base, uint32_t mask)
{
  for (uint32_t n = 0;; n++) {
    uint32_t isr = I2C_ISR(base);

    if (isr & (I2C_ISR_BERR | I2C_ISR_ARLO)) {
      return FAILURE;
    }
    if (isr & I2C_ISR_NACKF) {
      return TIMEOUT; // the device did not answer
    }
    if (isr & mask) {
      return SUCCESS;
    }
    if (n > I2C_POLL_TIMEOUT) {
      return TIMEOUT;
    }
  }
}

/*!
\brief  Bring the I2C back to idle after a failed transfer.
\details After a NACK the controller sends the STOP itself (RM0385 30.4.9):
         wait for it, with a limit, since a bus error or a lost arbitration
         sends none. Then clear the flags and reset the controller: PE low for
         at least three APB cycles (RM0385 30.4.6); each read below takes one.
\param  base  I2C base address.
*/
static void i2c_recover(uint32_t base)
{
  for (uint32_t n = 0; !(I2C_ISR(base) & I2C_ISR_STOPF) && n <= I2C_POLL_TIMEOUT; n++) {}
  I2C_ICR(base) = I2C_ICR_ALL;
  I2C_CR1(base) &= ~I2C_CR1_PE;
  (void)I2C_CR1(base);
  (void)I2C_CR1(base);
  (void)I2C_CR1(base);
  I2C_CR1(base) |= I2C_CR1_PE;
}

/*!
\brief  Configure one I2C pin: open-drain alternate function, no pull.
\details Open-drain is set before the alternate function, so the line is
         never driven high. The board has external pull-ups.
\param  port  Port base address.
\param  pin   Pin number.
\param  af    Alternate function.
*/
static void i2c_pin(uint32_t port, uint32_t pin, uint32_t af)
{
  GpioEnableClock(port);
  GPIO_OTYPER(port) |= 1U << pin;
  GPIO_PUPDR(port) &= ~(3U << (pin * 2));
  GpioSetAf(port, pin, af);
}

int I2cInit(const I2c *i2c)
{
  uint32_t base = i2c->base;

  *i2c->rstr |= i2c->rst_bit;
  *i2c->rstr &= ~i2c->rst_bit;
  *i2c->enr |= i2c->enr_bit;
  (void)*i2c->enr; // read back: the clock reaches the I2C

  if (i2c->kernel_hsi) {
    RCC_CR |= RCC_CR_HSION;
    for (uint32_t n = 0; !(RCC_CR & RCC_CR_HSIRDY); n++) {
      if (n > I2C_POLL_TIMEOUT) {
        return TIMEOUT;
      }
    }
  }
  RCC_DCKCFGR2 = (RCC_DCKCFGR2 & ~i2c->sel_mask) | i2c->sel_value;

  i2c_pin(i2c->scl_port, i2c->scl_pin, i2c->af);
  i2c_pin(i2c->sda_port, i2c->sda_pin, i2c->af);

  // TIMINGR is written while PE is 0; analog filter on, digital filter off
  I2C_CR1(base) = 0;
  I2C_TIMINGR(base) = i2c->timingr;
  I2C_CR1(base) = I2C_CR1_PE;
  return SUCCESS;
}

int I2cReadReg(const I2c *i2c, uint8_t addr7, uint8_t reg, uint8_t *data, uint32_t len)
{
  uint32_t base = i2c->base;
  int rc = SUCCESS;

  if (len == 0 || len > 255U) {
    return FAILURE; // NBYTES holds 8 bits; RELOAD is not used
  }
  for (uint32_t n = 0; I2C_ISR(base) & I2C_ISR_BUSY; n++) {
    if (n > I2C_POLL_TIMEOUT) {
      i2c_recover(base);
      return TIMEOUT;
    }
  }

  // Write the register address; AUTOEND = 0, so TC is set and a RESTART follows
  I2C_CR2(base) = I2C_CR2_SADD7(addr7) | I2C_CR2_NBYTES(1) | I2C_CR2_START;
  rc = i2c_wait_flag(base, I2C_ISR_TXIS);
  if (rc == SUCCESS) {
    I2C_TXDR(base) = reg;
    rc = i2c_wait_flag(base, I2C_ISR_TC);
  }

  // RESTART in read; AUTOEND = 1: NACK and STOP after the last byte
  if (rc == SUCCESS) {
    I2C_CR2(base) = I2C_CR2_SADD7(addr7) | I2C_CR2_RD_WRN | I2C_CR2_NBYTES(len) | I2C_CR2_AUTOEND |
                    I2C_CR2_START;
    for (uint32_t i = 0; i < len && rc == SUCCESS; i++) {
      rc = i2c_wait_flag(base, I2C_ISR_RXNE);
      if (rc == SUCCESS) {
        data[i] = (uint8_t)I2C_RXDR(base);
      }
    }
  }
  if (rc == SUCCESS) {
    rc = i2c_wait_flag(base, I2C_ISR_STOPF);
  }

  if (rc != SUCCESS) {
    i2c_recover(base);
    return rc;
  }
  I2C_ICR(base) = I2C_ICR_STOPCF;
  return SUCCESS;
}
