#!/bin/sh
# No startup service is installed. Run explicitly with sudo on the PYNQ board.
set -eu
release_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec /usr/local/share/pynq-venv/bin/python3 -I "$release_root/scripts/release_entry.py" "$@"
