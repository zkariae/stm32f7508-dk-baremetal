"""Values the hil-bench firmware under test must report.

COMMANDS is the list CAPS must return, in the order of the firmware's command
table (protocol.md section 6.3). Each new command adds its name here; the
smoke and CAPS tests derive their expected values from this list. The QSPI
values are those of the board's flash and of protocol.md sections 6.6 to 6.10.

Version: 1.2
Date: 28/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
  1.1  27/10/2026  Add LED_SET and LED_GET (protocol 1.1).
  1.2  28/10/2026  Add the QSPI commands and values (protocol 1.2).
"""

COMMANDS = [
    "HELLO", "CAPS", "LED_SET", "LED_GET",
    "QSPI_ID", "QSPI_READ", "QSPI_ERASE", "QSPI_WRITE",
]

QSPI_JEDEC_ID = 0x0018BA20      # N25Q128A, protocol.md section 6.7
QSPI_FLASH_SIZE = 0x01000000    # 16 MB
QSPI_TEST_START = 0x00FF0000    # Test area, section 6.6
QSPI_TEST_END = 0x01000000      # Excluded
QSPI_ERASE_SIZE = 4096
QSPI_PAGE_SIZE = 256
QSPI_DATA_MAX = 32              # Bytes per QSPI_READ or QSPI_WRITE
