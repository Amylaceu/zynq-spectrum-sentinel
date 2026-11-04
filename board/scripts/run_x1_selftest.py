"""Board PYNQ entry for finite X1 self-test; AD9361 remains held in reset."""
import os
import signal
from pathlib import Path
import sys

if os.geteuid()!=0:
    raise SystemExit('Run with sudo and the board PYNQ Python interpreter')
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'ps'))
os.environ['XILINX_XRT']='/usr'
from sentinel.app.selftest_x1 import main

if __name__=='__main__':
    # Let Session.close() and evidence finally blocks run on bounded-run timeout.
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    main()
