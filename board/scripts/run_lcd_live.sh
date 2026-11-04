#!/bin/sh
set -eu
cd /home/xilinx/sentinel
nohup env XILINX_XRT=/usr PYTHONPATH=/home/xilinx/sentinel/ps \
 /usr/local/share/pynq-venv/bin/python3 scripts/lcd_live_receive.py --seconds 900 \
 >logs/P5.4_lcd_live_board.log 2>&1 </dev/null &
echo "$!"
