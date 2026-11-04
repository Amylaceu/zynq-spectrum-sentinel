"""Bounded internal RX-tone/DMA acceptance, retaining buffers on DMA failure."""
import argparse
import ctypes as ct
import hashlib
import json
import os
import time
from pathlib import Path

os.environ['XILINX_XRT'] = '/usr'
import numpy as np
from sentinel.cma import allocate_owned
from sentinel.overlay import SentinelOverlay
from sentinel.rf.ad9361 import bind_library
from sentinel.dma import AdiDmac
from sentinel.rx_acceptance import analyze_bist_tone

parser = argparse.ArgumentParser()
parser.add_argument('--attempt',type=int,choices=(1,2,3),default=1)
args = parser.parse_args()
root = Path('/home/xilinx/sentinel')
output = root/('measurements/rx_bist_round%d.json' % args.attempt)
result = dict(status='started',attempt=args.attempt,source='ad9361_internal_rx_bist_tone',
              rf_transmission_requested=False,captures=[])
def save(stage):
    result['stage'] = stage
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(stage,flush=True)
def check(code,what):
    if code < 0: raise RuntimeError(what+': '+str(code))
save('validate_overlay')
bit = root/'overlay/bringup_z20_lcd/bringup_z20_lcd.bit'
overlay = SentinelOverlay(str(bit),download=False)
if not overlay.overlay.is_loaded(): raise RuntimeError('Required bring-up overlay not loaded')
identity = json.loads((root/'measurements/ad9361_product_id_bringup_z20_lcd.json').read_text())
digest = hashlib.sha256(bit.read_bytes()).hexdigest()
if not identity['valid'] or not identity['stable'] or identity['bit_sha256'] != digest:
    raise RuntimeError('Matching stable chip identity required')
result['bit_sha256'] = digest
lib = bind_library(str(root/'ps/libad9361_pynq/libad9361_pynq.so'))

owners=[]
def guarded_allocate(n):
    owner = allocate_owned(n+128)
    owner[:] = 0xa5;owner[64:64+n] = 0xcc;owner.flush()
    owners.append(owner)
    return owner[64:64+n]
dma = AdiDmac(overlay.registers('axi_ad9361_adc_dma'),'rx',allocator=guarded_allocate)
try:
    save('initialize_rf')
    check(lib.z20_ad9361_open(),'no-OS init')
    sample_rate = ct.c_uint32()
    check(lib.z20_get_sample_rate(ct.byref(sample_rate)),'rate')
    result['sample_rate_hz'] = sample_rate.value
    save('enable_rx_internal_tone')
    check(lib.z20_rx_test_tone(1),'RX internal tone')
    mode = ct.c_uint32()
    check(lib.z20_get_ensm_mode(ct.byref(mode)),'ENSM')
    if mode.value != 1: raise RuntimeError('Receive-only ENSM required')
    result['ensm_mode_during_capture'] = mode.value
    time.sleep(.02)
    adc = overlay.registers('axi_ad9361')
    result['adc_channel_controls'] = [hex(adc.read(0x400+0x40*i)) for i in range(4)]
    n = 8192
    for index in range(4):
        save('capture_%d' % index)
        started = time.monotonic()
        received = dma.recv(n*8,timeout_s=2)
        elapsed = time.monotonic()-started
        owner = owners[-1];owner.invalidate()
        guards_ok = bool(np.all(owner[:64]==0xa5) and np.all(owner[-64:]==0xa5))
        words = np.asarray(received).view('<i2').reshape(n,4).copy()
        summary = analyze_bist_tone(words,sample_rate.value)
        summary.update(index=index,bytes=n*8,elapsed_s=elapsed,guards_ok=guards_ok,
                       physical_address=hex(int(received.physical_address)))
        result['captures'].append(summary)
        if index==0:
            np.save(root/'measurements/rx_bist_first_native.npy',words)
            result['first_native_sha256']=hashlib.sha256(words.tobytes()).hexdigest()
        save('capture_%d_analyzed' % index)
        if not guards_ok or not summary['passed']:
            raise RuntimeError('RX tone/DMA acceptance failed')
        del received
        owner.freebuffer();owners.pop();del owner
    attenuation=[]
    for channel in (0,1):
        a=ct.c_uint32();check(lib.z20_get_tx_attenuation(channel,ct.byref(a)),'TX attenuation')
        attenuation.append(a.value)
    result['tx_attenuation_mdb']=attenuation
    if attenuation != [89750,89750]: raise RuntimeError('TX attenuation changed')
    check(lib.z20_rx_test_tone(0),'disable RX test tone')
    result['status']='passed'
except Exception as error:
    result.update(status='failed',error=str(error))
finally:
    # Disable capture and assert RF reset before considering buffer release.
    dma.mmio.write(dma.CTRL,0)
    lib.z20_ad9361_close()
    result['gpio_after_close']=overlay.registers('axi_ad9361_gpio').read(0)
    result['buffers_quarantined']=bool(dma.inflight)
    save('closed_rf_and_dma')
    print(json.dumps(result,indent=2),flush=True)
if dma.inflight:
    # Do not exit/free CMA while an unacknowledged transfer may own memory.
    # Keep this background process alive until an explicit board reset.
    while True: time.sleep(10)
for owner in owners: owner.freebuffer()
if result['status']!='passed': raise SystemExit(1)
