"""PYNQ entry for X2 finite tests; AD9361 stays in reset."""
import os
from pathlib import Path
import sys

if os.geteuid() != 0:
    raise SystemExit('Run with sudo and the board PYNQ Python interpreter')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ps'))
os.environ['XILINX_XRT'] = '/usr'
from sentinel.app.selftest_x2 import main

if __name__ == '__main__':
    main()
