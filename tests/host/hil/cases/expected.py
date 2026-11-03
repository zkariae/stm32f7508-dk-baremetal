"""Values the hil-bench firmware under test must report.

COMMANDS is the list CAPS must return, in the order of the firmware's command
table (protocol.md section 6.3). Each new command adds its name here; the
smoke and CAPS tests derive their expected values from this list. The QSPI
values are those of the board's flash and of protocol.md sections 6.6 to 6.10.
The LCD values are those of the board's RK043FN48H panel and of protocol.md
sections 6.11 to 6.19; the pin table comes from the alternate function
mapping of the STM32F750x8 datasheet [N6], not from the firmware.

Version: 1.3
Date: 03/11/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
  1.1  27/10/2026  Add LED_SET and LED_GET (protocol 1.1).
  1.2  28/10/2026  Add the QSPI commands and values (protocol 1.2).
  1.3  03/11/2026  Add GPIO_CONFIG, the LCD commands and values (protocol 1.3).
"""

COMMANDS = [
    "HELLO", "CAPS", "LED_SET", "LED_GET",
    "QSPI_ID", "QSPI_READ", "QSPI_ERASE", "QSPI_WRITE",
    "GPIO_CONFIG", "LCD_INIT", "LCD_CLOCK", "LCD_TIMING",
    "LCD_LAYER", "LCD_SCAN", "LCD_FILL", "LCD_PIXEL",
]

QSPI_JEDEC_ID = 0x0018BA20      # N25Q128A, protocol.md section 6.7
QSPI_FLASH_SIZE = 0x01000000    # 16 MB
QSPI_TEST_START = 0x00FF0000    # Test area, section 6.6
QSPI_TEST_END = 0x01000000      # Excluded
QSPI_ERASE_SIZE = 4096
QSPI_PAGE_SIZE = 256
QSPI_DATA_MAX = 32              # Bytes per QSPI_READ or QSPI_WRITE

# The 28 LTDC signals of the panel: (port, pin, alternate function), all AF14
# except LTDC_B4 on PG12, which is AF9 (datasheet [N6])
LCD_PINS = [
    # Red R0 to R7
    ("I", 15, 14), ("J", 0, 14), ("J", 1, 14), ("J", 2, 14),
    ("J", 3, 14), ("J", 4, 14), ("J", 5, 14), ("J", 6, 14),
    # Green G0 to G7
    ("J", 7, 14), ("J", 8, 14), ("J", 9, 14), ("J", 10, 14),
    ("J", 11, 14), ("K", 0, 14), ("K", 1, 14), ("K", 2, 14),
    # Blue B0 to B7
    ("E", 4, 14), ("J", 13, 14), ("J", 14, 14), ("J", 15, 14),
    ("G", 12, 9), ("K", 4, 14), ("K", 5, 14), ("K", 6, 14),
    # HSYNC, VSYNC, CLK, DE
    ("I", 10, 14), ("I", 9, 14), ("I", 14, 14), ("K", 7, 14),
]

# Outputs driven high by LCD_INIT (section 6.13): LCD_DISP and LCD_BL_CTRL
LCD_POWER_PINS = [("I", 12), ("K", 3)]

LCD_TIMING = {                  # LCD_TIMING result, section 6.15
    "hsw": "1", "hbp": "42", "width": "480", "hfp": "8",
    "vsw": "10", "vbp": "2", "height": "272", "vfp": "4",
}
LCD_PIXEL_HZ = 9000000          # Section 6.14
LCD_FB_ADDR = 0x20010000        # First SRAM address, section 6.12
LCD_WIDTH = 480
LCD_HEIGHT = 272
