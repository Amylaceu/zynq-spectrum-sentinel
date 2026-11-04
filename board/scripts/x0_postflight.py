"""Read accepted v1 stop/reset state without loading an overlay or writing MMIO."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    bundle = root / 'overlay/sentinel_v1'
    acceptance = json.loads((bundle/'acceptance.json').read_text())
    if acceptance.get('status') != 'PASS':
        raise RuntimeError('No accepted v1 artifact bundle')
    for suffix in ('bit', 'hwh', 'xsa'):
        path = bundle/('sentinel_v1.'+suffix)
        if hashlib.sha256(path.read_bytes()).hexdigest() != acceptance['artifacts_sha256'][path.name]:
            raise RuntimeError('Bundle hash mismatch: '+path.name)
    os.environ['XILINX_XRT'] = '/usr'
    with open('/run/lock/zss_ad9361.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from pynq import Overlay, MMIO
        overlay = Overlay(str(bundle/'sentinel_v1.bit'), download=False)
        if not overlay.is_loaded():
            raise RuntimeError('Expected v1 is not loaded; refusing MMIO')
        addresses = {'axi_ad9361_gpio': 0x41200000, 'src_mux_0': 0x43c00000}
        for name, address in addresses.items():
            if int(overlay.ip_dict[name]['phys_addr']) != address:
                raise RuntimeError('Unexpected address: '+name)
        gpio = MMIO(addresses['axi_ad9361_gpio'], 4096)
        source = MMIO(addresses['src_mux_0'], 4096)
        version = source.read(0xfc)
        if version != 0x53520001:
            raise RuntimeError('Unexpected source version')
        result = {
            'scope': 'Read-only MMIO after accepted artifact and loaded-image checks',
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'gpio_data': gpio.read(0), 'source_ctrl': source.read(0),
            'source_version': version, 'overlay_downloaded': False,
            'register_writes': False, 'rf_initialized': False,
        }
        result['status'] = 'PASS' if result['gpio_data'] == 0 and not result['source_ctrl'] & 1 else 'FAIL'
        print(json.dumps(result), flush=True)
        if result['status'] != 'PASS':
            raise RuntimeError('RF reset or source stop readback failed')


if __name__ == '__main__':
    main()
