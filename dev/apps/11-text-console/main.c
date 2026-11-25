// SPDX-License-Identifier: MIT
/*!
****************************
\file       11-text-console/main.c
\brief      Text console, measuring version: character sheet and drawing durations.

\author     Z. BEN-AKKA
\version    1.1
\date       25/11/2026

\details
  Measuring version of phase I (work/doc_zak/phaseI_text.md, decision C);
  nothing is received yet.
  1) Stops USART1, left enabled by the bootloader, before any clock change:
     USART_BRR is written only with UE = 0 (RM0385 Rev 9, p. 1062).
  2) Measures, with the LTDC reading the framebuffer: a palette, 1020 cells in
     both formats with the glyphs in QSPI and in DTCM, one line, the comparison
     of the terminal with the screen, a line feed, a form feed, and the copy
     of a scroll by 32-bit words. One line on the UART per measure.
  3) Draws a character sheet in both formats, which stays on the screen.
  Built as 11-text-console-app, run in place from QSPI behind the 08 bootloader.

\section text_console_main_c_version_history Version history
| Version | Date       | Author      | Description                                                    |
|:-------:|:----------:|:------------|:---------------------------------------------------------------|
| 1.0     | 24/11/2026 | Z. BEN-AKKA | Initial version.                                               |
| 1.1     | 25/11/2026 | Z. BEN-AKKA | Character sheet in both formats; rendering, terminal measured. |
****************************
*/

#include <stdint.h>

#include "board.h"
#include "defines.h"
#include "delay/delay.h"
#include "fb/fb.h"
#include "font/font.h"
#include "ltdc/ltdc.h"
#include "rcc/rcc.h"
#include "terminal/terminal.h"
#include "text/text.h"
#include "uart/uart.h"

#define BAUDRATE 115200UL

#define CELL_W     8U                    ///< Width of a character cell.
#define CELL_H     16U                   ///< Height of a character cell.
#define COLUMNS    (LCD_WIDTH / CELL_W)  ///< 60 cells per line.
#define ROWS       (LCD_HEIGHT / CELL_H) ///< 17 lines.
#define CELLS      (COLUMNS * ROWS)      ///< 1020 cells on the screen.
#define CODE_FIRST 0x20U                 ///< First character of the fonts.
#define CODE_COUNT 95U                   ///< Characters of the fonts.
#define GLYPHS_MAX (CODE_COUNT * 64U)    ///< Bytes of the largest font (4 bits).
#define CURSOR_H   2U                    ///< Height of the cursor line.

#define SCROLL_PIXELS (LCD_WIDTH * (LCD_HEIGHT - CELL_H)) ///< Pixels moved by a scroll.
#define SCREEN_PIXELS (LCD_WIDTH * LCD_HEIGHT)            ///< Pixels of the screen.

#define CYCLES_PER_US (SYSCLK_HZ / 1000000UL) ///< Core cycles per microsecond.

#define BLACK  0x0000U
#define WHITE  0xFFFFU
#define RED    0xF800U
#define GREEN  0x07E0U
#define YELLOW 0xFFE0U
#define CYAN   0x07FFU

/// RGB565 framebuffer in SRAM (linker section .framebuffer): too large for the 64 KB DTCM.
static volatile uint16_t fb_pixels[SCREEN_PIXELS]
    __attribute__((section(".framebuffer"), aligned(8)));

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {fb_pixels, LCD_WIDTH, LCD_HEIGHT};

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.

static const Font *const font1 = &FONT_MONO_8X16_1BPP; ///< 1 bit per pixel, in QSPI.
static const Font *const font4 = &FONT_MONO_8X16_4BPP; ///< 4 bits per pixel, in QSPI.

static TextPalette normal;        ///< White on black.
static const Font *measured_font; ///< Font of the measure in progress.

static uint8_t dtcm_glyphs[GLYPHS_MAX]; ///< Glyphs copied from QSPI (.bss: DTCM).
static TerminalCell grid[CELLS];        ///< Grid of the terminal.
static TerminalCell shown[CELLS];       ///< What the screen shows.
static Terminal terminal;               ///< Terminal that is measured.
static volatile uint32_t changed;       ///< Cells found different, kept by the compiler.

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
\brief  Run a function and print its duration.
*/
static void measure(const char *name, void (*run)(void))
{
  const uint32_t start = DWT_CYCCNT;

  run();

  const uint32_t cycles = DWT_CYCCNT - start;

  UartPuts(console, name);
  put_field(": cycles=", cycles);
  put_field(" us=", cycles / CYCLES_PER_US);
  UartPuts(console, "\n");
}

