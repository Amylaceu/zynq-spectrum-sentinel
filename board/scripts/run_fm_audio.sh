#!/bin/sh
set -eu
case "${1:-90000000}" in 90000000|95800000|100900000) station="${1:-90000000}" ;; *) exit 2 ;; esac
case "${2:-1}" in 1|2|3) attempt="${2:-1}" ;; *) exit 2 ;; esac
case "${3:-4}" in 4|8|16) blocks="${3:-4}" ;; *) exit 2 ;; esac
cd /home/xilinx/sentinel
nohup env XILINX_XRT=/usr PYTHONPATH=/home/xilinx/sentinel/ps \
 /usr/local/share/pynq-venv/bin/python3 scripts/capture_fm_audio.py --station "$station" --attempt "$attempt" --blocks "$blocks" \
 >"logs/P5.3_fm_audio_${station}_round${attempt}.log" 2>&1 </dev/null &
echo "$!"
