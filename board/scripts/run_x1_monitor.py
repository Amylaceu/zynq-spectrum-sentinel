"""Privileged X1 entry point; inherits only explicitly prepared project code."""
import os
from pathlib import Path
import sys

if os.geteuid()!=0:
    raise SystemExit('Run with sudo and the board PYNQ Python interpreter')
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'ps'))
os.environ['XILINX_XRT']='/usr'
from sentinel.app.monitor_x1 import main

if __name__=='__main__':
    main()
