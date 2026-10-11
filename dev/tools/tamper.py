#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       tamper.py
# \brief      Patch one 32-bit word of a firmware image.
#
# \author     Z. BEN-AKKA
# \version    1.1
# \date       10/10/2026
#
# \details
#   Builds the modified application used to test 09-securebootloader.
#
# \section tamper_py_version_history Version history
# | Version | Date       | Author      | Description                 |
# |:-------:|:----------:|:------------|:----------------------------|
# | 1.0     | 09/10/2026 | Z. BEN-AKKA | Initial version.            |
# | 1.1     | 10/10/2026 | Z. BEN-AKKA | Header per Contributing.md. |
# ****************************
# */
"""
Play the attacker: patch one 32-bit word in a firmware image.

09-securebootloader uses it to turn the blink into one that runs four times
faster: a perfectly working application, just not the one the bootloader
was built for, so it must be refused.

    ./tamper.py in.bin out.bin 0x000f4240 0x0003d090

The old value must appear exactly once, so the patch cannot land somewhere
unexpected.
"""

import struct
import sys


def main():
    if len(sys.argv) != 5:
        sys.exit("usage: tamper.py IN.bin OUT.bin OLD NEW")

    src, dst = sys.argv[1], sys.argv[2]
    old = struct.pack("<I", int(sys.argv[3], 0))   # little-endian, as in memory
    new = struct.pack("<I", int(sys.argv[4], 0))

    with open(src, "rb") as f:
        data = bytearray(f.read())

    count = data.count(old)
    if count != 1:
        sys.exit(f"{sys.argv[3]} found {count} times in {src}, expected once")

    offset = data.find(old)
    data[offset:offset + 4] = new
    with open(dst, "wb") as f:
        f.write(data)
    print(f"patched {sys.argv[3]} -> {sys.argv[4]} at offset {offset:#x}")


if __name__ == "__main__":
    main()
