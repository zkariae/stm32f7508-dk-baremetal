<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       cd/client/README.md
\brief      Client guide of a release: check, set up, flash, update, Docker.

\author     Z. BEN-AKKA
\version    1.0
\date       16/11/2026

\details
  Delivered as README.md at the root of every release folder
  (cd/README.md section 5.2). Written for the developer who receives a
  release: how to check the download, set up OpenOCD and the USB access on
  Linux, WSL or Windows, flash the board with flash.sh, flash.bat or the
  flasher image, update to a newer release, and what each exit code means.
  It stays generic: the delivered application and its version are in
  RELEASE_NOTES.md.

\section client_readme_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 16/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
-->

# STM32F7508-DK bare-metal: release guide

This release flashes one application to an STM32F7508-DK board through its
on-board ST-LINK. Nothing needs to be built: the binaries are in the
release, and the scripts check them before they flash anything.

In this guide, `<version>` stands for the version of the release, for
example `1.0.0` for the release `release-v1.0.0`.

## 1. Contents of a release

The GitHub Release `release-v<version>` holds two files:

| File | Content |
|:--|:--|
| `stm32f7508-dk-baremetal-release-v<version>.zip` | The release folder below |
| `stm32f7508-dk-baremetal-release-v<version>.zip.sha256` | The SHA-256 of the zip, to check the download |

```text
stm32f7508-dk-baremetal-release-v<version>/
├── README.md          This guide
├── RELEASE_NOTES.md   What changed, the delivered application, the SHA-256 of each image
├── SHA256SUMS         SHA-256 of every other file of the folder
├── flash.sh           Flashing script, Linux and WSL
├── flash.bat          Flashing script, Windows
├── images.txt         The images to flash, in order
└── images/
    └── <image>.bin    One per line of images.txt
```

`images.txt` has one line per image, in flashing order: the image, its
file, the memory, the address and the OpenOCD options. For example:

```text
# image file memory address openocd-options
07-lcd-logo images/07-lcd-logo.bin flash 0x08000000 -f interface/stlink.cfg -f target/stm32f7x.cfg
```

An application is either:

- **standalone**: one image in the internal flash of the microcontroller.
  It replaces whatever was there, a bootloader included;
- **a bootloader pair**: an application in the external QSPI flash, and the
  bootloader that starts it from the internal flash. The pair is always
  flashed whole, the QSPI application first.

`RELEASE_NOTES.md` says which application the release delivers, and
whether it is standalone or a pair.

## 2. Check the download

Keep the zip and its `.sha256` file in the same folder.

Linux or WSL:

```bash
sha256sum -c stm32f7508-dk-baremetal-release-v<version>.zip.sha256
unzip stm32f7508-dk-baremetal-release-v<version>.zip
```

The first command must print `OK`.

Windows (cmd):

```bat
certutil -hashfile stm32f7508-dk-baremetal-release-v<version>.zip SHA256
type stm32f7508-dk-baremetal-release-v<version>.zip.sha256
```

The two hashes must be the same (`certutil` may print it in upper case or
with spaces). Then extract the zip with the Explorer.

The flashing scripts check every extracted file again against `SHA256SUMS`
before they flash anything.

## 3. Set up

The board is connected by its USB ST-LINK connector (CN14). OpenOCD
0.11.0 or later is needed: earlier versions cannot program the QSPI
flash.

### 3.1 Linux

```bash
sudo apt install openocd
openocd --version
```

The package installs a udev rule (`60-openocd.rules`) that gives the
ST-LINK to the `plugdev` group. Add your user to it once, then log out and
in again:

```bash
sudo usermod -aG plugdev "$USER"
```

### 3.2 WSL

