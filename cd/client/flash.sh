#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       flash.sh
# \brief      Check a release folder, then flash its images with the ST-LINK.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       15/11/2026
#
# \details
#   Delivered at the root of the release folder (cd/README.md section 5.3),
#   for Linux and WSL, and the entry point of the flasher image. Checks every
#   file against SHA256SUMS and every line of images.txt, then flashes the
#   images in the order of images.txt with the same OpenOCD command as
#   "make <app>-flash": a bootloader pair is always flashed whole, QSPI
#   application first. A standalone image replaces any bootloader in
#   internal flash, so it is flashed only once confirmed. Nothing is flashed
#   unless every check passed.
#
#     ./flash.sh             check, confirm a standalone image, flash
#     ./flash.sh --yes       the same, without the confirmation
#     ./flash.sh --dry-run   check, then print the OpenOCD commands only
#
#   Exit codes: 0 done, 2 usage error, 3 integrity error, 4 OpenOCD missing
#   or older than 0.11.0, 5 not confirmed, 6 flash failed.
#
# \section flash_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 15/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_INTEGRITY=3
readonly EXIT_OPENOCD=4
readonly EXIT_REFUSED=5
readonly EXIT_FLASH=6

# First version with the stmqspi driver that a QSPI image needs
readonly OPENOCD_MIN=0.11.0

usage() {
  cat <<'EOF'
Usage: ./flash.sh [--yes] [--dry-run] [--help]

Checks the release files against SHA256SUMS, then flashes the images of
images.txt to the STM32F7508-DK with OpenOCD and the ST-LINK.

  --yes       do not ask before replacing a bootloader in internal flash
  --dry-run   run the checks, print the OpenOCD commands, flash nothing
  --help      print this help

Exit codes: 0 done, 2 usage error, 3 integrity error, 4 OpenOCD missing or
older than 0.11.0, 5 not confirmed, 6 flash failed.
EOF
}

# $1: exit code, then the message
die() {
  local code=$1
  shift
  echo "flash.sh: error: $*" >&2
  exit "$code"
}

info() {
  echo "flash.sh: $*"
}

####################################################################
# Options
####################################################################

yes=0
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --yes) yes=1 ;;
    --dry-run) dry_run=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "flash.sh: error: unknown option: $arg" >&2
      usage >&2
      exit "$EXIT_USAGE"
      ;;
  esac
done

# The paths of SHA256SUMS and images.txt are relative to the release folder
cd "$(dirname "${BASH_SOURCE[0]}")"

####################################################################
# Integrity
####################################################################

command -v sha256sum >/dev/null || die "$EXIT_INTEGRITY" "sha256sum not found (package coreutils)"
for f in SHA256SUMS images.txt; do
  [[ -f $f ]] || die "$EXIT_INTEGRITY" "$f not found: run flash.sh from the extracted release folder"
done

info "checking SHA256SUMS"
sha256sum -c --strict --quiet SHA256SUMS ||
  die "$EXIT_INTEGRITY" "a file does not match SHA256SUMS: download the release again; nothing flashed"

# Files covered by SHA256SUMS: "<sha256>  <path>", "*" before the path in binary mode
declare -A summed=()
while read -r _ path; do
  summed[${path#\*}]=1
done <SHA256SUMS
[[ -n ${summed[images.txt]:-} ]] || die "$EXIT_INTEGRITY" "images.txt is not listed in SHA256SUMS"

# images.txt: "image file memory address openocd-options", in flashing order
names=()
files=()
memories=()
addresses=()
options=()
n=0
while IFS= read -r line || [[ -n $line ]]; do
  n=$((n + 1))
  if [[ -z ${line//[[:space:]]/} || $line == \#* ]]; then
    continue
  fi
  read -r name file memory address rest <<<"$line"
  where="images.txt line $n"
  [[ -n ${rest:-} ]] || die "$EXIT_INTEGRITY" "$where: expected image, file, memory, address, OpenOCD options"
  [[ $file == images/* && $file != *..* ]] || die "$EXIT_INTEGRITY" "$where: $file is not in images/"
  [[ -n ${summed[$file]:-} ]] || die "$EXIT_INTEGRITY" "$where: $file is not listed in SHA256SUMS"
  [[ $memory == flash || $memory == qspi ]] || die "$EXIT_INTEGRITY" "$where: unknown memory $memory"
  [[ $address =~ ^0x[0-9A-Fa-f]{1,8}$ ]] || die "$EXIT_INTEGRITY" "$where: bad address $address"
  names+=("$name")
  files+=("$file")
  memories+=("$memory")
  addresses+=("$address")
  options+=("$rest")
done <images.txt
((${#files[@]} > 0)) || die "$EXIT_INTEGRITY" "images.txt lists no image"
info "files match SHA256SUMS, images.txt lists ${#files[@]} image(s)"

####################################################################
# OpenOCD
####################################################################

# A dry run flashes nothing: a missing or old OpenOCD is only reported
openocd_problem() {
  if ((dry_run)); then
    echo "flash.sh: warning: $*" >&2
  else
    die "$EXIT_OPENOCD" "$*"
  fi
}

if command -v openocd >/dev/null; then
  version_text=$(openocd --version 2>&1 || true)
  version_text=${version_text%%$'\n'*}
  info "$version_text"
  if [[ $version_text =~ ([0-9]+\.[0-9]+\.[0-9]+) ]]; then
    lowest=$(printf '%s\n' "$OPENOCD_MIN" "${BASH_REMATCH[1]}" | sort -V)
    [[ ${lowest%%$'\n'*} == "$OPENOCD_MIN" ]] ||
      openocd_problem "OpenOCD ${BASH_REMATCH[1]} is older than $OPENOCD_MIN"
  else
    openocd_problem "cannot read the OpenOCD version"
  fi
else
  openocd_problem "openocd not found: install OpenOCD $OPENOCD_MIN or later (see README.md)"
fi

####################################################################
# Confirmation
####################################################################

if ((${#files[@]} == 1)) && [[ ${memories[0]} == flash ]]; then
  echo "WARNING: ${names[0]} is a standalone image: it replaces any bootloader in internal flash."
  if ((!yes && !dry_run)); then
    [[ -t 0 ]] || die "$EXIT_REFUSED" "no terminal to confirm: run again with --yes; nothing flashed"
    read -r -p "Flash ${names[0]}? [y/N] " answer || answer=""
    case "$answer" in
      y | Y | yes | YES) ;;
      *) die "$EXIT_REFUSED" "not confirmed; nothing flashed" ;;
    esac
  fi
else
  info "bootloader pair: flashed whole, in the order of images.txt"
fi

####################################################################
# Flash
####################################################################

for i in "${!files[@]}"; do
  program="program ${files[i]} ${addresses[i]} verify reset exit"
  if ((dry_run)); then
    echo "openocd ${options[i]} -c \"$program\""
    continue
  fi
  read -r -a args <<<"${options[i]}"
  info "flashing ${names[i]} (${memories[i]}, ${addresses[i]})"
  openocd "${args[@]}" -c "$program" ||
    die "$EXIT_FLASH" "OpenOCD failed on ${names[i]}: check the ST-LINK connection, then run flash.sh again"
done

if ((dry_run)); then
  info "dry run: nothing flashed"
else
  info "done: every image flashed and verified, the board restarts"
fi
