#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       package.sh
# \brief      Build the release folder of a tag, its zip and their checksums.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       16/11/2026
#
# \details
#   Package stage of the CD job (cd/README.md section 6.1), also run by hand
#   before the first tag. From the checked-out tag, writes under
#   work/release/ only:
#     stm32f7508-dk-baremetal-<tag>/           the release folder (section 5.2)
#     stm32f7508-dk-baremetal-<tag>.zip        that folder, zipped
#     stm32f7508-dk-baremetal-<tag>.zip.sha256 the SHA-256 of the zip
#   The folder is also the build context of the flasher image. The zip is
#   reproducible: the files get the date of the tagged commit and are zipped
#   in a fixed order, so packaging a tag again gives the same zip.
#   Can be run from any folder: it moves to the repository root. Stops with
#   exit code 1 and a message at the first error, before anything is removed
#   when the tag is wrong.
#
#     cd/scripts/package.sh release-v1.0.0
#
#   RELEASE_APP set in the environment overrides cd/release.mk, for checks.
#
# \section package_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 16/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

die() {
  echo "package.sh: error: $*" >&2
  exit 1
}

if [[ $# -ne 1 || $1 == -* ]]; then
  echo "Usage: cd/scripts/package.sh <release-vX.Y.Z tag>" >&2
  exit 1
fi
tag=$1

cd "$(git rev-parse --show-toplevel)"

####################################################################
# Checks, before anything is written
####################################################################

# The tag is part of the paths below: check it first
[[ $tag =~ ^release-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] ||
  die "$tag is not a release tag: expected release-vX.Y.Z"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "tag $tag not found"
[[ $(git cat-file -t "refs/tags/$tag") == tag ]] ||
  die "$tag is a lightweight tag: a release tag is annotated (git tag -a)"
# The release is made of the checked-out files: they must be the tag's
[[ $(git rev-parse HEAD) == "$(git rev-parse "$tag^{commit}")" ]] ||
  die "HEAD is not the commit of $tag: check out the tag first"
command -v zip >/dev/null || die "zip not found (package zip)"

make_args=(--no-print-directory -f Makefile -f cd/release.mk)
if [[ -n ${RELEASE_APP:-} ]]; then
  make_args+=("RELEASE_APP=$RELEASE_APP")
fi

# Nothing to do after ci/scripts/build.sh; builds the images otherwise
echo "package.sh: make release-build"
make "${make_args[@]}" release-build

####################################################################
# Release folder
####################################################################

out=work/release
name=stm32f7508-dk-baremetal-$tag
dir=$out/$name
zip_file=$name.zip

rm -rf "${dir:?}" "${out:?}/${zip_file:?}" "${out:?}/${zip_file:?}.sha256"
mkdir -p "$dir/images"

echo "package.sh: $dir"
cd/scripts/notes.sh "$tag" >"$dir/RELEASE_NOTES.md"
cp cd/client/README.md "$dir/README.md"
cp cd/client/flash.sh cd/client/flash.bat "$dir/"
make "${make_args[@]}" release-manifest >"$dir/images.txt"
mapfile -t bins < <(make "${make_args[@]}" release-bins)
for bin in "${bins[@]}"; do
  cp "$bin" "$dir/images/"
done

# The same modes on every machine; flash.sh runs as ./flash.sh
find "$dir" -type d -exec chmod 755 {} +
find "$dir" -type f -exec chmod 644 {} +
chmod 755 "$dir/flash.sh"

# Every other file of the folder, listed before SHA256SUMS exists, in a fixed order
(
  cd "$dir"
  mapfile -t files < <(find . -type f -printf '%P\n' | LC_ALL=C sort)
  sha256sum "${files[@]}" >SHA256SUMS
)

####################################################################
# Zip and its checksum
####################################################################

# Reproducible zip: the date of the tagged commit on every entry, in UTC,
# entries in a fixed order, no directory entries, no extra attributes
stamp=$(git log -1 --format=%ct "$tag^{commit}")
find "$dir" -exec touch -h -d "@$stamp" {} +
(
  cd "$out"
  find "$name" -type f | LC_ALL=C sort | TZ=UTC zip -X -D -q "$zip_file" -@
  sha256sum "$zip_file" >"$zip_file.sha256"
)

echo "package.sh: $out/$zip_file"
echo "package.sh: $out/$zip_file.sha256"
echo "package.sh: done"
