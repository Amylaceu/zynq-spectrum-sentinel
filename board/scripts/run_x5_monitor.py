"""Explicit root-only X5 entry; works from an isolated, hashed deployment root."""
import os
from pathlib import Path
import sys


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('Use the PYNQ Python interpreter with sudo')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    os.environ['XILINX_XRT'] = '/usr'
    from sentinel.app.monitor_x5 import main
    main()
