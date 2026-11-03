// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/lcd_commands.c
\brief      GPIO_CONFIG and LCD commands of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.0
\date       29/10/2026

\details
  Implements protocol.md sections 6.11 to 6.19.
  - GPIO_CONFIG reads MODER, AFR and IDR of one pin, after enabling the
    clock of its port; it works without LCD_INIT.
  - LCD_INIT runs the steps of section 6.13 in order. Until it succeeds the
    other LCD commands return BUSY and change nothing (section 6.12).
  - LCD_CLOCK, LCD_TIMING and LCD_LAYER decode the RCC and LTDC registers.
  - LCD_SCAN polls LTDC_CPSR for the whole window, measured with SysTickMs().
  - LCD_FILL and LCD_PIXEL write and read the framebuffer. The data cache is
    off (section 6.12), so the LTDC and the CPU see the same pixels.
  The framebuffer is the only object of the .framebuffer section, so it
  starts at 0x20010000, the first SRAM address (section 6.12).

\section lcd_commands_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 29/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "lcd_commands.h"

#include <stddef.h>

#include "board.h" // BOARD_LCD_TIMING, LCD_WIDTH, LCD_HEIGHT
#include "defines.h"
#include "delay/delay.h"
#include "fb/fb.h"
#include "gpio/gpio.h"
#include "hil_protocol.h"
#include "ltdc/ltdc.h"
#include "rcc/rcc.h"

#define CFGR_SWS_PLL       (2U << 2)     ///< RCC_CFGR SWS: SYSCLK from the main PLL.
#define PLLCFGR_SRC_HSE    (1U << 22)    ///< RCC_PLLCFGR PLLSRC: HSE input.
#define PLLCFGR_M_MASK     0x3FU         ///< RCC_PLLCFGR PLLM, bits 5:0.
#define PLLSAICFGR_N_SHIFT 6U            ///< RCC_PLLSAICFGR PLLSAIN, bits 14:6.
#define PLLSAICFGR_N_MASK  0x1FFU
#define PLLSAICFGR_R_SHIFT 28U           ///< RCC_PLLSAICFGR PLLSAIR, bits 30:28.
#define PLLSAICFGR_R_MASK  7U
#define DCKCFGR1_DIVR_SHIFT 16U          ///< RCC_DCKCFGR1 PLLSAIDIVR, bits 17:16: /2 << code.
#define DCKCFGR1_DIVR_MASK  3U

#define LTDC_HIGH(reg) (((reg) >> 16) & 0xFFFU) ///< Horizontal field of an LTDC timing register.
#define LTDC_LOW(reg)  ((reg) & 0xFFFU)         ///< Vertical field of an LTDC timing register.
#define LTDC_PF_MASK   7U                       ///< LTDC_L1PFCR PF, bits 2:0.

#define COLOR_TEXT_MAX 6u ///< "0x" and at most 4 digits (section 6.12).

/// RGB565 framebuffer in SRAM (linker section .framebuffer): too large for the 64 KB DTCM.
static volatile uint16_t fb_pixels[LCD_WIDTH * LCD_HEIGHT]
    __attribute__((section(".framebuffer"), aligned(8)));

/// The framebuffer shown by LTDC layer 1.
static const Framebuffer screen = {fb_pixels, LCD_WIDTH, LCD_HEIGHT};

static uint8_t lcd_ready; ///< LCD_INIT has succeeded in this session.

/// GPIO_CONFIG mode names, indexed by the 2 MODER bits of the pin.
static const char *const gpio_modes[] = {
    HIL_GPIO_MODE_INPUT,
    HIL_GPIO_MODE_OUTPUT,
    HIL_GPIO_MODE_AF,
    HIL_GPIO_MODE_ANALOG,
};

/// LCD_LAYER format names, indexed by LTDC_L1PFCR PF.
static const char *const pixel_formats[] = {
    "argb8888", "rgb888", "rgb565", "argb1555", "argb4444", "l8", "al44", "al88",
};

/*!
\brief  Append a colour field: 0x and four uppercase hexadecimal digits (section 6.12).
*/
static void AddColor(Record *result, uint16_t color)
{
  static const char digits[] = "0123456789ABCDEF";
  char text[COLOR_TEXT_MAX + 1u] = {'0', 'x'};

  for (uint32_t i = 0u; i < 4u; ++i) {
    text[2u + i] = digits[(color >> (12u - 4u * i)) & 0xFu];
  }
  text[COLOR_TEXT_MAX] = '\0';
  RecordAdd(result, HIL_KEY_COLOR, text);
}

/*!
\brief  1 if SYSCLK comes from the main PLL fed by the HSE (section 6.12).
*/
static uint32_t RunsFromHse(void)
{
  return (RCC_CFGR & RCC_CFGR_SWS_MASK) == CFGR_SWS_PLL && (RCC_PLLCFGR & PLLCFGR_SRC_HSE) != 0u;
}

