// SPDX-License-Identifier: MIT
/*!
****************************
\file       11-text-console/main.c
\brief      Text console, probe version: UART reception and framebuffer copy from QSPI.

\author     Z. BEN-AKKA
\version    1.0
\date       24/11/2026

\details
  Probe of phase I (work/doc_zak/phaseI_text.md, decision A); no text is
  drawn yet.
  1) Stops USART1, left enabled by the bootloader, before any clock change:
     USART_BRR is written only with UE = 0 (RM0385 Rev 9, p. 1062).
  2) Draws 17 bars of 16 px, then scrolls them twice by one bar, once with
     16-bit and once with 32-bit accesses, and prints both durations.
  3) Receives on USART1 by interrupt. One second after the last event it
     prints the bytes read, the time from the first event to the last, the
     error counters and the sum of the bytes.
  Built as 11-text-console-app, run in place from QSPI behind the 08 bootloader.

\section text_console_main_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 24/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "defines.h"
#include "delay/delay.h"
#include "fb/fb.h"
#include "ltdc/ltdc.h"
#include "rcc/rcc.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

#define BAR_H        16U                  ///< Height of a bar: one text line.
#define BAR_COUNT    (LCD_HEIGHT / BAR_H) ///< 17 bars fill the screen.
#define COLOUR_COUNT 8U                   ///< Colours of the bars, repeated.
#define BLACK        0x0000U              ///< Colour of the line freed by a scroll.

#define SCROLL_PIXELS (LCD_WIDTH * (LCD_HEIGHT - BAR_H)) ///< Pixels moved by a scroll.
#define SCREEN_PIXELS (LCD_WIDTH * LCD_HEIGHT)           ///< Pixels of the screen.

#define CYCLES_PER_US (SYSCLK_HZ / 1000000UL) ///< Core cycles per microsecond.
#define RX_IDLE_MS    1000U                   ///< Silence before a reception report.

/// RGB565 colours of the bars, from the top.
static const uint16_t palette[COLOUR_COUNT] = {
    0xFFFFU, // white
    0xF800U, // red
    0x07E0U, // green
    0x001FU, // blue
    0xFFE0U, // yellow
    0x07FFU, // cyan
    0xF81FU, // magenta
    0xFD20U, // orange
};

/// RGB565 framebuffer in SRAM (linker section .framebuffer): too large for the 64 KB DTCM.
static volatile uint16_t fb_pixels[SCREEN_PIXELS]
    __attribute__((section(".framebuffer"), aligned(8)));

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {fb_pixels, LCD_WIDTH, LCD_HEIGHT};

static const Uart *const console = &BOARD_UART_VCP; ///< Console input and output.

/// Reception since the last report.
typedef struct {
  uint32_t active;   ///< An event was read since the last report.
  uint32_t first_ms; ///< Time of the first event.
  uint32_t last_ms;  ///< Time of the last event.
  uint32_t bytes;    ///< Bytes read from the queue.
  uint32_t sum;      ///< Sum of these bytes.
} RxBurst;

/*!
\brief  Print a message and stop.
*/
static void __attribute__((noreturn)) halt(const char *msg)
{
  UartPuts(console, msg);
  while (1) {}
}

/*!
\brief  Print a name followed by a decimal value.
*/
static void put_field(const char *name, uint32_t value)
{
  UartPuts(console, name);
  UartPutDec(console, value);
}

/*!
\brief  Start the DWT cycle counter.
*/
static void cycle_counter_init(void)
{
  DEMCR |= DEMCR_TRCENA;
  DWT_LAR = DWT_LAR_UNLOCK;
  DWT_CYCCNT = 0U;
  DWT_CTRL |= DWT_CTRL_CYCCNTENA;
}

/*!
\brief  Draw the bars over the whole screen.
*/
static void draw_bars(void)
{
  for (uint32_t i = 0; i < BAR_COUNT; i++) {
    FbRect(&screen, 0, i * BAR_H, LCD_WIDTH, BAR_H, palette[i % COLOUR_COUNT]);
  }
}

/*!
\brief  Scroll the screen by one bar with 16-bit accesses; the last bar becomes black.
*/
static void scroll16(void)
{
  const uint32_t shift = LCD_WIDTH * BAR_H;

  for (uint32_t i = 0; i < SCROLL_PIXELS; i++) {
    fb_pixels[i] = fb_pixels[i + shift];
  }
  for (uint32_t i = SCROLL_PIXELS; i < SCREEN_PIXELS; i++) {
    fb_pixels[i] = BLACK;
  }
}

