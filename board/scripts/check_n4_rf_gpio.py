"""Read N4 RF GPIO registers without writing GPIO or loading a bitstream."""
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path('/home/xilinx/sentinel')
sys.path.insert(0, str(ROOT / 'ps'))
os.environ['XILINX_XRT'] = '/usr'
from sentinel.v1 import V1

with open('/run/lock/zss_ad9361.lock', 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    h = V1(download=False)
    if not h.overlay.is_loaded():
        raise RuntimeError('Expected N4 overlay is not loaded')
    gpio = h.checked.registers('axi_ad9361_gpio')
    print(json.dumps({
        'scope': 'register read only; no writes, RF init or bitstream loading',
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'gpio': {hex(offset): hex(gpio.read(offset)) for offset in (0, 4, 8, 12)},
        'parameters': h.checked.ip_dict['axi_ad9361_gpio'].get('parameters', {}),
    }), flush=True)
