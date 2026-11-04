import json
import os
import gc
import time
from pathlib import Path
os.environ['XILINX_XRT']='/usr'
from sentinel.overlay import SentinelOverlay
from sentinel.cma import allocate_owned

root=Path('/home/xilinx/sentinel')
overlay=SentinelOverlay(str(root/'overlay/bringup_z20_lcd/bringup_z20_lcd.bit'),download=False)
if not overlay.overlay.is_loaded():raise RuntimeError('Bring-up overlay required')
def free_kb():
    return int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('CmaFree:')))
measurements=[]
for _ in range(3):
    before=free_kb();owner=allocate_owned(1048704);owner[:]=0xa5
    allocated=free_kb();address=hex(int(owner.physical_address))
    owner.freebuffer();del owner;gc.collect();time.sleep(.2);released=free_kb()
    measurements.append(dict(before_kb=before,allocated_kb=allocated,released_kb=released,address=address))
    print(measurements[-1],flush=True)
    if released < before:raise RuntimeError('CMA allocation not returned after explicit release')
result=dict(status='passed',backend='installed_pynq27_xrt_cache_protocol',measurements=measurements)
(root/'measurements/cma_release.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
