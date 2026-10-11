#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       dfu.py
# \brief      Flash a raw binary through the STM32 ROM bootloader (USB DFU).
#
# \author     Z. BEN-AKKA
# \version    1.1
# \date       10/10/2026
#
# \details
#   DfuSe client over pyusb: erase, write, verify, then run. See the
#   docstring below for usage.
#
# \section dfu_py_version_history Version history
# | Version | Date       | Author      | Description                 |
# |:-------:|:----------:|:------------|:----------------------------|
# | 1.0     | 25/09/2026 | Z. BEN-AKKA | Initial version.            |
# | 1.1     | 10/10/2026 | Z. BEN-AKKA | Header per Contributing.md. |
# ****************************
# */
"""
Flash a firmware image over USB through the STM32 ROM bootloader.

The bootloader at 0x1FF00000 speaks DfuSe, ST's extension of USB DFU 1.1.
Everything goes through control transfers on endpoint 0:

  - a download with block number 0 carries a command: set the address
    pointer (0x21) or erase the sector at an address (0x41);
  - a download with block number n >= 2 writes wTransferSize bytes at
    address_pointer + (n - 2) * wTransferSize;
  - uploads read back the same way.

The ROM only starts an erase or a write when it receives the GETSTATUS that
follows, then answers "busy, ask again in N ms" until it is done.

To get the board into the bootloader: hold USER, press and release RESET,
release USER. The device then enumerates as 0483:df11 on the USB OTG FS
connector (CN13), not on the ST-LINK one.

    ./dfu.py work/blink.bin              erase, write, verify, run
    ./dfu.py work/blink.bin --no-verify
    ./dfu.py --list                      show the memory map the ROM reports

Needs pyusb and libusb:  pip install pyusb
Under WSL, attach the device first:  usbipd attach --wsl --busid <id>
"""

import argparse
import re
import struct
import sys
import time

try:
    import usb.core
    import usb.util
except ImportError:
    sys.exit("pyusb is missing — pip install pyusb")

VID, PID = 0x0483, 0xDF11
FLASH_BASE = 0x08000000

# DFU 1.1 class requests
DNLOAD, UPLOAD, GETSTATUS, CLRSTATUS, ABORT = 1, 2, 3, 4, 6

# DFU 1.1 device states, only the ones we test against
STATE_IDLE = 2
STATE_DNBUSY = 4
STATE_DNLOAD_IDLE = 5
STATE_ERROR = 10

# DfuSe commands, sent as a download with block number 0
CMD_SET_ADDRESS = 0x21
CMD_ERASE = 0x41

REQ_OUT = 0x21   # host to device, class, interface
REQ_IN = 0xA1    # device to host, class, interface

TIMEOUT_MS = 5000

# Sector attribute bits, encoded as the letters 'a'..'g'
READABLE, ERASABLE, WRITABLE = 1, 2, 4


class DfuError(Exception):
    pass


def parse_layout(desc):
    """Decode a DfuSe interface string into a name and a list of sectors.

    "@Internal Flash  /0x08000000/04*032Kg,01*128Kg" reads: four 32 KB
    sectors from 0x08000000, then one of 128 KB, all 'g' = readable,
    erasable and writable. Further /address/groups pairs may follow.
    """
    parts = desc.split("/")
    name = parts[0].lstrip("@").strip()
    sectors = []
    for i in range(1, len(parts) - 1, 2):
        addr = int(parts[i], 16)
        for group in parts[i + 1].split(","):
            m = re.fullmatch(r"\s*(\d+)\*(\d+)\s*([KM]?)([a-g])\s*", group)
            if not m:
                raise DfuError(f"cannot parse memory layout: {desc!r}")
            count, size = int(m[1]), int(m[2])
            size *= {"": 1, "K": 1024, "M": 1024 * 1024}[m[3]]
            attrs = ord(m[4]) - ord("a") + 1
            for _ in range(count):
                sectors.append((addr, size, attrs))
                addr += size
    return name, sectors


def transfer_size(dev, default=2048):
    """wTransferSize from the DFU functional descriptor (type 0x21), which
    pyusb hands back as raw bytes attached to the config or an interface."""
    cfg = dev.get_active_configuration()
    blobs = [cfg.extra_descriptors] + [i.extra_descriptors for i in cfg]
    for raw in blobs:
        i = 0
        while i + 1 < len(raw) and raw[i]:
            if raw[i + 1] == 0x21 and raw[i] >= 7:
                return raw[i + 5] | raw[i + 6] << 8
            i += raw[i]
    return default


