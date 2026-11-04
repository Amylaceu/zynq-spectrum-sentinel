#!/bin/sh
# Run once interactively as root. Does not load an overlay or enable RF.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run: sudo sh /home/xilinx/sentinel/setup/install_n4_admin.sh' >&2; exit 1; }
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/zss_n4_admin.py
test -f "$src"
test -x /usr/local/share/pynq-venv/bin/python3
helper=/usr/local/sbin/zss-n4-admin
policy=/etc/sudoers.d/zss-n4-admin
# Stop instead of overwriting an existing administrator configuration.
if [ -e "$helper" ] || [ -e "$policy" ]; then
    echo 'Existing N4 admin installation found; inspect before reinstalling.' >&2
    exit 1
fi
/usr/bin/python3 -I -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$src"
temporary=$(mktemp -d /tmp/zss-n4-admin.XXXXXX)
trap 'rm -f -- "$temporary/policy"; rmdir -- "$temporary"' EXIT HUP INT TERM
printf '%s\n' 'xilinx ALL=(root) NOPASSWD: /usr/local/sbin/zss-n4-admin' > "$temporary/policy"
/usr/sbin/visudo -cf "$temporary/policy"
install -o root -g root -m 0755 "$src" "$helper"
install -o root -g root -m 0440 "$temporary/policy" "$policy"
if ! /usr/sbin/visudo -c; then
    rm -f -- "$policy" "$helper"
    echo 'Sudo configuration check failed; the new entries were removed.' >&2
    exit 1
fi
"$helper" health
echo 'N4_ADMIN_INSTALLED (no FPGA/RF operation was performed)'
