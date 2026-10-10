// SPDX-License-Identifier: MIT
/*!
****************************
\file       09-securebootloader/main.c
\brief      Bootloader that only starts the application it was built for.

\author     Z. BEN-AKKA
\version    1.3
\date       10/10/2026

\details
  Same flow as 08-custombootloader, plus a SHA-256 check (sha256.c):
  1) Resets the N25Q128A, checks its ID and maps it at 0x90000000.
  2) Checks the application's initial SP and PC.
  3) Hashes APP_IMAGE_SIZE bytes of the QSPI image and compares the digest
     with app_image_sha256, generated at build time by tools/fwhash.py.
  4) Jumps to the application only if both digests match.
  LD1 on failure: steady on (QSPI error), fast blink (no application),
  three flashes then a pause (hash mismatch).

\remarks
- Not covered: reflashing the bootloader itself (needs RDP level 1 and
  write protection on sector 0).
- Not covered: the external flash changing between check and execution
  (copy to RAM, then hash and run the copy).
- TODO: replace the pinned hash with a signature check to allow updates.

\section securebootloader_main_c_version_history Version history
| Version | Date       | Author      | Description                                         |
|:-------:|:----------:|:------------|:----------------------------------------------------|
| 1.0     | 09/10/2026 | Z. BEN-AKKA | Initial version.                                    |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md.        |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Shared functions moved to common/.                  |
| 1.3     | 10/10/2026 | Z. BEN-AKKA | Generic drivers, board specifics from common/board. |
****************************
*/

#include <stdint.h>

#include "defines.h"
#include "board/board.h"
#include "boot/boot.h"
#include "delay/delay.h"
#include "led/led.h"
#include "qspi/qspi.h"
#include "uart/uart.h"

#include "sha256.h"
#include "app_hash.h" // generated: APP_IMAGE_SIZE, app_image_sha256[]

#define BAUDRATE 115200UL

static const Uart *const console = &BOARD_UART_VCP; ///< Console output.
#define APP_BASE QSPI_MEM_BASE
#define APP_SIZE (16UL * 1024 * 1024) ///< Whole N25Q128A.

/// LD1 patterns shown by fail().
enum led_code {
  LED_STEADY,     ///< QSPI flash missing or not answering.
  LED_FAST_BLINK, ///< No valid application vector table.
  LED_ALARM,      ///< Application present but hash mismatch.
};

/*!
\brief  Report an error and halt, showing it on LD1.
\param  why   Message printed on the console.
\param  code  LD1 pattern.
*/
static void __attribute__((noreturn)) fail(const char *why, enum led_code code)
{
  UartPuts(console, "boot: ");
  UartPuts(console, why);
  UartPuts(console, ", halted\n");

  LedInit(&BOARD_LED_LD1);
  LedOn(&BOARD_LED_LD1);

  while (1) {
    switch (code) {
    case LED_STEADY:
      break;
    case LED_FAST_BLINK:
      LedToggle(&BOARD_LED_LD1);
      DelayCycles(400000);
      break;
    case LED_ALARM:
      for (int i = 0; i < 3; i++) {
        LedOn(&BOARD_LED_LD1);
        DelayCycles(300000);
        LedOff(&BOARD_LED_LD1);
        DelayCycles(300000);
      }
      DelayCycles(2000000);
      break;
    }
  }
}

/*!
\brief  Print a SHA-256 digest as 64 lowercase hexadecimal digits.
*/
static void print_digest(const uint8_t *d)
{
  for (int i = 0; i < SHA256_DIGEST_SIZE; i++) {
    UartPutc(console, "0123456789abcdef"[d[i] >> 4]);
    UartPutc(console, "0123456789abcdef"[d[i] & 0xF]);
  }
}

/*!
\brief  Compare two digests in constant time.
\return Non-zero if equal.
*/
static int digest_equal(const uint8_t *a, const uint8_t *b)
{
  uint8_t diff = 0;

  for (int i = 0; i < SHA256_DIGEST_SIZE; i++) {
    diff |= a[i] ^ b[i];
  }
  return diff == 0;
}

