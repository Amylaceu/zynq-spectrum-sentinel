#!/bin/sh
set -eu
case "${1:-1}" in 1|2|3) attempt="${1:-1}" ;; *) exit 2 ;; esac
cd /home/xilinx/sentinel
nohup env XILINX_XRT=/usr PYTHONPATH=/home/xilinx/sentinel/ps \
 /usr/local/share/pynq-venv/bin/python3 scripts/capture_fm_band.py --attempt "$attempt" \
 >"logs/P5.3_fm_scan_round${attempt}.log" 2>&1 </dev/null &
echo "$!"
