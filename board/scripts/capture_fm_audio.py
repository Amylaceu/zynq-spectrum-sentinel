"""Bounded antenna receive capture near90MHz for host FM demodulation; no BIST or TX."""
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

parser = argparse.ArgumentParser()
parser.add_argument('--attempt',type=int,choices=(1,2,3),default=1)
parser.add_argument('--station',type=int,choices=(90000000,95800000,100900000),default=90000000)
parser.add_argument('--blocks',type=int,choices=(4,8,16),default=4)
args = parser.parse_args()
root = Path('/home/xilinx/sentinel')
output = root/('measurements/fm_audio_%d_round%d.json' % (args.station,args.attempt))
result = dict(status='started',attempt=args.attempt,source='rx1a_antenna_candidate_for_fm_demod',
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

folder=root/'data/captured/fm_diagnostic';folder.mkdir(parents=True,exist_ok=True)
name='fm_%d_round%d'%(args.station,args.attempt)
data_path=folder/(name+'.sigmf-data')
stream=data_path.open('wb')
metadata={'global':{'core:datatype':'ci16_le','core:num_channels':1,'core:version':'1.0.0',
                   'core:description':'Antenna RX1 candidate, native12-bit samples left-aligned to16 bits. Gapped multishot diagnostic; no station identity verified.'},
          'captures':[],'annotations':[]}
result['candidate_frequency_hz']=args.station
result['sigmf_data_relative_path']=str(data_path.relative_to(root))
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
    save('tune_narrowband_antenna_receive')
    target_lo=args.station+250000
    check(lib.z20_configure_receive(target_lo,3840000,1500000),'configure receive')
    check(lib.z20_get_sample_rate(ct.byref(sample_rate)),'new sample rate')
    if abs(sample_rate.value-3840000)>1:raise RuntimeError('Unexpected narrowband sample rate')
    result['sample_rate_hz']=sample_rate.value
    metadata['global']['core:sample_rate']=sample_rate.value
    lo=ct.c_uint64();check(lib.z20_get_rx_lo(ct.byref(lo)),'LO readback')
    result['rx_lo_hz']=lo.value
    if abs(lo.value-target_lo)>3:raise RuntimeError('Incorrect RX LO readback')
    registers={hex(a):lib.z20_read_register(a) for a in (0x037,0x05e,0x247,0x3f4,0x006,0x007)}
    result['chip_registers']=registers
    if not (registers['0x5e']&0x80 and registers['0x247']&2) or registers['0x3f4']&1:
        raise RuntimeError('PLL unlock or BIST unexpectedly enabled')
    mode = ct.c_uint32()
    check(lib.z20_get_ensm_mode(ct.byref(mode)),'ENSM')
    if mode.value != 1: raise RuntimeError('Receive-only ENSM required')
    result['ensm_mode_during_capture'] = mode.value
    time.sleep(.3)
    adc = overlay.registers('axi_ad9361')
    result['adc_channel_controls'] = [hex(adc.read(0x400+0x40*i)) for i in range(4)]
    n = 1048576
    for index in range(args.blocks):
        save('capture_%d' % index)
        started = time.monotonic()
        received = dma.recv(n*8,timeout_s=2)
        elapsed = time.monotonic()-started
        owner = owners[-1];owner.invalidate()
        guards_ok = bool(np.all(owner[:64]==0xa5) and np.all(owner[-64:]==0xa5))
        words = np.asarray(received).view('<i2').reshape(n,4).copy()
        gain=[];rssi=[]
        for channel in (0,1):
            g=ct.c_int32();v=ct.c_int32()
            check(lib.z20_get_rx_gain(channel,ct.byref(g)),'RX gain')
            check(lib.z20_get_rx_rssi(channel,ct.byref(v)),'RSSI')
            gain.append(g.value);rssi.append(v.value)
        summary=dict(minimum=int(words.min()),maximum=int(words.max()),
                     std_counts=[float(np.std(words[:,i])) for i in range(4)],
                     clipped_fraction=float(np.mean((words<=-2048)|(words>=2047))),
                     rx_gain_db=gain,chip_rssi_mdb=rssi,
                     passed=bool(words.min()>=-2048 and words.max()<=2047 and np.std(words[:,0])>0 and np.std(words[:,1])>0))
        summary.update(index=index,bytes=n*8,elapsed_s=elapsed,guards_ok=guards_ok,
                       physical_address=hex(int(received.physical_address)))
        result['captures'].append(summary)
        rx1=(words[:,0:2].astype(np.int32)*16).astype('<i2')
        stream.write(rx1.tobytes());stream.flush()
        metadata['captures'].append({'core:sample_start':index*n,'core:frequency':lo.value,
                                     'zss:monotonic_start_s':started,'zss:sample_count':n})
        metadata['annotations'].append({'core:sample_start':index*n,'core:sample_count':n,
                                        'core:label':'candidate_%dHz_antenna'%args.station})
        save('capture_%d_analyzed' % index)
        if not guards_ok or not summary['passed']:
            raise RuntimeError('Antenna receive/DMA data acceptance failed')
        del received
        owner.freebuffer();owners.pop();del owner
    attenuation=[]
    for channel in (0,1):
        a=ct.c_uint32();check(lib.z20_get_tx_attenuation(channel,ct.byref(a)),'TX attenuation')
        attenuation.append(a.value)
    result['tx_attenuation_mdb']=attenuation
    if attenuation != [89750,89750]: raise RuntimeError('TX attenuation changed')
    stream.close()
    metadata['global']['core:sha512']=hashlib.sha512(data_path.read_bytes()).hexdigest()
    (folder/(name+'.sigmf-meta')).write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    result['iq_samples']=n*args.blocks
    result['captured_duration_s']=n*args.blocks/sample_rate.value
    result['continuous_recording']=False
    result['signal_identification']='pending_host_fm_demodulation'
    result['status']='passed'
except Exception as error:
    result.update(status='failed',error=str(error))
finally:
    stream.close()
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
