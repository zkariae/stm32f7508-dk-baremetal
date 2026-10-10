// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/board/board.c
\brief      STM32F7508-DK: on-board LED, console, LCD panel and QSPI flash.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  API documented in board.h.

\section board_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "board/board.h"

#include <stdint.h>

#include "defines.h"
#include "delay/delay.h"
#include "gpio/gpio.h"

const Led BOARD_LED_LD1 = {
    .port = GPIOI_BASE,
    .pin = LED_PIN,
    .active_high = 1,
};

const Uart BOARD_UART_VCP = {
    .base = USART1_BASE,
    .enr = &RCC_APB2ENR,
    .enr_bit = RCC_APB2ENR_USART1EN,
    .tx_port = GPIOA_BASE,
    .tx_pin = VCP_TX_PIN,
    .tx_af = 7, // AF7 = USART1_TX
};

const LtdcTiming BOARD_LCD_TIMING = {
    .width = LCD_WIDTH,
    .height = LCD_HEIGHT,
    .hsw = LCD_HSW,
    .hbp = LCD_HBP,
    .hfp = LCD_HFP,
    .vsw = LCD_VSW,
    .vbp = LCD_VBP,
    .vfp = LCD_VFP,
};

/// LTDC signals on the STM32F7508-DK (MB1191 schematic), all on AF14.
static const struct {
  uint8_t port, pin;
} lcd_pins[] = {
    // Red
    {PORT_I, 15},
    {PORT_J, 0},
    {PORT_J, 1},
    {PORT_J, 2},
    {PORT_J, 3},
    {PORT_J, 4},
    {PORT_J, 5},
    {PORT_J, 6},
    // Green
    {PORT_J, 7},
    {PORT_J, 8},
    {PORT_J, 9},
    {PORT_J, 10},
    {PORT_J, 11},
    {PORT_K, 0},
    {PORT_K, 1},
    {PORT_K, 2},
    // Blue
    {PORT_E, 4},
    {PORT_J, 13},
    {PORT_J, 14},
    {PORT_J, 15},
    {PORT_G, 12},
    {PORT_K, 4},
    {PORT_K, 5},
    {PORT_K, 6},
    // Control
    {PORT_I, 10}, // HSYNC
    {PORT_I, 9},  // VSYNC
    {PORT_I, 14}, // CLK
    {PORT_K, 7},  // DE
};

#define LCD_PIN_COUNT (sizeof(lcd_pins) / sizeof(lcd_pins[0]))

void BoardLcdPinsInit(void)
{
  for (uint32_t i = 0; i < LCD_PIN_COUNT; i++) {
    GpioEnableClock(GPIO_PORT(lcd_pins[i].port));
    GpioSetAf(GPIO_PORT(lcd_pins[i].port), lcd_pins[i].pin, 14U);
  }
}

void BoardLcdPowerOn(void)
{
  GpioEnableClock(GPIOI_BASE);
  GpioEnableClock(GPIOK_BASE);

  GpioSetOutput(GPIOI_BASE, LCD_DISP_PIN);
  GpioSetOutput(GPIOK_BASE, LCD_BL_PIN);

  // Panel before backlight, to avoid a flash of noise at power-up
  GpioSet(GPIOI_BASE, LCD_DISP_PIN);
  DelayMs(20);
  GpioSet(GPIOK_BASE, LCD_BL_PIN);
}

void BoardLcdBacklightOn(void)
{
  GpioSet(GPIOK_BASE, LCD_BL_PIN);
}

void BoardLcdBacklightOff(void)
{
  GpioClear(GPIOK_BASE, LCD_BL_PIN);
}

void BoardQspiPinsInit(void)
{
  GpioEnableClock(GPIOB_BASE);
  GpioEnableClock(GPIOD_BASE);
  GpioEnableClock(GPIOE_BASE);

  GpioSetAf(GPIOB_BASE, 2, 9);  // CLK
  GpioSetAf(GPIOB_BASE, 6, 10); // NCS (AF10)
  GpioSetAf(GPIOD_BASE, 11, 9); // IO0
  GpioSetAf(GPIOD_BASE, 12, 9); // IO1
  GpioSetAf(GPIOE_BASE, 2, 9);  // IO2
  GpioSetAf(GPIOD_BASE, 13, 9); // IO3
}
