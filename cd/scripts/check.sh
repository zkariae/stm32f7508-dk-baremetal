#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       check.sh
# \brief      Check the packaged release of a tag, without the board.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       16/11/2026
#
# \details
#   Check stage of the CD job (cd/README.md section 6.1), also run by hand
#   after package.sh before the first tag. Nothing is published unless it
#   passes. In order:
#      1. the zip matches its .sha256 file;
#      2. the zip holds exactly the layout of section 5.2;
#      3. the zip and the release folder (the image build context) are equal;
#      4. SHA256SUMS passes and covers exactly every other file;
#      5. the binaries are those built from the tag;
#      6. images.txt is the release-manifest of the Makefile and board.mk;
#      7. README.md, flash.sh, flash.bat and RELEASE_NOTES.md are those of
#         cd/client and notes.sh, flash.sh is executable, flash.bat is CRLF;
#      8. the shell scripts pass shellcheck;
#      9. flash.sh --dry-run prints the expected OpenOCD commands;
#     10. the flasher image builds, under its published name, and its
#         flash.sh --dry-run prints the same commands.
#   Never pushes and never flashes: the dry runs only ask OpenOCD for its
#   version, and the container has no USB device. Writes only under
#   work/release/check/, removed once every check passed. Stops with exit
#   code 1 at the first failed check, which it names.
#
#     cd/scripts/check.sh release-v1.0.0
#
#   RELEASE_APP set in the environment overrides cd/release.mk, for checks.
#
# \section check_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 16/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

readonly FLASHER=ghcr.io/zkariae/stm32f7508-dk-flasher

die() {
  echo "check.sh: error: $*" >&2
  exit 1
}

ok() {
  echo "check.sh: $* ok"
}