/*!
\brief  Scroll the screen by one bar with 32-bit accesses; the last bar becomes black.
*/
static void scroll32(void)
{
  // Two pixels per word: the framebuffer is aligned on 8 bytes and its counts are even
  volatile uint32_t *words = (volatile uint32_t *)(uint32_t)fb_pixels;
  const uint32_t shift = LCD_WIDTH * BAR_H / 2U;

  for (uint32_t i = 0; i < SCROLL_PIXELS / 2U; i++) {
    words[i] = words[i + shift];
  }
  for (uint32_t i = SCROLL_PIXELS / 2U; i < SCREEN_PIXELS / 2U; i++) {
    words[i] = BLACK;
  }
}

/*!
\brief  Run a scroll and print its duration.
*/
static void measure(const char *name, void (*scroll)(void))
{
  const uint32_t start = DWT_CYCCNT;

  scroll();

  const uint32_t cycles = DWT_CYCCNT - start;

  UartPuts(console, name);
  put_field(": cycles=", cycles);
  put_field(" us=", cycles / CYCLES_PER_US);
  UartPuts(console, "\n");
}

/*!
\brief  Print a reception and the errors counted since the previous report.
*/
static void report(const RxBurst *burst, const UartRxStats *before, const UartRxStats *now)
{
  put_field("rx: bytes=", burst->bytes);
  put_field(" ms=", burst->last_ms - burst->first_ms);
  put_field(" fe=", now->framing_errors - before->framing_errors);
  put_field(" ne=", now->noise_errors - before->noise_errors);
  put_field(" ore=", now->overrun_errors - before->overrun_errors);
  put_field(" ovf=", now->buffer_overflows - before->buffer_overflows);
  UartPuts(console, " sum=");
  UartPutHex32(console, burst->sum);
  UartPuts(console, "\n");
}

/*!
\brief  Account for one event read from the reception queue.
*/
static void count_event(RxBurst *burst, UartRxEvent event)
{
  const uint32_t now = SysTickMs();

  if (!burst->active) {
    burst->active = 1U;
    burst->first_ms = now;
    burst->bytes = 0U;
    burst->sum = 0U;
  }
  burst->last_ms = now;
  if (event <= UART_RX_EVENT_BYTE_MAX) {
    burst->bytes++;
    burst->sum += event;
  }
}

/*!
\brief  Application entry point: probe the reception and the scroll.
\return Never returns.
*/
int main(void)
{
  RxBurst burst = {0U, 0U, 0U, 0U, 0U};
  UartRxStats before = {0U, 0U, 0U, 0U, 0U};

  // The bootloader leaves USART1 enabled: stopped before its clock changes and BRR is written
  USART_CR1(console->base) = 0U;

  if (RccInit216MHz(HSE_HZ) != SUCCESS) {
    RCC_CFGR = 0U; // Back on HSI with /1 prescalers, so the message can be read
    UartInit(console, HSI_HZ, BAUDRATE);
    halt("\ntext console: clock error\n");
  }
  SysTickInit(SYSCLK_HZ);
  cycle_counter_init();
  UartInit(console, APB2_HZ, BAUDRATE);
  UartPuts(console, "\ntext console: RX probe\n");

  if (RccInitPixelClock9MHz() != SUCCESS) {
    halt("text console: pixel clock error\n");
  }
  BoardLcdPinsInit();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // Black background until layer 1 is on

  // The whole screen is drawn before layer 1 shows it: the first image is complete
  draw_bars();
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, (uint32_t)fb_pixels);
  BoardLcdPowerOn();

  // Measured with the LTDC reading the framebuffer, as in the console
  (void)LtdcFifoUnderrun(); // Clear the flag
  measure("copy16", scroll16);
  measure("copy32", scroll32);
  put_field("underrun=", LtdcFifoUnderrun() ? 1U : 0U);
  UartPuts(console, "\n");

  UartRxStart(console);

  while (1) {
    UartRxEvent event;

    if (UartRxGet(console, &event)) {
      count_event(&burst, event);
    } else if (burst.active && SysTickMs() - burst.last_ms >= RX_IDLE_MS) {
      UartRxStats now;

      UartRxGetStats(console, &now);
      report(&burst, &before, &now);
      before = now;
      burst.active = 0U;
    }
  }
}