/*!
\brief  Measured: compute a palette.
*/
static void run_palette(void)
{
  TextPaletteInit(&normal, WHITE, BLACK);
}

/*!
\brief  Draw count cells from the top left, the characters in turn.
*/
static void draw_cells(uint32_t count)
{
  for (uint32_t i = 0; i < count; i++) {
    TextChar(&screen, i % COLUMNS * CELL_W, i / COLUMNS * CELL_H, measured_font, &normal,
             (uint8_t)(CODE_FIRST + i % CODE_COUNT));
  }
}

/*!
\brief  Measured: draw every cell of the screen.
*/
static void run_screen(void)
{
  draw_cells(CELLS);
}

/*!
\brief  Measured: draw one line.
*/
static void run_line(void)
{
  draw_cells(COLUMNS);
}

/*!
\brief  Measured: compare the terminal with what the screen shows.
*/
static void run_scan(void)
{
  uint32_t count = 0;

  for (uint32_t row = 0; row < ROWS; row++) {
    for (uint32_t column = 0; column < COLUMNS; column++) {
      const TerminalCell cell = TerminalGetCell(&terminal, row, column);
      const TerminalCell *old = &shown[row * COLUMNS + column];

      if (cell.code != old->code || cell.style != old->style) {
        count++;
      }
    }
  }
  changed = count;
}

/*!
\brief  Measured: scroll the terminal by one line.
*/
static void run_lf(void)
{
  TerminalPut(&terminal, '\n');
}

/*!
\brief  Measured: empty the terminal.
*/
static void run_ff(void)
{
  TerminalPut(&terminal, '\f');
}

/*!
\brief  Measured: scroll the pixels by one line with 32-bit accesses.
*/
static void run_copy32(void)
{
  // Two pixels per word: the framebuffer is aligned on 8 bytes and its counts are even
  volatile uint32_t *words = (volatile uint32_t *)(uint32_t)fb_pixels;
  const uint32_t shift = LCD_WIDTH * CELL_H / 2U;

  for (uint32_t i = 0; i < SCROLL_PIXELS / 2U; i++) {
    words[i] = words[i + shift];
  }
  for (uint32_t i = SCROLL_PIXELS / 2U; i < SCREEN_PIXELS / 2U; i++) {
    words[i] = BLACK;
  }
}

/*!
\brief  Measure the whole screen, with the glyphs in QSPI then in DTCM.
*/
static void measure_font(const Font *font, const char *qspi_name, const char *dtcm_name)
{
  const uint32_t bytes = font->count * font->height * font->width * font->bpp / 8U;
  Font dtcm_font = *font;

  measured_font = font;
  measure(qspi_name, run_screen);

  // Volatile reads: the compiler would call memcpy, which the project does not have
  for (uint32_t i = 0; i < bytes; i++) {
    dtcm_glyphs[i] = ((const volatile uint8_t *)font->glyphs)[i];
  }
  dtcm_font.glyphs = dtcm_glyphs;
  measured_font = &dtcm_font;
  measure(dtcm_name, run_screen);
}

/*!
\brief  Run every measure.
*/
static void measure_all(void)
{
  (void)LtdcFifoUnderrun(); // Clear the flag

  measure("palette", run_palette);
  measure_font(font1, "1bpp qspi", "1bpp dtcm");
  measure_font(font4, "4bpp qspi", "4bpp dtcm");
  measured_font = font4;
  measure("line", run_line);

  // The screen shows the whole terminal: the comparison finds no change
  TerminalInit(&terminal, grid, COLUMNS, ROWS);
  for (uint32_t i = 0; i < CELLS; i++) {
    shown[i] = TerminalGetCell(&terminal, i / COLUMNS, i % COLUMNS);
  }
  measure("scan", run_scan);
  put_field("changed=", changed);
  UartPuts(console, "\n");

  // From the last line, a line feed scrolls
  for (uint32_t i = 1; i < ROWS; i++) {
    TerminalPut(&terminal, '\n');
  }
  measure("lf", run_lf);
  measure("ff", run_ff);
  measure("copy32", run_copy32);

  put_field("underrun=", LtdcFifoUnderrun() ? 1U : 0U);
  UartPuts(console, "\n");
}