if [[ $# -ne 1 || $1 == -* ]]; then
  echo "Usage: cd/scripts/check.sh <release-vX.Y.Z tag>" >&2
  exit 1
fi
tag=$1

cd "$(git rev-parse --show-toplevel)"

[[ $tag =~ ^release-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] ||
  die "$tag is not a release tag: expected release-vX.Y.Z"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "tag $tag not found"
[[ $(git rev-parse HEAD) == "$(git rev-parse "$tag^{commit}")" ]] ||
  die "HEAD is not the commit of $tag: check out the tag first"
version=${tag#release-v}

make_args=(--no-print-directory -f Makefile -f cd/release.mk)
if [[ -n ${RELEASE_APP:-} ]]; then
  make_args+=("RELEASE_APP=$RELEASE_APP")
fi
manifest=$(make "${make_args[@]}" release-manifest)
mapfile -t bins < <(make "${make_args[@]}" release-bins)

out=work/release
name=stm32f7508-dk-baremetal-$tag
dir=$out/$name
zip_file=$out/$name.zip
work=$out/check
ext=$work/$name

# The OpenOCD commands of images.txt, in the form of board_flash ("make <app>-flash")
expected_commands=$(
  while read -r _ file _ address options; do
    echo "openocd $options -c \"program $file $address verify reset exit\""
  done < <(grep -v '^#' <<<"$manifest")
)

# $1: output of flash.sh --dry-run. Its OpenOCD commands must be the expected ones.
same_commands() {
  local got
  got=$(grep '^openocd ' <<<"$1" || true)
  if [[ $got != "$expected_commands" ]]; then
    printf 'expected:\n%s\ngot:\n%s\n' "$expected_commands" "$got" >&2
    return 1
  fi
}

####################################################################
# 1 to 4: the zip, its layout, the folder, SHA256SUMS
####################################################################

[[ -f $zip_file && -f $zip_file.sha256 ]] ||
  die "1 zip: $zip_file or its .sha256 not found: run cd/scripts/package.sh $tag first"
(cd "$out" && sha256sum -c --strict --quiet "$name.zip.sha256") ||
  die "1 zip: $zip_file does not match its .sha256"
ok "1 zip"

expected_layout=$(
  {
    for file in README.md RELEASE_NOTES.md SHA256SUMS flash.bat flash.sh images.txt; do
      echo "$name/$file"
    done
    for bin in "${bins[@]}"; do
      echo "$name/images/${bin##*/}"
    done
  } | LC_ALL=C sort
)
layout=$(unzip -Z1 "$zip_file" | LC_ALL=C sort)
if [[ $layout != "$expected_layout" ]]; then
  diff <(echo "$expected_layout") <(echo "$layout") >&2 || true
  die "2 layout: the zip does not hold exactly the release files (< expected, > zip)"
fi
ok "2 layout"

[[ -d $dir ]] || die "3 folder: $dir not found"
rm -rf "${work:?}"
mkdir -p "$work"
unzip -q "$zip_file" -d "$work"
diff -r "$dir" "$ext" >&2 || die "3 folder: $dir and the zip differ"
ok "3 folder"

(cd "$ext" && sha256sum -c --strict --quiet SHA256SUMS) || die "4 SHA256SUMS: a file does not match"
listed=$(while read -r _ path; do echo "${path#\*}"; done <"$ext/SHA256SUMS" | LC_ALL=C sort)
others=$(cd "$ext" && find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort)
[[ $listed == "$others" ]] || die "4 SHA256SUMS: does not list exactly every other file"
ok "4 SHA256SUMS"

####################################################################
# 5 to 7: the content against the repository
####################################################################

for bin in "${bins[@]}"; do
  cmp -s "$bin" "$ext/images/${bin##*/}" || die "5 binaries: images/${bin##*/} differs from $bin"
done
ok "5 binaries"

diff <(echo "$manifest") "$ext/images.txt" >&2 ||
  die "6 images.txt: differs from release-manifest (< make, > zip)"
ok "6 images.txt"

cmp -s cd/client/README.md "$ext/README.md" || die "7 files: README.md differs from cd/client/README.md"
cmp -s cd/client/flash.sh "$ext/flash.sh" || die "7 files: flash.sh differs from cd/client/flash.sh"
cmp -s cd/client/flash.bat "$ext/flash.bat" || die "7 files: flash.bat differs from cd/client/flash.bat"
notes=$(cd/scripts/notes.sh "$tag") || die "7 files: notes.sh failed"
cmp -s <(echo "$notes") "$ext/RELEASE_NOTES.md" || die "7 files: RELEASE_NOTES.md differs from notes.sh $tag"
[[ -x $ext/flash.sh ]] || die "7 files: flash.sh is not executable in the zip"
if grep -q -v $'\r$' "$ext/flash.bat"; then
  die "7 files: flash.bat has lines without CRLF"
fi
ok "7 files"

####################################################################
# 8: shellcheck
####################################################################

command -v shellcheck >/dev/null || die "8 shellcheck: not found (package shellcheck)"
shellcheck cd/client/flash.sh cd/scripts/*.sh || die "8 shellcheck: warnings above"
ok "8 shellcheck"

####################################################################
# 9 and 10: dry runs, from the folder and in the flasher image
####################################################################

run=$("$ext/flash.sh" --dry-run 2>&1) || {
  echo "$run" >&2
  die "9 dry run: flash.sh --dry-run failed"
}
same_commands "$run" || die "9 dry run: unexpected OpenOCD commands"
ok "9 dry run"

command -v docker >/dev/null || die "10 image: docker not found"
image=$FLASHER:$version
docker build -f cd/docker/Dockerfile --build-arg "VERSION=$version" -t "$image" "$dir" ||
  die "10 image: docker build failed"
label=$(docker inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$image")
[[ $label == "$version" ]] || die "10 image: version label is '$label', expected $version"
run=$(docker run --rm "$image" --dry-run 2>&1) || {
  echo "$run" >&2
  die "10 image: flash.sh --dry-run failed in $image"
}
same_commands "$run" || die "10 image: unexpected OpenOCD commands in $image"
ok "10 image"

rm -rf "${work:?}"
echo "check.sh: all checks passed; $image built, not pushed"