class Dfu:
    def __init__(self, dev, alt=0):
        self.dev = dev
        try:
            dev.get_active_configuration()
        except usb.core.USBError:
            dev.set_configuration()
        usb.util.claim_interface(dev, 0)
        dev.set_interface_altsetting(interface=0, alternate_setting=alt)
        intf = dev.get_active_configuration()[(0, alt)]
        self.name, self.sectors = parse_layout(
            usb.util.get_string(dev, intf.iInterface))
        self.xfer = transfer_size(dev)

    # --- DFU 1.1 -------------------------------------------------------

    def _out(self, req, value, data=b""):
        self.dev.ctrl_transfer(REQ_OUT, req, value, 0, data, TIMEOUT_MS)

    def status(self):
        s = self.dev.ctrl_transfer(REQ_IN, GETSTATUS, 0, 0, 6, TIMEOUT_MS)
        return s[0], s[1] | s[2] << 8 | s[3] << 16, s[4]

    def to_idle(self):
        """Clear whatever a previous, interrupted session left behind."""
        _, _, state = self.status()
        if state == STATE_ERROR:
            self._out(CLRSTATUS, 0)
        elif state != STATE_IDLE:
            self._out(ABORT, 0)

    def _download(self, block, data):
        self._out(DNLOAD, block, data)
        while True:
            status, poll, state = self.status()
            if status:
                raise DfuError(f"device reported status {status:#x} "
                               f"in state {state}")
            if state != STATE_DNBUSY:
                break
            time.sleep(poll / 1000)
        if state != STATE_DNLOAD_IDLE:
            raise DfuError(f"unexpected state {state} after download")

    def _command(self, cmd, addr):
        self._download(0, struct.pack("<BI", cmd, addr))

    # --- Memory --------------------------------------------------------

    def check_writable(self, addr, length):
        pos, end = addr, addr + length
        for start, size, attrs in sorted(self.sectors):
            if start <= pos < start + size and attrs & WRITABLE:
                pos = start + size
        if pos < end:
            raise DfuError(f"{addr:#010x}..{end:#010x} is not writable "
                           f"(stops at {pos:#010x})")

    def erase(self, addr, length):
        for start, size, attrs in self.sectors:
            if start < addr + length and start + size > addr:
                if not attrs & ERASABLE:
                    raise DfuError(f"sector at {start:#010x} is not erasable")
                print(f"  erase  {start:#010x}  ({size // 1024} KB)")
                self._command(CMD_ERASE, start)

    def write(self, addr, data):
        self._command(CMD_SET_ADDRESS, addr)
        for off in range(0, len(data), self.xfer):
            self._download(2 + off // self.xfer, data[off:off + self.xfer])
            done = min(off + self.xfer, len(data))
            print(f"\r  write  {done}/{len(data)} bytes", end="", flush=True)
        print()

    def read(self, addr, length):
        self._command(CMD_SET_ADDRESS, addr)
        self._out(ABORT, 0)            # uploads are only accepted from dfuIDLE
        out = bytearray()
        block = 2
        while len(out) < length:
            n = min(self.xfer, length - len(out))
            out += self.dev.ctrl_transfer(REQ_IN, UPLOAD, block, 0, n,
                                          TIMEOUT_MS)
            block += 1
        self._out(ABORT, 0)
        return bytes(out)

    def leave(self, addr):
        """A zero-length download ends the session; on the GETSTATUS that
        follows, the ROM jumps to the vector table at addr. The device
        vanishes from the bus mid-request, so errors here are expected."""
        self._command(CMD_SET_ADDRESS, addr)
        self._out(DNLOAD, 0)
        try:
            self.status()
        except usb.core.USBError:
            pass
        usb.util.dispose_resources(self.dev)


def find_device():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        sys.exit("no DFU device (0483:df11) found\n"
                 "  hold USER, press and release RESET, then release USER\n"
                 "  plug the cable into USB OTG FS (CN13), not ST-LINK\n"
                 "  under WSL: usbipd attach --wsl --busid <id>")
    return dev


def list_device(dev):
    cfg = dev.get_active_configuration()
    for intf in cfg:
        print(f"  alt {intf.bAlternateSetting}: "
              f"{usb.util.get_string(dev, intf.iInterface)}")
    print(f"  transfer size: {transfer_size(dev)} bytes")


def main():
    p = argparse.ArgumentParser(
        description="Flash a raw binary through the STM32 USB DFU bootloader.")
    p.add_argument("image", nargs="?", help="raw binary (.bin) to flash")
    p.add_argument("--address", type=lambda s: int(s, 0), default=FLASH_BASE,
                   help="load address (default 0x08000000)")
    p.add_argument("--no-verify", dest="verify", action="store_false",
                   help="skip reading the image back")
    p.add_argument("--no-run", dest="run", action="store_false",
                   help="stay in the bootloader afterwards")
    p.add_argument("--list", action="store_true",
                   help="show the memory regions the bootloader exposes")
    args = p.parse_args()
    if not args.list and args.image is None:
        p.error("an image is required unless --list is given")

    dev = find_device()
    try:
        if args.list:
            list_device(dev)
            return
        dfu = Dfu(dev)
    except usb.core.USBError as e:
        if e.errno == 13:
            sys.exit("permission denied on 0483:df11 — run with sudo "
                     "or add a udev rule")
        raise

    with open(args.image, "rb") as f:
        data = f.read()
    if not data:
        sys.exit(f"{args.image} is empty")
    # Pad to a whole word with the erased value, so the ROM never has to
    # program a partial one
    data += b"\xff" * (-len(data) % 4)

    try:
        dfu.check_writable(args.address, len(data))
        dfu.to_idle()
        print(f"{dfu.name}: {len(data)} bytes at {args.address:#010x}")
        dfu.erase(args.address, len(data))
        dfu.write(args.address, data)
        if args.verify:
            if dfu.read(args.address, len(data)) != data:
                raise DfuError("verify failed: flash does not match image")
            print("  verify ok")
        if args.run:
            dfu.leave(args.address)
            print("  running")
    except DfuError as e:
        sys.exit(f"dfu: {e}")


if __name__ == "__main__":
    main()