const char *GpioConfigCmd(const CommandArg *args, uint32_t count, Record *result)
{
  const char *port_text = CommandFindArg(args, count, HIL_KEY_PORT);
  const char *pin_text = CommandFindArg(args, count, HIL_KEY_PIN);
  uint32_t pin;

  if (count != 2u || port_text == NULL || pin_text == NULL || port_text[0] < HIL_GPIO_PORT_FIRST ||
      port_text[0] > HIL_GPIO_PORT_LAST || port_text[1] != '\0' ||
      !RecordParseDec(pin_text, HIL_GPIO_PIN_MAX, &pin)) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  const uint32_t port = GPIO_PORT((uint32_t)(port_text[0] - HIL_GPIO_PORT_FIRST));

  GpioEnableClock(port); // A port with its clock off reads as zeros
  RecordAdd(result, HIL_KEY_MODE, gpio_modes[(GPIO_MODER(port) >> (2u * pin)) & 3u]);
  RecordAddDec(result, HIL_KEY_AF, (GPIO_AFR(port, pin) >> (4u * (pin % 8u))) & 0xFu);
  RecordAddDec(result, HIL_KEY_LEVEL, (GPIO_IDR(port) >> pin) & 1u);
  return NULL;
}

const char *LcdInitCmd(const CommandArg *args, uint32_t count, Record *result)
{
  (void)args;
  (void)result;
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  if (!RunsFromHse()) {
    return HIL_ERR_DEVICE_ERROR; // The 9 MHz pixel clock needs the 1 MHz PLL input from the HSE
  }
  if (RccInitPixelClock9MHz() != SUCCESS) {
    return HIL_ERR_DEVICE_TIMEOUT;
  }
  BoardLcdPinsInit();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // Black background until layer 1 is on

  // The whole frame is cleared before layer 1 shows it: SRAM is random at reset
  FbClear(&screen, 0x0000u);
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, (uint32_t)fb_pixels);

  // Panel and backlight last: the undriven panel is white, it must get the frame at once
  BoardLcdPowerOn();
  lcd_ready = 1u;
  return NULL;
}

const char *LcdClockCmd(const CommandArg *args, uint32_t count, Record *result)
{
  (void)args;
  if (!lcd_ready) {
    return HIL_ERR_BUSY;
  }
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  const uint32_t source = (RCC_PLLCFGR & PLLCFGR_SRC_HSE) ? HSE_HZ : HSI_HZ;
  const uint32_t m = RCC_PLLCFGR & PLLCFGR_M_MASK;
  const uint32_t n = (RCC_PLLSAICFGR >> PLLSAICFGR_N_SHIFT) & PLLSAICFGR_N_MASK;
  const uint32_t r = (RCC_PLLSAICFGR >> PLLSAICFGR_R_SHIFT) & PLLSAICFGR_R_MASK;
  const uint32_t divr = 2u << ((RCC_DCKCFGR1 >> DCKCFGR1_DIVR_SHIFT) & DCKCFGR1_DIVR_MASK);

  // 32-bit steps: input / M is at most 2 MHz and the VCO at most 432 MHz in a valid setting
  RecordAdd(result, HIL_KEY_PLLSAI, (RCC_CR & RCC_CR_PLLSAIRDY) ? HIL_PLLSAI_LOCKED : HIL_PLLSAI_OFF);
  RecordAddDec(result, HIL_KEY_PIXEL_HZ, source / m * n / r / divr);
  return NULL;
}

const char *LcdTimingCmd(const CommandArg *args, uint32_t count, Record *result)
{
  (void)args;
  if (!lcd_ready) {
    return HIL_ERR_BUSY;
  }
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  const uint32_t sscr = LTDC_SSCR;
  const uint32_t bpcr = LTDC_BPCR;
  const uint32_t awcr = LTDC_AWCR;
  const uint32_t twcr = LTDC_TWCR;

  // Each register holds an accumulated total minus one
  RecordAddDec(result, HIL_KEY_HSW, LTDC_HIGH(sscr) + 1u);
  RecordAddDec(result, HIL_KEY_HBP, LTDC_HIGH(bpcr) - LTDC_HIGH(sscr));
  RecordAddDec(result, HIL_KEY_WIDTH, LTDC_HIGH(awcr) - LTDC_HIGH(bpcr));
  RecordAddDec(result, HIL_KEY_HFP, LTDC_HIGH(twcr) - LTDC_HIGH(awcr));
  RecordAddDec(result, HIL_KEY_VSW, LTDC_LOW(sscr) + 1u);
  RecordAddDec(result, HIL_KEY_VBP, LTDC_LOW(bpcr) - LTDC_LOW(sscr));
  RecordAddDec(result, HIL_KEY_HEIGHT, LTDC_LOW(awcr) - LTDC_LOW(bpcr));
  RecordAddDec(result, HIL_KEY_VFP, LTDC_LOW(twcr) - LTDC_LOW(awcr));
  return NULL;
}

