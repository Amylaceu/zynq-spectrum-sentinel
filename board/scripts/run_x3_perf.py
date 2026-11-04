"""Root-only bounded X3 entry point, PYNQ Python 3.8; see docs/x3_execution.md."""
import os
from pathlib import Path
import sys

if os.geteuid() != 0:
    raise SystemExit('Run using sudo and the PYNQ Python interpreter')
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'ps'))
os.environ['XILINX_XRT'] = '/usr'
from sentinel.app.perf_x3 import main

if __name__ == '__main__':
    main()
