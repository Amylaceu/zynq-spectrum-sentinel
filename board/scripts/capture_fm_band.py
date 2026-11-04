"""Bounded antenna receive capture around98MHz; no BIST and no TX."""
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
args = parser.parse_args()
root = Path('/home/xilinx/sentinel')
output = root/('measurements/fm_scan_round%d.json' % args.attempt)
result = dict(status='started',attempt=args.attempt,source='rx1a_antenna_fm_band',
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
    save('tune_98mhz_antenna_receive')
    check(lib.z20_start_receive(98000000),'start receive')
    lo=ct.c_uint64();check(lib.z20_get_rx_lo(ct.byref(lo)),'LO readback')
    result['rx_lo_hz']=lo.value
    if abs(lo.value-98000000)>2:raise RuntimeError('Incorrect RX LO readback')
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
    n = 131072
    nfft=8192;window=np.hanning(nfft)
    denominator=nfft*np.sum(window**2)*2048**2
    spectra=[]
    for index in range(8):
        save('capture_%d' % index)
        started = time.monotonic()
        received = dma.recv(n*8,timeout_s=2)
        elapsed = time.monotonic()-started
        owner = owners[-1];owner.invalidate()
        guards_ok = bool(np.all(owner[:64]==0xa5) and np.all(owner[-64:]==0xa5))
        words = np.asarray(received).view('<i2').reshape(n,4).copy()
        channel_psd=[]
        for channel in range(2):
            z=words[:,2*channel].astype(float)+1j*words[:,2*channel+1].astype(float)
            blocks=z.reshape(-1,nfft)
            channel_psd.append(np.mean(np.abs(np.fft.fft(blocks*window,axis=1))**2,axis=0)/denominator)
        spectra.append(channel_psd)
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
        if index==0:
            np.save(root/('measurements/fm_scan_first_native_round%d.npy'%args.attempt),words)
            result['first_native_sha256']=hashlib.sha256(words.tobytes()).hexdigest()
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
    np.savez_compressed(root/('measurements/fm_scan_psd_round%d.npz'%args.attempt),
                        frequency_hz=lo.value+np.fft.fftshift(np.fft.fftfreq(nfft,1./sample_rate.value)),
                        power_bin_fullscale=np.fft.fftshift(np.mean(spectra,axis=0),axes=1),
                        sample_rate_hz=sample_rate.value,lo_hz=lo.value)
    result['fft_size']=nfft
    result['psd_normalization']='mean(abs(FFT(x*hann))**2)/(N*sum(hann**2)*2048**2)'
    result['signal_identification']='pending_host_analysis'
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
