"""Base PL checks; full application acceptance requires the future custom IPs."""
import argparse
import json
from pathlib import Path

from .overlay import SentinelOverlay


def check_base(overlay,read_only=True):
    result={'stage':'base','rf_initialized':False,'tx_enabled':False,'gpio_write_test':'skipped_read_only'}
    sysid=overlay.registers('axi_sysid_0').read(0)
    core=overlay.registers('axi_ad9361').read(0)
    spi=overlay.registers('axi_ad9361_spi').read(0x64)
    if sysid!=0x10161 or core in (0,0xffffffff) or spi!=0x25:
        raise RuntimeError('Base version/status mismatch: '+str((sysid,core,spi)))
    result.update(sysid=hex(sysid),ad9361_interface_version=hex(core),spi_status=hex(spi))
    gpio=overlay.registers('axi_ad9361_gpio')
    result['gpio']=gpio.read(0)
    if not read_only:
        # Base top uses only bits0..8; bit15 never reaches a pad. This test
        # preserves all RF-related bits and restores the full original word.
        original=gpio.read(0)
        try:
            test=original^(1<<15)
            gpio.write(0,test)
            if gpio.read(0)!=test:
                raise RuntimeError('GPIO output register readback mismatch')
        finally:
            gpio.write(0,original)
        result['gpio_write_test']='passed_unused_bit15'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--stage',choices=['base'],default='base')
    p.add_argument('--bit',default='/home/xilinx/sentinel/overlay/base_z20/base_z20.bit')
    p.add_argument('--reuse',action='store_true')
    p.add_argument('--read-only',action='store_true')
    p.add_argument('--out')
    a=p.parse_args()
    overlay=SentinelOverlay(a.bit,download=not a.reuse)
    if a.reuse and not overlay.overlay.is_loaded():
        raise RuntimeError('Expected overlay is not loaded; refuse blind MMIO access')
    result=check_base(overlay,read_only=a.read_only)
    print(json.dumps(result,indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
