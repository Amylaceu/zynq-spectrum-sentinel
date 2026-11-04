"""Read-only stop check for an explicitly accepted v1d or Z2 loaded image.

No download, ADC initialization, source enable or TX operation is performed.
Keep this entry independent of V1d construction, which allocates DMA objects.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    from sentinel.overlay import validate_artifacts
    bit = validate_artifacts(args.bit)
    image = bit.stem
    if image not in ('sentinel_v1d', 'sentinel_z2'):
        raise ValueError('Only audited baseline or X5 image is supported')
    path = bit.parent/'acceptance.json'
    if image in ('sentinel_v1d', 'sentinel_z2'):
        if hashlib.sha256(path.read_bytes()).hexdigest() != Path(str(path)+'.sha256').read_text().split()[0]:
            raise ValueError('Acceptance sidecar mismatch')
    acceptance = json.loads(path.read_text())
    if acceptance['status'] != 'PASS' or acceptance.get('image') != image:
        raise ValueError('Require accepted image')
    for suffix in ('.bit', '.hwh'):
        artifact = bit.with_suffix(suffix)
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != acceptance['artifacts_sha256'][artifact.name]:
            raise ValueError('Artifact digest mismatch')
    os.environ['XILINX_XRT'] = '/usr'
    with open('/run/lock/zss_ad9361.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from pynq import Overlay, MMIO
        overlay = Overlay(str(bit), download=False)
        if not overlay.is_loaded():
            raise RuntimeError('Matching image not loaded; no MMIO attempted')
        registers = {}
        addresses = {'axi_ad9361_gpio': 0x41200000, 'src_mux_0': 0x43c00000,
                     'cfar_core_0': 0x43c20000, 'lcd_engine': 0x43c60000}
        if image in ('sentinel_v1d', 'sentinel_z2'):
            addresses['x5_status'] = 0x41250000
        for name, base in addresses.items():
            if int(overlay.ip_dict[name]['phys_addr']) != base:
                raise RuntimeError('Wrong register address '+name)
            registers[name] = MMIO(base, 4096)
        if registers['cfar_core_0'].read(0xfc) != 0x43460002:
            raise RuntimeError('Wrong CFAR version')
        lcd_version = registers['lcd_engine'].read(0xfc)
        if lcd_version != (0x4c430005 if image == 'sentinel_v1d' else 0x4c430006):
            raise RuntimeError('Wrong LCD version: %#x' % lcd_version)
        record = dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                      image=image, gpio_data=registers['axi_ad9361_gpio'].read(0),
                      source_ctrl=registers['src_mux_0'].read(0), lcd_version=lcd_version,
                      scope='Stopped readback only; no RF initialization or download')
        if image in ('sentinel_v1d', 'sentinel_z2'):
            record['capture_status'] = registers['x5_status'].read(0)
        stopped = record['gpio_data'] == 0 and record['source_ctrl'] & 1 == 0
        record['status'] = 'PASS' if stopped else 'FAIL'
        print(json.dumps(record), flush=True)
        if not stopped:
            raise RuntimeError('Source/RF reset readback failed')


if __name__ == '__main__':
    main()
