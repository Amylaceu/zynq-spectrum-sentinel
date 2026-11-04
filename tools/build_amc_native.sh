#!/bin/sh
# CPU-only optional library. Run ON THE TARGET BOARD after copying the source.
# Usage: sh tools/build_amc_native.sh /absolute/output/libsentinel_gardner.so
set -eu
if [ "$#" -ne 1 ]; then
    echo 'Usage: build_amc_native.sh /absolute/output/libsentinel_gardner.so' >&2
    exit 2
fi
case "$1" in /*) ;; *) echo 'Output must be an absolute path' >&2; exit 2;; esac
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=$1
if [ -e "$destination" ]; then
    echo 'Refusing to replace an existing library; choose a new output path' >&2
    exit 1
fi
mkdir -p -- "$(dirname -- "$destination")"
temporary=$(mktemp "${destination}.tmp.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT HUP INT TERM
gcc -std=c99 -O2 -fPIC -shared -fno-fast-math -ffp-contract=off \
    -Wall -Wextra -Werror "$repo/src/ps/sentinel/amc/native/gardner.c" \
    -o "$temporary" -lm
# A hard link publishes atomically and fails if another writer created it.
ln -- "$temporary" "$destination"
sha256sum -- "$destination"
