"""Check stopped source/reset only after matching the actual loaded overlay."""
import fcntl
import json
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/'ps'))
    os.environ['XILINX_XRT'] = '/usr'
    from sentinel.app.monitor_x2 import checked_bundle
    from pynq import Overlay, MMIO
    with open('/run/lock/zss_ad9361.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        candidates = [('sentinel_v1c', 0x43460002), ('sentinel_v1b', 0x43460002)]
        selected = None
        for name, version in candidates:
            bit = root/'overlay'/name/(name+'.bit')
            if not bit.exists():
                continue
            overlay = Overlay(str(bit), download=False)
            if overlay.is_loaded():
                selected = name, version, bit, overlay
                break
        if selected is None:
            raise RuntimeError('No matching accepted overlay; refuse MMIO')
        name, version, bit, overlay = selected
        if name == 'sentinel_v1c':
            checked_bundle(bit)
        else:
            from sentinel.app.monitor_x1 import checked_bundle as checked_old
            checked_old(bit)
        bases = {'axi_ad9361_gpio': 0x41200000, 'src_mux_0': 0x43c00000,
                 'cfar_core_0': 0x43c20000}
        for instance, base in bases.items():
            if int(overlay.ip_dict[instance]['phys_addr']) != base:
                raise ValueError('Unexpected address: '+instance)
        if MMIO(bases['cfar_core_0'], 16384).read(0xfc) != version:
            raise ValueError('Loaded CFAR contract mismatch')
        gpio = MMIO(bases['axi_ad9361_gpio'], 4096).read(0)
        ctrl = MMIO(bases['src_mux_0'], 4096).read(0)
        result = dict(status='PASS' if gpio == 0 and not ctrl & 1 else 'FAIL',
                      boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                      loaded_overlay=name, gpio=gpio, source_ctrl=ctrl)
        print(json.dumps(result))
        if result['status'] != 'PASS':
            raise RuntimeError('Receiver is not stopped/reset')


if __name__ == '__main__':
    main()
