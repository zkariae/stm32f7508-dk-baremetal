#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       publish.sh
# \brief      Push the flasher image to GHCR and publish the GitHub Release of a tag.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       16/11/2026
#
# \details
#   Publish stage of the CD job (cd/README.md section 6.1), run after
#   package.sh and check.sh. In order:
#     1. guards: tag format, annotated tag, HEAD = tag commit, zip and its
#        .sha256, release notes, flasher image built by check.sh, tag on
#        origin pointing to the same commit (so the API never creates it);
#     2. latest: moved only when no higher annotated release-vX.Y.Z tag is
#        on origin;
#     3. GHCR: push of ghcr.io/zkariae/stm32f7508-dk-flasher:X.Y.Z, and
#        :latest when this release is the highest;
#     4. GitHub Release: created as a draft, assets uploaded, then published,
#        so a client never sees it incomplete. When it already exists (Build
#        Now on an existing tag), its notes are updated and its two assets
#        replaced by the same files.
#   Never pushes a tag or a branch, never flashes. The tokens come from the
#   environment (withCredentials in cd/Jenkinsfile) and never reach a
#   command line or the output: docker login reads stdin, curl reads its
#   header from a file descriptor, and the Docker credentials live in a
#   temporary DOCKER_CONFIG removed on exit. Stops with exit code 1 at the
#   first error.
#
#     GHCR_USER=... GHCR_TOKEN=... GITHUB_TOKEN=... cd/scripts/publish.sh release-v1.0.0
#     cd/scripts/publish.sh --dry-run release-v1.0.0
#
#   --dry-run runs every guard and the latest decision, needs no token, and
#   prints what would be published without writing anything.
#
# \section publish_sh_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 16/11/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

set -euo pipefail

readonly FLASHER=ghcr.io/zkariae/stm32f7508-dk-flasher
readonly REPO=zkariae/stm32f7508-dk-baremetal
readonly API=https://api.github.com/repos/$REPO
readonly UPLOADS=https://uploads.github.com/repos/$REPO
readonly TAG_RE='^release-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'

die() {
  echo "publish.sh: error: $*" >&2
  exit 1
}

say() {
  echo "publish.sh: $*"
}

usage() {
  echo "Usage: cd/scripts/publish.sh [--dry-run] <release-vX.Y.Z tag>" >&2
  exit 1
}

dry_run=false
if [[ ${1:-} == --dry-run ]]; then
  dry_run=true
  shift
