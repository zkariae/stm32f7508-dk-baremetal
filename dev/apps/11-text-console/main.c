// SPDX-License-Identifier: MIT
/*!
****************************
\file       11-text-console/main.c
\brief      Text console: what arrives on the UART is shown on the LCD.

\author     Z. BEN-AKKA
\version    1.2
\date       25/11/2026

\details
  Terminal of 60 columns and 17 lines, 115200 baud, no echo on the UART.
  1) Stops USART1, left enabled by the bootloader, before any clock change:
     USART_BRR is written only with UE = 0 (RM0385 Rev 9, p. 1062).
  2) Copies the glyphs from QSPI to DTCM, where they are drawn about four
     times faster (phase I, decision C).
  3) Each turn of the loop reads at most 256 events, then draws the changed
     cells of at most one line: the reception queue, 22 ms long, is read again
     after about 2 ms. Line feeds received meanwhile cost one drawing.
  4) One second after the last event, prints the bytes read, the time from the
     first event to the last and the errors.
  Built as 11-text-console-app, run in place from QSPI behind the 08 bootloader.

\section text_console_main_c_version_history Version history
| Version | Date       | Author      | Description                                                    |
|:-------:|:----------:|:------------|:---------------------------------------------------------------|
| 1.0     | 24/11/2026 | Z. BEN-AKKA | Initial version.                                               |
| 1.1     | 25/11/2026 | Z. BEN-AKKA | Character sheet in both formats; rendering, terminal measured. |
| 1.2     | 25/11/2026 | Z. BEN-AKKA | UART to LCD terminal; measuring code removed.                  |
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

#define CELL_W       8U                    ///< Width of a character cell.
#define CELL_H       16U                   ///< Height of a character cell.
#define COLUMNS      (LCD_WIDTH / CELL_W)  ///< 60 cells per line.
#define ROWS         (LCD_HEIGHT / CELL_H) ///< 17 lines.
#define CELLS        (COLUMNS * ROWS)      ///< 1020 cells on the screen.
#define GLYPHS_BYTES (95U * 64U)           ///< Glyphs of the 4-bit font.
#define CURSOR_H     2U                    ///< Height of the cursor line.
#define CURSOR_FLAG  0x80U                 ///< In the style of a shown cell: holds the cursor.

#define RX_BATCH   UART_RX_BUFFER_SIZE ///< Events read in a turn, at most.
#define RX_IDLE_MS 1000U               ///< Silence before a reception report.

#define BLACK 0x0000U
#define WHITE 0xFFFFU
#define RED   0xF800U

/// RGB565 framebuffer in SRAM (linker section .framebuffer): too large for the 64 KB DTCM.
static volatile uint16_t fb_pixels[LCD_WIDTH * LCD_HEIGHT]
    __attribute__((section(".framebuffer"), aligned(8)));

/// The LCD framebuffer, shown by LTDC layer 1.
static const Framebuffer screen = {fb_pixels, LCD_WIDTH, LCD_HEIGHT};

static const Uart *const console = &BOARD_UART_VCP; ///< Text input, reports output.

static uint8_t glyphs[GLYPHS_BYTES]; ///< Glyphs copied from QSPI (.bss: DTCM).
static Font font;                    ///< The 4-bit font, reading these glyphs.
static TextPalette palettes[3];      ///< Colours of each TerminalStyle.

static TerminalCell grid[CELLS];  ///< Grid of the terminal.
static Terminal terminal;         ///< The terminal.
static TerminalCell shown[CELLS]; ///< What the screen shows, cursor included (CURSOR_FLAG).
static uint32_t next_row;         ///< Line looked at first for the next drawing.

/// Reception since the last report.
typedef struct {
  uint32_t active;   ///< An event was read since the last report.
  uint32_t first_ms; ///< Time of the first event.
  uint32_t last_ms;  ///< Time of the last event.
  uint32_t bytes;    ///< Bytes read from the queue.
} RxBurst;

static RxBurst burst;      ///< Reception in progress.
static UartRxStats before; ///< Counters at the last report.

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
\brief  Copy the glyphs to DTCM and compute the colours of the styles.
*/
static void text_init(void)
{
  font = FONT_MONO_8X16_4BPP;
  // Volatile reads: the compiler would call memcpy, which the project does not have
  for (uint32_t i = 0; i < GLYPHS_BYTES; i++) {
    glyphs[i] = ((const volatile uint8_t *)font.glyphs)[i];
  }
  font.glyphs = glyphs;

  TextPaletteInit(&palettes[TERMINAL_NORMAL], WHITE, BLACK);
  TextPaletteInit(&palettes[TERMINAL_INVERTED], BLACK, WHITE);
  TextPaletteInit(&palettes[TERMINAL_ERROR], WHITE, RED);
}

