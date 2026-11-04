#!/bin/sh
set -u
cd /home/xilinx/sentinel
tar -xzf third_party/noos_rf_sources.tar.gz -C third_party/no-OS || exit 1
make -C ps/libad9361_pynq -j2 >logs/P5.3_noos_compile.log 2>&1
result=$?
printf '%s\n' "$result" >logs/P5.3_noos_compile_exit.txt
exit "$result"