fi
if [[ $# -ne 1 || $1 == -* ]]; then
  usage
fi
tag=$1

cd "$(git rev-parse --show-toplevel)"

####################################################################
# 1. Guards: nothing is written before they all pass
####################################################################

[[ $tag =~ $TAG_RE ]] || die "$tag is not a release tag: expected release-vX.Y.Z"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "tag $tag not found"
[[ $(git cat-file -t "$tag") == tag ]] || die "$tag is a lightweight tag: a release tag is annotated"
commit=$(git rev-parse "$tag^{commit}")
[[ $(git rev-parse HEAD) == "$commit" ]] || die "HEAD is not the commit of $tag: check out the tag first"
version=${tag#release-v}

out=work/release
name=stm32f7508-dk-baremetal-$tag
zip_name=$name.zip
zip_file=$out/$zip_name
notes=$out/$name/RELEASE_NOTES.md
image=$FLASHER:$version

[[ -f $zip_file && -f $zip_file.sha256 ]] ||
  die "$zip_file or its .sha256 not found: run cd/scripts/package.sh and check.sh $tag first"
(cd "$out" && sha256sum -c --strict --quiet "$zip_name.sha256") ||
  die "$zip_file does not match its .sha256"
[[ -f $notes ]] || die "$notes not found: run cd/scripts/package.sh $tag first"
command -v docker >/dev/null || die "docker not found"
docker image inspect "$image" >/dev/null 2>&1 ||
  die "image $image not found: run cd/scripts/check.sh $tag first"

remote_tags=$(git ls-remote --tags origin) || die "cannot read the tags of origin"
remote_commit=$(awk -v ref="refs/tags/$tag^{}" '$2 == ref { print $1 }' <<<"$remote_tags")
[[ -n $remote_commit ]] ||
  die "$tag is not an annotated tag on origin: the developer pushes it before the delivery"
[[ $remote_commit == "$commit" ]] ||
  die "$tag points to $remote_commit on origin, not to the built commit $commit"
say "guards ok: $tag on origin points to $commit"

if ! $dry_run; then
  for var in GHCR_USER GHCR_TOKEN GITHUB_TOKEN; do
    [[ -n ${!var:-} ]] || die "$var is not set (withCredentials in cd/Jenkinsfile)"
  done
fi

####################################################################
# 2. latest: only for the highest release tag on origin
####################################################################

# Annotated tags only (peeled ^{} line): a lightweight tag is never delivered.
highest=$(
  awk '{ print $2 }' <<<"$remote_tags" |
    sed -n 's|^refs/tags/\(release-v[^^]*\)^{}$|\1|p' |
    grep -E "$TAG_RE" |
    sed 's/^release-v//' |
    sort -V |
    tail -n 1
)
if [[ $highest == "$version" ]]; then
  latest=true
  say "latest: $version is the highest release, latest moves to it"
else
  latest=false
  say "latest: $highest is higher than $version, latest stays where it is"
fi

if $dry_run; then
  say "dry run: would push $image"
  if $latest; then
    say "dry run: would push $FLASHER:latest"
  fi
  say "dry run: would create or update the GitHub Release $tag (make_latest=$latest)"
  say "dry run: with $notes, $zip_name and $zip_name.sha256"
  exit 0
fi

####################################################################
# 3. GHCR
####################################################################

DOCKER_CONFIG=$(mktemp -d)
export DOCKER_CONFIG
cleanup() {
  docker logout ghcr.io >/dev/null 2>&1 || true
  rm -rf "${DOCKER_CONFIG:?}"
}
trap cleanup EXIT

printf '%s' "$GHCR_TOKEN" | docker login ghcr.io --username "$GHCR_USER" --password-stdin >/dev/null ||
  die "docker login ghcr.io failed: check the credential ghcr-zkariae"
docker push "$image" || die "docker push $image failed"
say "pushed $image"
if $latest; then
  docker tag "$image" "$FLASHER:latest"
  docker push "$FLASHER:latest" || die "docker push $FLASHER:latest failed"
  say "pushed $FLASHER:latest"
fi

####################################################################
# 4. GitHub Release
####################################################################

# $1: method, $2: URL, then extra curl options. Prints the response body, or
# the error body of GitHub on stderr. The token is read by curl from a file
# descriptor, never from its arguments.
api() {
  local method=$1 url=$2 response
  shift 2
  if ! response=$(
    curl -sS --fail-with-body -X "$method" \
      -H @<(printf 'Authorization: Bearer %s\n' "$GITHUB_TOKEN") \
      -H 'Accept: application/vnd.github+json' \
      -H 'X-GitHub-Api-Version: 2022-11-28' \
      "$@" "$url"
  ); then
    echo "$response" >&2
    return 1
  fi
  echo "$response"
}

# $1: draft (true|false), $2: make_latest (true|false|""). Prints the JSON body.
release_json() {
  python3 -I - "$tag" "$notes" "$1" "$2" <<'EOF'
import json
import sys

tag, notes, draft, latest = sys.argv[1:]
with open(notes, encoding="utf-8") as f:
    data = {"tag_name": tag, "name": tag, "body": f.read(), "draft": draft == "true"}
if latest:
    data["make_latest"] = latest
print(json.dumps(data))
EOF
}

# stdin: JSON. $1: Python expression on `data`. Prints its result.
json_get() {
  python3 -I -c "import json, sys; data = json.load(sys.stdin); print($1)"
}

# Drafts are not found by /releases/tags/<tag>: look for the tag in the list.
releases=$(api GET "$API/releases?per_page=100") || die "cannot list the releases of $REPO"
found=$(json_get "next((r['id'] for r in data if r['tag_name'] == '$tag'), '')" <<<"$releases")

if [[ -z $found ]]; then
  created=$(release_json true "" | api POST "$API/releases" --data-binary @-) ||
    die "cannot create the draft release $tag"
  id=$(json_get "data['id']" <<<"$created")
  say "draft release $tag created (id $id)"
else
  id=$found
  say "release $tag already exists (id $id): notes and assets are replaced"
  release=$(api GET "$API/releases/$id") || die "cannot read the release $id"
  while read -r asset_id asset_name; do
    if [[ $asset_name == "$zip_name" || $asset_name == "$zip_name.sha256" ]]; then
      api DELETE "$API/releases/assets/$asset_id" >/dev/null || die "cannot delete the asset $asset_name"
      say "old asset $asset_name deleted"
    fi
  done < <(json_get "'\n'.join(f\"{a['id']} {a['name']}\" for a in data['assets'])" <<<"$release")
fi

# $1: file, $2: content type
upload() {
  api POST "$UPLOADS/releases/$id/assets?name=${1##*/}" \
    -H "Content-Type: $2" --data-binary "@$1" >/dev/null || die "cannot upload ${1##*/}"
  say "asset ${1##*/} uploaded"
}
upload "$zip_file" application/zip
upload "$zip_file.sha256" text/plain

published=$(release_json false "$latest" | api PATCH "$API/releases/$id" --data-binary @-) ||
  die "cannot publish the release $tag"
url=$(json_get "data['html_url']" <<<"$published")

if $latest; then
  say "$tag published: $image and latest, release $url"
else
  say "$tag published: $image, release $url"
fi
