#!/bin/bash
# Build a real installable development ISO from the locked, patched checkouts.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
mkdir -p out
exec > >(tee "$ROOT/out/iso-build.log") 2>&1
printf 'Starting real Omarchy ISO build at %s\n' "$(date -u +%FT%TZ)"

python3 scripts/prepare-sources.py
command -v docker >/dev/null
command -v jq >/dev/null
command -v xorriso >/dev/null

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
  "${DOCKER[@]}" info >/dev/null
fi

export OMARCHY_BUILD_IMAGE
export OMARCHY_NODE_VERSION
export OMARCHY_NODE_SHA256
export SOURCE_DATE_EPOCH
OMARCHY_BUILD_IMAGE=$(jq -er '.builder_image' config/sources.lock.json)
OMARCHY_NODE_VERSION=$(jq -er '.node.version' config/sources.lock.json)
OMARCHY_NODE_SHA256=$(jq -er '.node.sha256' config/sources.lock.json)
[[ $OMARCHY_BUILD_IMAGE =~ @sha256:[0-9a-f]{64}$ ]]
SOURCE_DATE_EPOCH=$(git -C sources/omarchy-iso show -s --format=%ct HEAD)

run_identity="${GITHUB_RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}-${GITHUB_RUN_ATTEMPT:-1}"
[[ $run_identity =~ ^[A-Za-z0-9_-]+$ ]]
export OMARCHY_BUILD_OUTPUT="$ROOT/out/build-$run_identity"
mkdir "$OMARCHY_BUILD_OUTPUT"

"${DOCKER[@]}" pull "$OMARCHY_BUILD_IMAGE"
"${DOCKER[@]}" image inspect "$OMARCHY_BUILD_IMAGE" > "$OMARCHY_BUILD_OUTPUT/builder-image.json"

# Save all effective source files, including overlays; omit Git object stores.
# Rebuilding uses the locked clones plus tracked patches, not this inspection archive.
if [[ ${INCLUDE_SOURCE_ARCHIVE:-true} == true ]]; then
  tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    -I 'zstd -T0 -3' -cf out/effective-sources.tar.zst \
    sources config patches overlays scripts
fi

(
  cd sources/omarchy-iso
  ./bin/omarchy-iso-make \
    --local-source "$ROOT/sources/omarchy" "$ROOT/sources/omarchy-pkgs" \
    --keep-pkg-cache --no-cache --no-boot-offer
)

shopt -s nullglob
isos=("$OMARCHY_BUILD_OUTPUT"/*.iso)
if ((${#isos[@]} != 1)) || [[ ! -s ${isos[0]} ]]; then
  printf 'Expected exactly one non-empty ISO in %s\n' "$OMARCHY_BUILD_OUTPUT" >&2
  exit 1
fi
iso=${isos[0]}
# Inspect the actual ISO's BIOS/UEFI boot catalogue, not a mock boot result.
xorriso -indev "$iso" -report_el_torito plain > "$OMARCHY_BUILD_OUTPUT/boot-catalog.txt" 2>&1
grep -q 'El Torito boot img' "$OMARCHY_BUILD_OUTPUT/boot-catalog.txt"
(
  cd "$OMARCHY_BUILD_OUTPUT"
  sha256sum -- "$(basename "$iso")" > "$(basename "$iso").sha256"
)
python3 scripts/write-build-manifest.py "$iso"
printf 'ISO build completed: %s\n' "$iso"
