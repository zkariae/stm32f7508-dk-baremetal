"""Values the hil-bench firmware under test must report.

COMMANDS is the list CAPS must return, in the order of the firmware's command
table (protocol.md section 6.3). Each new command adds its name here; the
smoke and CAPS tests derive their expected values from this list.

Version: 1.1
Date: 27/10/2026
Author: Z. BEN-AKKA
History:
  1.0  27/10/2026  Initial version.
  1.1  27/10/2026  Add LED_SET and LED_GET (protocol 1.1).
"""

COMMANDS = ["HELLO", "CAPS", "LED_SET", "LED_GET"]
