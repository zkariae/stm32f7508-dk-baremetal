#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       notes.sh
# \brief      Write the release notes of a release tag.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       16/11/2026
#
# \details
#   Prints RELEASE_NOTES.md (cd/README.md section 5.4), also the text of
#   the GitHub Release, on the standard output:
#     1. the message of the annotated tag;
#     2. the pull requests merged since the previous release-v* tag, read
#        from the merge commits ("Merge pull request #<n> from ...", the
#        title on the next line), with no call to the GitHub API;
#     3. the delivered application of cd/release.mk, its mode and the
#        SHA-256 of each image, from the binaries already built;
#     4. the flasher image and its tags.
#   Run by package.sh, and by hand before the first tag. Can be run from any
#   folder: it moves to the repository root. Stops with exit code 1 and a
#   message when the tag is not an annotated release-vX.Y.Z tag, or when a
#   binary is missing.
#
#     cd/scripts/notes.sh release-v1.0.0 > RELEASE_NOTES.md
#
#   RELEASE_APP set in the environment overrides cd/release.mk, for checks.
#
# \section notes_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 16/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

readonly FLASHER=ghcr.io/zkariae/stm32f7508-dk-flasher

die() {
  echo "notes.sh: error: $*" >&2
  exit 1
}

if [[ $# -ne 1 || $1 == -* ]]; then
  echo "Usage: cd/scripts/notes.sh <release-vX.Y.Z tag>" >&2
  exit 1
fi
tag=$1

cd "$(git rev-parse --show-toplevel)"

####################################################################
# Tag
####################################################################

# X, Y and Z decimal without leading zeros (CD2)
[[ $tag =~ ^release-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] ||
  die "$tag is not a release tag: expected release-vX.Y.Z"
version=${tag#release-v}
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "tag $tag not found"
# The message of an annotated tag is the summary of the release
[[ $(git cat-file -t "refs/tags/$tag") == tag ]] ||
  die "$tag is a lightweight tag: a release tag is annotated (git tag -a)"
message=$(git tag -l --format='%(contents)' "$tag")
commit=$(git rev-parse --short=7 "$tag^{commit}")

# The nearest release tag before this one, none for the first release
previous=$(git describe --tags --abbrev=0 --match 'release-v*' "$tag^{commit}^" 2>/dev/null || true)

####################################################################
# Application, from cd/release.mk
####################################################################

make_args=(--no-print-directory -f Makefile -f cd/release.mk)
if [[ -n ${RELEASE_APP:-} ]]; then
  make_args+=("RELEASE_APP=$RELEASE_APP")
fi
app=$(make "${make_args[@]}" release-app)
mapfile -t lines < <(make "${make_args[@]}" release-manifest | grep -v '^#')
mapfile -t bins < <(make "${make_args[@]}" release-bins)
((${#lines[@]} > 0 && ${#lines[@]} == ${#bins[@]})) ||
  die "release-manifest and release-bins disagree for $app"
for bin in "${bins[@]}"; do
  [[ -f $bin ]] || die "$bin not found: run make -f Makefile -f cd/release.mk release-build first"
done

read -r _ _ first_memory _ <<<"${lines[0]}"
if ((${#lines[@]} == 1)) && [[ $first_memory == flash ]]; then
  mode="standalone, internal flash: it replaces any bootloader"
else
  mode="bootloader pair, flashed whole, QSPI application first"
fi

####################################################################
# Notes
####################################################################

echo "# stm32f7508-dk-baremetal $tag"
echo
echo "$message"
echo
echo "Built from commit $commit."
echo
echo "## Changes"
echo
if [[ -z $previous ]]; then
  echo "First release: there is no earlier release-v tag."
else
  echo "Pull requests merged since $previous:"
  echo
  count=0
  # One record per merge commit: subject, unit separator, body, record separator
  while IFS=$'\x1f' read -r -d $'\x1e' subject body; do
    subject=${subject#$'\n'}
    if [[ $subject =~ ^Merge\ pull\ request\ \#([0-9]+)\  ]]; then
      title=${body%%$'\n'*}
      echo "- #${BASH_REMATCH[1]} ${title:-(no title)}"
      count=$((count + 1))
    fi
  done < <(git log --merges --format='%s%x1f%b%x1e' "$previous..$tag")
  if ((count == 0)); then
    echo "- No pull request."
  fi
fi
echo
echo "## Delivered application"
echo
echo "\`$app\`: $mode. Flash it with \`flash.sh\` or \`flash.bat\` (README.md)."
echo
echo "| Image | Memory | Address | SHA-256 |"
echo "|:--|:--|:--|:--|"
for i in "${!lines[@]}"; do
  read -r image _ memory address _ <<<"${lines[i]}"
  read -r sum _ < <(sha256sum "${bins[i]}")
  echo "| \`$image\` | $memory | $address | \`$sum\` |"
done
echo
echo "## Flasher image"
echo
echo "\`$FLASHER:$version\`, also tagged \`latest\` when this is the newest release:"
echo
echo '```bash'
echo "docker run --rm -it --device /dev/bus/usb $FLASHER:$version"
echo '```'
