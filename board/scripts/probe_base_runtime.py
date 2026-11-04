"""Small staged base-overlay probe; no RF initialization or TX operation."""
import json
import os
from pathlib import Path

os.environ['XILINX_XRT']='/usr'
from pynq import Overlay,MMIO

root=Path('/home/xilinx/sentinel')
path=root/'measurements/base_runtime_probe.jsonl'


def checkpoint(stage, **details):
    row=dict(stage=stage,**details)
    with path.open('a') as stream:
        stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(row),flush=True)


overlay=Overlay(str(root/'overlay/base_z20/base_z20.bit'),download=False)
checkpoint('metadata',ips=sorted(overlay.ip_dict))
checkpoint('download_start')
overlay.download()
checkpoint('download_returned')
for name,offset in [('axi_sysid_0',0),('axi_ad9361',0),('axi_ad9361_gpio',0),('axi_ad9361_spi',0x64)]:
    address=overlay.ip_dict[name]['phys_addr']
    checkpoint('read_start',ip=name,address=address,offset=offset)
    word=MMIO(address,offset+4).read(offset)
    checkpoint('read_returned',ip=name,value=word,hex=hex(word))
checkpoint('complete',rf_initialized=False,tx_enabled=False)
