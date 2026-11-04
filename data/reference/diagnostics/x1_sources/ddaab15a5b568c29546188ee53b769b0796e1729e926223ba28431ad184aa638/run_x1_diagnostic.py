"""Exclusive PYNQ entry for paired finite-frame diagnostics."""
import os
from pathlib import Path
import sys

if os.geteuid() != 0:
    raise SystemExit('Use sudo and the board PYNQ Python interpreter')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ps'))
os.environ['XILINX_XRT'] = '/usr'
from sentinel.app.diagnose_x1 import main

if __name__ == '__main__':
    main()
