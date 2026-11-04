#!/bin/sh
# Update only the installed helper after exact old/new SHA256 verification.
# Usage: sudo sh update_x0_admin.sh <old-sha256> <new-sha256>
set -eu
[ "$(id -u)" = 0 ] || { echo "Root required" >&2; exit 1; }
[ "$#" = 2 ] || { echo "Expected old and new SHA256" >&2; exit 1; }
for digest in "$1" "$2"; do
    [ "${#digest}" = 64 ] || exit 1
    case "$digest" in *[!0-9a-f]*) exit 1;; esac
done
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
src="$base/zss_n4_admin.py"
helper=/usr/local/sbin/zss-n4-admin
actual=$(sha256sum "$helper" | cut -d " " -f 1)
new=$(sha256sum "$src" | cut -d " " -f 1)
[ "$new" = "$2" ] || { echo "New helper hash mismatch" >&2; exit 1; }
if [ "$actual" = "$2" ]; then echo X0_ADMIN_ALREADY_UPDATED; exit 0; fi
[ "$actual" = "$1" ] || { echo "Installed helper changed; refusing overwrite" >&2; exit 1; }
if pgrep -f "[s]entinel.app.monitor|[b]ench_lcd.py|[s]elftest_v1" >/dev/null; then
    echo "Active board task; wait for it to finish" >&2; exit 1
fi
/usr/bin/python3 -I -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$src"
backup="${helper}.pre-x0-${1}"
if [ -e "$backup" ]; then
    [ "$(sha256sum "$backup" | cut -d " " -f 1)" = "$1" ] || exit 1
else
    install -o root -g root -m 0755 "$helper" "$backup"
fi
temporary=$(mktemp /usr/local/sbin/zss-n4-admin.x0.XXXXXX)
trap 'rm -f -- "$temporary"' EXIT HUP INT TERM
install -o root -g root -m 0755 "$src" "$temporary"
[ "$(sha256sum "$temporary" | cut -d " " -f 1)" = "$2" ] || exit 1
mv -f -- "$temporary" "$helper"
"$helper" health
echo X0_ADMIN_UPDATED_NO_RF_OPERATION
