"""Read stopped X1 state, guarding accepted files and actual loaded image."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    root=args.root.resolve()
    sys.path.insert(0,str(root/'ps'))
    from sentinel.app.monitor_x1 import checked_bundle
    bit=root/'overlay/sentinel_v1b/sentinel_v1b.bit'
    checked_bundle(bit)
    os.environ['XILINX_XRT']='/usr'
    with open('/run/lock/zss_ad9361.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from pynq import Overlay,MMIO
        overlay=Overlay(str(bit),download=False)
        if not overlay.is_loaded():
            raise RuntimeError('Refuse MMIO before matching loaded v1b')
        mappings={'axi_ad9361_gpio':0x41200000,'src_mux_0':0x43c00000,'cfar_core_0':0x43c20000}
        regs={}
        for name,base in mappings.items():
            if int(overlay.ip_dict[name]['phys_addr'])!=base:
                raise RuntimeError('Address mismatch: '+name)
            regs[name]=MMIO(base,4096)
        if regs['cfar_core_0'].read(0xfc)!=0x43460002:
            raise RuntimeError('Wrong CFAR version')
        record={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'gpio_data':regs['axi_ad9361_gpio'].read(0),
                'source_ctrl':regs['src_mux_0'].read(0),
                'scope':'Read-only X1 stop-state check; no overlay download or RF initialization'}
        record['status']='PASS' if record['gpio_data']==0 and record['source_ctrl']&1==0 else 'FAIL'
        print(json.dumps(record),flush=True)
        if record['status']!='PASS':
            raise RuntimeError('Stop/reset readback failed')


if __name__=='__main__':
    main()