/*!
\brief  Start with an empty terminal on a black screen.
*/
static void terminal_init(void)
{
  FbClear(&screen, BLACK);
  TerminalInit(&terminal, grid, COLUMNS, ROWS);
  for (uint32_t i = 0; i < CELLS; i++) {
    shown[i] = TerminalGetCell(&terminal, i / COLUMNS, i % COLUMNS);
  }
}

/*!
\brief  Give the queued events to the terminal, RX_BATCH at most.
*/
static void receive(void)
{
  UartRxEvent event;

  for (uint32_t i = 0; i < RX_BATCH && UartRxGet(console, &event); i++) {
    const uint32_t now = SysTickMs();

    if (!burst.active) {
      burst.active = 1U;
      burst.first_ms = now;
      burst.bytes = 0U;
    }
    burst.last_ms = now;

    if (event <= UART_RX_EVENT_BYTE_MAX) {
      burst.bytes++;
      TerminalPut(&terminal, (uint8_t)event);
    } else {
      TerminalError(&terminal);
    }
  }
}

/*!
\brief  Draw a cell, with the cursor if its style holds CURSOR_FLAG.
*/
static void draw_cell(uint32_t row, uint32_t column, TerminalCell cell)
{
  const TextPalette *palette = &palettes[cell.style & ~CURSOR_FLAG];
  const uint32_t x = column * CELL_W;
  const uint32_t y = row * CELL_H;

  TextChar(&screen, x, y, &font, palette, cell.code);
  if (cell.style & CURSOR_FLAG) {
    // In the colour of the text, so that it shows on every style
    FbRect(&screen, x, y + CELL_H - CURSOR_H, CELL_W, CURSOR_H, palette->levels[TEXT_LEVELS - 1U]);
  }
}

/*!
\brief  Draw the cells of a line that differ from what the screen shows.
\return 1 if a cell was drawn, 0 if the line was up to date.
*/
static int draw_row(uint32_t row)
{
  uint32_t cursor_row;
  uint32_t cursor_column;
  int drawn = 0;

  TerminalGetCursor(&terminal, &cursor_row, &cursor_column);
  for (uint32_t column = 0; column < COLUMNS; column++) {
    TerminalCell cell = TerminalGetCell(&terminal, row, column);
    TerminalCell *old = &shown[row * COLUMNS + column];

    if (row == cursor_row && column == cursor_column) {
      cell.style |= CURSOR_FLAG;
    }
    if (cell.code != old->code || cell.style != old->style) {
      draw_cell(row, column, cell);
      *old = cell;
      drawn = 1;
    }
  }
  return drawn;
}

/*!
\brief  Draw the next line that changed, if any; the lines take turns.
*/
static void draw_next_row(void)
{
  for (uint32_t i = 0; i < ROWS; i++) {
    const uint32_t row = next_row;

    next_row = (next_row + 1U) % ROWS;
    if (draw_row(row)) {
      return;
    }
  }
}

/*!
\brief  Print the reception and the errors since the last report, after a silence.
*/
static void report_when_idle(void)
{
  UartRxStats now;

  if (!burst.active || SysTickMs() - burst.last_ms < RX_IDLE_MS) {
    return;
  }

  UartRxGetStats(console, &now);
  put_field("rx: bytes=", burst.bytes);
  put_field(" ms=", burst.last_ms - burst.first_ms);
  put_field(" fe=", now.framing_errors - before.framing_errors);
  put_field(" ne=", now.noise_errors - before.noise_errors);
  put_field(" ore=", now.overrun_errors - before.overrun_errors);
  put_field(" ovf=", now.buffer_overflows - before.buffer_overflows);
  UartPuts(console, "\n");
  before = now;
  burst.active = 0U;
}

/*!
\brief  Application entry point: show the text received on the UART.
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
  UartInit(console, APB2_HZ, BAUDRATE);
  UartPuts(console, "\ntext console: 60 x 17\n");

  if (RccInitPixelClock9MHz() != SUCCESS) {
    halt("text console: pixel clock error\n");
  }
  BoardLcdPinsInit();
  LtdcInit(&BOARD_LCD_TIMING, 0x00000000U); // Black background until layer 1 is on

  // The whole screen is drawn before layer 1 shows it: the first image is complete
  text_init();
  terminal_init();
  LtdcLayer1InitRgb565(&BOARD_LCD_TIMING, (uint32_t)fb_pixels);
  BoardLcdPowerOn();

  UartRxStart(console);

  while (1) {
    receive();
    draw_next_row();
    report_when_idle();
  }
}
