#!/bin/sh
set -eu
cd /home/xilinx/sentinel
export XILINX_XRT=/usr
export PYTHONPATH=/home/xilinx/sentinel/ps:${PYTHONPATH:-}
exec /usr/local/share/pynq-venv/bin/python3 -m sentinel.app.monitor "$@"