/*!
\brief  Draw a text on the sheet.
\return Column after the text.
*/
static uint32_t put_text(uint32_t row, uint32_t column, const Font *font,
                         const TextPalette *palette, const char *text)
{
  for (; *text != '\0'; text++) {
    TextChar(&screen, column * CELL_W, row * CELL_H, font, palette, (uint8_t)*text);
    column++;
  }
  return column;
}

/*!
\brief  Draw a text on the sheet, in colours of its own.
\return Column after the text.
*/
static uint32_t put_colour(uint32_t row, uint32_t column, uint16_t colour, uint16_t background,
                           const char *text)
{
  TextPalette palette;

  TextPaletteInit(&palette, colour, background);
  return put_text(row, column, font4, &palette, text);
}

/*!
\brief  Draw the 95 characters on two lines of the sheet.
*/
static void put_codes(uint32_t row, const Font *font)
{
  uint8_t codes[CODE_COUNT];

  for (uint32_t i = 0; i < CODE_COUNT; i++) {
    codes[i] = (uint8_t)(CODE_FIRST + i);
  }
  TextString(&screen, 0, row * CELL_H, font, &normal, codes, COLUMNS);
  TextString(&screen, 0, (row + 1U) * CELL_H, font, &normal, &codes[COLUMNS], CODE_COUNT - COLUMNS);
}

/*!
\brief  Draw the character sheet.
*/
static void draw_sheet(void)
{
  static const char sentence[] = "The quick brown fox jumps over the lazy dog, 0123456789.";
  static const char similar[] = "0O oO 1lI| 5S 8B 2Z {}[]() ;: ., '\" ` @&%# ~-_ \\/ <=>";
  static const char low[] = "gjpqy_{}";
  uint32_t column;

  FbClear(&screen, BLACK);

  (void)put_text(0, 0, font4, &normal, "JetBrains Mono Regular 13 px, 8 x 16 cells, 60 x 17");
  (void)put_text(1, 0, font4, &normal, "1 bit per pixel");
  put_codes(2, font1);
  (void)put_text(4, 0, font4, &normal, "4 bits per pixel");
  put_codes(5, font4);

  (void)put_text(8, 0, font1, &normal, sentence);
  (void)put_text(9, 0, font4, &normal, sentence);
  (void)put_text(10, 0, font1, &normal, similar);
  (void)put_text(11, 0, font4, &normal, similar);

  column = put_colour(12, 0, BLACK, WHITE, "Black on white");
  column = put_colour(12, column + 1U, GREEN, BLACK, "Green");
  column = put_colour(12, column + 1U, YELLOW, BLACK, "Yellow");
  (void)put_colour(12, column + 1U, CYAN, BLACK, "Cyan");

  // The special cells of the terminal
  column = put_text(13, 0, font4, &normal, "From 0x80: ");
  column = put_colour(13, column, BLACK, WHITE, "?");
  column = put_text(13, column, font4, &normal, "  Error: ");
  column = put_colour(13, column, WHITE, RED, "!");
  column = put_text(13, column, font4, &normal, "  Cursor: ");
  FbRect(&screen, column * CELL_W, 14U * CELL_H - CURSOR_H, CELL_W, CURSOR_H, WHITE);

  // The right edge, then the bottom edge with descenders
  for (uint32_t i = 0; i < COLUMNS; i++) {
    TextChar(&screen, i * CELL_W, 15U * CELL_H, font4, &normal, (uint8_t)('0' + i % 10U));
    TextChar(&screen, i * CELL_W, 16U * CELL_H, (i < COLUMNS / 2U) ? font1 : font4, &normal,
             (uint8_t)low[i % (sizeof(low) - 1U)]);
  }
}

/*!
\brief  Application entry point: measure the drawing, then show the character sheet.
\return Never returns.
*/
int main(void)
{
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
  UartPuts(console, "\ntext console: character sheet\n");

  if (RccInitPixelClock9MHz() != SUCCESS) {
    halt("text console: pixel clock error\n");
  }
  BoardLcdPinsInit();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // Black background until layer 1 is on

  // The whole screen is drawn before layer 1 shows it: the first image is complete
  FbClear(&screen, BLACK);
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, (uint32_t)fb_pixels);
  BoardLcdPowerOn();

  measure_all();
  draw_sheet();
  UartPuts(console, "sheet drawn\n");

  while (1) {}
}
