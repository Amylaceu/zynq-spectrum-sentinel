"""Read AD9361 product ID with reset/ENABLE/TXNRX kept in a safe state."""
import json
import argparse
import fcntl
import hashlib
import os
import time
from pathlib import Path

os.environ['XILINX_XRT']='/usr'
from sentinel.overlay import SentinelOverlay
from sentinel.quad_spi import QuadSpi

root=Path('/home/xilinx/sentinel')
parser=argparse.ArgumentParser()
parser.add_argument('--overlay',choices=['base_z20','bringup_z20_lcd'],default='base_z20')
parser.add_argument('--download',action='store_true')
args=parser.parse_args()
lock=open('/run/lock/zss_ad9361.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
overlay=SentinelOverlay(str(root/'overlay'/args.overlay/(args.overlay+'.bit')),download=args.download)
if not overlay.overlay.is_loaded():
    raise RuntimeError('Verified image must already be loaded')
gpio=overlay.registers('axi_ad9361_gpio')
spi=QuadSpi(overlay.registers('axi_ad9361_spi'),mode=1)
gpio.write(0,0)
time.sleep(.1)
gpio.write(0,1)  # RESETB released; ENABLE and TXNRX stay low.
time.sleep(.02)
spi.reset()
try:
    values=[]
    for _ in range(10):
        values.append(spi.read_register(0x037))
        time.sleep(.01)
    result=dict(overlay=args.overlay,bit_sha256=hashlib.sha256((root/'overlay'/args.overlay/(args.overlay+'.bit')).read_bytes()).hexdigest(),address='0x037',command='00 37 00',mode=1,
                product_ids=[hex(v) for v in values],gpio=gpio.read(0),
                stable=len(set(values))==1,valid=all((v&0xf8)==0x08 for v in values),
                rf_initialized=False,tx_enabled=False)
    (root/('measurements/ad9361_product_id_'+args.overlay+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)
    if not result['valid'] or not result['stable']:
        gpio.write(0,0)
        raise RuntimeError('AD9361 product-ID acceptance failed; RF held in reset')
except Exception:
    gpio.write(0,0)
    raise