const char *LcdLayerCmd(const CommandArg *args, uint32_t count, Record *result)
{
  (void)args;
  if (!lcd_ready) {
    return HIL_ERR_BUSY;
  }
  if (count != 0u) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  const uint32_t bpcr = LTDC_BPCR;
  const uint32_t whpcr = LTDC_L1WHPCR;
  const uint32_t wvpcr = LTDC_L1WVPCR;

  // Window registers: start in bits 11:0, stop in bits 27:16
  RecordAddDec(result, HIL_KEY_ENABLED, (LTDC_L1CR & LTDC_L1CR_LEN) ? 1u : 0u);
  RecordAdd(result, HIL_KEY_FORMAT, pixel_formats[LTDC_L1PFCR & LTDC_PF_MASK]);
  RecordAddHex32(result, HIL_KEY_FB_ADDR, LTDC_L1CFBAR);
  RecordAddDec(result, HIL_KEY_X, LTDC_LOW(whpcr) - LTDC_HIGH(bpcr) - 1u);
  RecordAddDec(result, HIL_KEY_Y, LTDC_LOW(wvpcr) - LTDC_LOW(bpcr) - 1u);
  RecordAddDec(result, HIL_KEY_WIDTH, LTDC_HIGH(whpcr) - LTDC_LOW(whpcr) + 1u);
  RecordAddDec(result, HIL_KEY_HEIGHT, LTDC_HIGH(wvpcr) - LTDC_LOW(wvpcr) + 1u);
  return NULL;
}

const char *LcdScanCmd(const CommandArg *args, uint32_t count, Record *result)
{
  uint32_t ms;
  uint32_t frames = 0u;

  if (!lcd_ready) {
    return HIL_ERR_BUSY;
  }
  if (count != 1u || !RecordStrEq(args[0].key, HIL_KEY_MS) ||
      !RecordParseDec(args[0].value, HIL_LCD_SCAN_MS_MAX, &ms) || ms < HIL_LCD_SCAN_MS_MIN) {
    return HIL_ERR_INVALID_ARGUMENT;
  }

  // Start on a tick edge, so the window lasts ms milliseconds, not up to one less
  uint32_t start = SysTickMs();
  while (SysTickMs() == start) {
  }
  start = SysTickMs();
  (void)LtdcFifoUnderrun(); // Clear FUIF at the start of the window

  // One CPSR read per loop, far more often than once per millisecond
  uint32_t previous = LTDC_CPSR & LTDC_CPSR_CYPOS_MASK;
  while (SysTickMs() - start < ms) {
    const uint32_t line = LTDC_CPSR & LTDC_CPSR_CYPOS_MASK;

    if (line < previous) {
      ++frames; // The line position went back: a new frame started
    }
    previous = line;
  }
  RecordAddDec(result, HIL_KEY_FRAMES, frames);
  RecordAddDec(result, HIL_KEY_UNDERRUN, LtdcFifoUnderrun() ? 1u : 0u);
  return NULL;
}

const char *LcdFillCmd(const CommandArg *args, uint32_t count, Record *result)
{
  uint32_t color;

  (void)result;
  if (!lcd_ready) {
    return HIL_ERR_BUSY;
  }
  if (count != 1u || !RecordStrEq(args[0].key, HIL_KEY_COLOR) ||
      RecordStrLen(args[0].value) > COLOR_TEXT_MAX || !RecordParseHex32(args[0].value, &color)) {
    return HIL_ERR_INVALID_ARGUMENT; // At most 4 digits, so color is at most HIL_LCD_COLOR_MAX
  }
  FbClear(&screen, (uint16_t)color);
  return NULL;
}

const char *LcdPixelCmd(const CommandArg *args, uint32_t count, Record *result)
{
  const char *x_text = CommandFindArg(args, count, HIL_KEY_X);
  const char *y_text = CommandFindArg(args, count, HIL_KEY_Y);
  uint32_t x;
  uint32_t y;

  if (!lcd_ready) {
    return HIL_ERR_BUSY;
  }
  if (count != 2u || x_text == NULL || y_text == NULL ||
      !RecordParseDec(x_text, LCD_WIDTH - 1u, &x) || !RecordParseDec(y_text, LCD_HEIGHT - 1u, &y)) {
    return HIL_ERR_INVALID_ARGUMENT;
  }
  AddColor(result, fb_pixels[y * LCD_WIDTH + x]);
  return NULL;
}