/*!
\brief  Hash the application in QSPI and halt unless it matches the pinned digest.
*/
static void verify_app(void)
{
  uint8_t digest[SHA256_DIGEST_SIZE];
  sha256_ctx ctx;

  UartPuts(console, "boot: hashing ");
  UartPutHex32(console, APP_IMAGE_SIZE);
  UartPuts(console, " bytes at 0x90000000\n");

  sha256_init(&ctx);
  sha256_update(&ctx, (const void *)APP_BASE, APP_IMAGE_SIZE);
  sha256_final(&ctx, digest);

  UartPuts(console, "boot: sha256   ");
  print_digest(digest);
  UartPuts(console, "\n");

  if (!digest_equal(digest, app_image_sha256)) {
    UartPuts(console, "boot: expected ");
    print_digest(app_image_sha256);
    UartPuts(console, "\n");
    fail("FIRMWARE REJECTED, hash mismatch", LED_ALARM);
  }
  UartPuts(console, "boot: firmware authentic\n");
}

/*!
\brief  Read and print the flash ID; halt unless it is an N25Q128A.
*/
static void check_flash_id(void)
{
  uint32_t id;

  if (QspiReadJedecId(&id) != SUCCESS) {
    fail("QSPI stuck busy", LED_STEADY);
  }
  UartPuts(console, "boot: QSPI id ");
  UartPutHex32(console, id);
  UartPuts(console, "\n");
  if (id != N25Q128A_ID) {
    fail("unexpected QSPI flash", LED_STEADY);
  }
}

/*!
\brief  Read the application's initial SP and PC; halt unless they look valid.
\param  sp  Output: initial stack pointer (vector table word 0).
\param  pc  Output: reset handler address (vector table word 1).
*/
static void read_app_vector(uint32_t *sp, uint32_t *pc)
{
  *sp = REG(APP_BASE);
  *pc = REG(APP_BASE + 4);
  UartPuts(console, "boot: app SP ");
  UartPutHex32(console, *sp);
  UartPuts(console, ", PC ");
  UartPutHex32(console, *pc);
  UartPuts(console, "\n");
  if (!BootAppLooksValid(*sp, *pc, APP_BASE, APP_SIZE)) {
    fail("no application at 0x90000000", LED_FAST_BLINK);
  }
}

/*!
\brief  Enable the I-cache and hand over to the application.

\details
  The application inherits the memory-mapped QUADSPI and its pins (it must
  not reconfigure them), USART1 on PA9, the I-cache, and VTOR on its table.

\param  sp  Initial stack pointer.
\param  pc  Reset handler address.
*/
static void __attribute__((noreturn)) start_app(uint32_t sp, uint32_t pc)
{
  BootICacheEnable();
  UartPuts(console, "boot: jumping\n");
  UartFlush(console);
  BootJump(APP_BASE, sp, pc);
}

/*!
\brief  Bootloader entry point: map the QSPI flash, check the application, start it.
\return Never returns.
*/
int main(void)
{
  UartInit(console, HSI_HZ, BAUDRATE);
  UartPuts(console, "\nboot: 09-securebootloader\n");

  BoardQspiPinsInit();
  QspiInit(N25Q128A_SIZE_LOG2, 0); // HCLK / 1
  if (QspiSoftwareReset() != SUCCESS) {
    fail("QSPI stuck busy", LED_STEADY);
  }
  check_flash_id();
  if (QspiMemoryMappedQuadOut(N25Q_CMD_QUAD_OUT_READ, N25Q_QUAD_OUT_DUMMY) != SUCCESS) {
    fail("QSPI stuck busy", LED_STEADY);
  }

  uint32_t sp, pc;
  read_app_vector(&sp, &pc);
  verify_app();
  start_app(sp, pc);
}