WSL does not see USB devices by itself: install
[usbipd-win](https://github.com/dorssel/usbipd-win) on Windows, then, in a
PowerShell run as administrator:

```powershell
usbipd list                          # find the BUSID of the ST-LINK (0483:374b)
usbipd bind --busid <busid>          # once
usbipd attach --wsl --busid <busid>  # after each plug or Windows restart
```

Then set up the WSL distribution as on Linux (section 3.1). After
`usermod`, restart WSL from Windows with `wsl --shutdown`.

### 3.3 Windows

1. Install the ST-LINK driver (STSW-LINK009, from st.com).
2. Download [xPack OpenOCD](https://github.com/xpack-dev-tools/openocd-xpack/releases)
   for Windows, extract it, and add its `bin` folder to the `PATH`.
3. Open a new cmd window and check: `openocd --version`.

If the ST-LINK is attached to WSL, detach it first so that Windows sees
it: `usbipd detach --busid <busid>`.

## 4. Flash

Run the script from the extracted folder:

| Linux, WSL | Windows (cmd) | Effect |
|:--|:--|:--|
| `./flash.sh` | `flash.bat` | Check, ask for confirmation if needed, flash |
| `./flash.sh --yes` | `flash.bat /yes` | The same, without the confirmation |
| `./flash.sh --dry-run` | `flash.bat /dry-run` | Check, then print the OpenOCD commands; nothing is flashed |
| `./flash.sh --help` | `flash.bat /?` | Help |

`flash.bat` also accepts `--yes`, `--dry-run` and `--help`.

Each script:

1. checks every file against `SHA256SUMS`, and every line of `images.txt`;
2. checks that OpenOCD is found and is 0.11.0 or later, and prints its
   version;
3. for a standalone application, warns that it replaces any bootloader in
   internal flash and asks `Flash <image>? [y/N]`: only `y` or `yes`
   flashes. Without a console the answer is no: use `--yes` (`/yes`);
4. flashes each line of `images.txt` in order, with
   `openocd <options> -c "program <file> <address> verify reset exit"`.

Each image ends with `** Verified OK **`, then the board restarts on the
new application, and the script prints
`done: every image flashed and verified, the board restarts`.

`flash.bat` can be run from a network or WSL folder
(`\\wsl.localhost\...`): it maps the folder to a drive letter by itself.
To work in that folder in cmd, use `pushd <folder>`, not `cd`.

## 5. Flash with Docker (Linux, WSL)

The flasher image holds OpenOCD and the files of the release: no
download of the zip and no OpenOCD set-up are needed, only Docker Engine
and the USB access.

```bash
docker run --rm -it --device /dev/bus/usb ghcr.io/zkariae/stm32f7508-dk-flasher:<version>
```

- The options of `flash.sh` go after the image name, for example
  `... stm32f7508-dk-flasher:<version> --dry-run`.
- `-it` gives the script a console for the confirmation; without it, add
  `--yes`.
- The tag `latest` is the most recent release; prefer the version you
  were given.
- On WSL, use Docker Engine installed in the distribution, and attach the
  ST-LINK with `usbipd attach --wsl` first (section 3.2).

## 6. Update

1. Download the new release and check it (section 2).
2. Extract it in a new folder, then flash it (section 4 or 5).

Nothing has to be removed first: flashing replaces the previous
application. To go back, flash the previous release the same way.

## 7. Exit codes and troubleshooting

| Code | Meaning | What to do |
|:-:|:--|:--|
| 0 | Done (or dry run done) | — |
| 2 | Unknown option | See `--help` |
| 3 | A file is missing, does not match `SHA256SUMS`, or `images.txt` is wrong | Download and extract the release again; do not edit the files |
| 4 | OpenOCD not found, or older than 0.11.0 | Install or update it (section 3), check `openocd --version` |
| 5 | Not confirmed | Answer `y`, or use `--yes` (`/yes`) |
| 6 | OpenOCD failed | See below, then run the script again: the flash is only complete once every image is verified |

When OpenOCD fails (code 6):

| Message | Cause | Fix |
|:--|:--|:--|
| `open failed` | The ST-LINK is not seen | Check the USB cable (CN14); on WSL, `usbipd attach`; on Windows, detach it from WSL and install the driver |
| `LIBUSB_ERROR_ACCESS` | No right on the USB device | Linux, WSL: `plugdev` group (section 3.1) |
| `Error: init mode failed` | The target does not answer | Unplug and plug the board again, then retry |

Other cases:

- `Permission denied` on `./flash.sh`: run `bash flash.sh`, or
  `chmod +x flash.sh` once.
- `CMD does not support UNC paths as current directories` in cmd: use
  `pushd` instead of `cd` (section 4).

## 8. Limits

- Docker Desktop on Windows does not see a USB device attached to WSL:
  use Docker Engine inside the WSL distribution, or `flash.bat`.
- `flash.bat` cannot tell whether a console is attached: without one, the
  empty answer refuses, so automated use needs `/yes`.
- macOS is not tested.
