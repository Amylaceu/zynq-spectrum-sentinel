"""Muted internal AD9361 TX->RX loopback: verify every captured native word."""
import argparse
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
os.environ['XILINX_XRT']='/usr'
import numpy as np
from sentinel.overlay import SentinelOverlay
from sentinel.cma import allocate_owned
from sentinel.dma import AdiDmac,AdiCyclicTx
from sentinel.loopback import sequence,compare_cyclic
from sentinel.rf import AD9361
from sentinel.artifacts import atomic_write,atomic_json

p=argparse.ArgumentParser();p.add_argument('--rate',type=float,default=30.72e6)
p.add_argument('--out',default='measurements/tx_loopback.json')
p.add_argument('--attempt',type=int,choices=(1,2,3,4),default=1)
p.add_argument('--authorized-extra-attempt',action='store_true',help='Round4 only: explicit user authorization must already be recorded')
p.add_argument('--load-overlay',action='store_true',help='Explicitly reload the verified live image before RF access')
args=p.parse_args();root=Path('/home/xilinx/sentinel')
if args.attempt==4 and not args.authorized_extra_attempt:raise ValueError('Round4 requires explicit user authorization')
output=(root/args.out).resolve()
if root/'measurements' not in output.parents:raise ValueError('Output must be under measurements')
if args.rate!=30720000:raise ValueError('This acceptance is fixed at30.72MSPS')
result=dict(status='started',attempt=args.attempt,sequences=[],rf_transmission_requested=False,
            tx_ports_empty_user_confirmed=True,format='TX signed12 left-aligned16 -> RX signed12 sign-extended16; all12 bits compared')
result['extra_attempt_user_authorized']=args.attempt==4 and args.authorized_extra_attempt
def save():
 atomic_json(output,result);print(json.dumps(result),flush=True)
result['stage']='preflight';save()
lock=open('/run/lock/zss_ad9361.lock','a')
try:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 bit=root/'overlay/live_z20_lcd/live_z20_lcd.bit'
 result['bit_sha256']=hashlib.sha256(bit.read_bytes()).hexdigest()
 if result['bit_sha256']!='773a378a6ee8f4b6b7e9a824e71a4eaa823087f33faf57c2029348f2a92c8487':
  raise RuntimeError('Not the verified N1 live image')
 overlay=SentinelOverlay(str(bit),download=args.load_overlay)
 if not overlay.overlay.is_loaded():raise RuntimeError('Verified live_z20_lcd image must be loaded')
 result['overlay_reloaded']=args.load_overlay;save()
except Exception as error:
 result.update(status='failed',error=str(error));save();raise
finally:
 # The C platform acquires this same lock during radio.open().
 # Hold it for overlay programming only, then hand ownership to that backend.
 fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
adc=overlay.registers('axi_ad9361')
rx=AdiDmac(overlay.registers('axi_ad9361_adc_dma'),'rx')
tx=AdiCyclicTx(overlay.registers('axi_ad9361_dac_dma'))
owners=[];saved={};radio=AD9361();readbacks=[]
def max_attenuation():
 a=radio.tx_atten;readbacks.append([round(v*1000) for v in a])
 if a!=(89.75,89.75):raise RuntimeError('Attenuation changed')
def buffer(n):
 owner=allocate_owned(n+128);owner[:]=0xa5;owner.flush();owners.append(owner)
 return owner[64:-64]
try:
 result['stage']='initialize_rf';save()
 radio.open(rate=30720000,rx_lo=98000000,bandwidth=24000000)
 result['product_id']=radio.lib.z20_read_register(0x037)
 if result['product_id']<0 or result['product_id']&0xf8!=0x08:raise RuntimeError('Invalid AD9361 product ID')
 result['stage']='configure_digital_paths';save()
 max_attenuation()
 for ch in range(4):
  for off in (0x400+ch*0x40,0x418+ch*0x40,0x4414+ch*0x40,0x4418+ch*0x40):saved[off]=adc.read(off)
  adc.write(0x400+ch*0x40,0x51) # sign extension/format/enable; no DCFILT or IQCOR
  adc.write(0x418+ch*0x40,0) # actual ADC, not HDL RX<-TX mux
  adc.write(0x4414+ch*0x40,0) # disable DAC IQCOR
  adc.write(0x4418+ch*0x40,2) # DMA data source, pinned HDL encoding
 adc.write(0x4044,1)
 result['stage']='enable_internal_loopback';save();radio.bist_loopback(True)
 result['observe_config']=radio.lib.z20_read_register(0x3f5)
 result['rx_channel_control']=[adc.read(0x400+ch*0x40) for ch in range(4)]
 result['dac_data_select']=[adc.read(0x4418+ch*0x40) for ch in range(4)]
 for kind in ('ramp','pn'):
  reference=sequence(kind)
  txbuf=buffer(65536);txbuf.view('<i2')[:]=(reference.astype(np.int32)*16).astype('<i2').reshape(-1);txbuf.flush()
  received=buffer(262144);rx.allocator=lambda _:received
  result['stage']='start_'+kind+'_cyclic_tx';save()
  max_attenuation();tx.start(txbuf);time.sleep(.03);max_attenuation()
  result['stage']='capture_'+kind+'_rx';save()
  rx.recv(262144,timeout_s=3);max_attenuation()
  words=np.asarray(received).view('<i2').reshape(-1,4).copy()
  result['stage']='drain_'+kind+'_cyclic_tx';save();tx.stop();max_attenuation()
  record=compare_cyclic(reference,words)
  record.update(kind=kind,tx_bytes=65536,rx_bytes=262144,
   rx_min=int(words.min()),rx_max=int(words.max()),
   reference_sha256=hashlib.sha256(reference.tobytes()).hexdigest(),rx_sha256=hashlib.sha256(words.tobytes()).hexdigest(),
   guards_ok=all(bool(np.all(o[:64]==0xa5) and np.all(o[-64:]==0xa5)) for o in owners))
  capture=root/('measurements/tx_loopback_round'+str(args.attempt)+'_'+kind+'.npz')
  atomic_write(capture,lambda stream: np.savez_compressed(stream,reference_native=reference,received_native=words))
  record['capture_file']=str(capture.relative_to(root))
  record['capture_sha256']=hashlib.sha256(capture.read_bytes()).hexdigest()
  result['sequences'].append(record)
  save()
  if not record['passed'] or not record['guards_ok']:raise RuntimeError(kind+' bit-exact acceptance failed')
 radio.bist_loopback(False);max_attenuation()
 result['status']='passed';result['stage']='completed'
except Exception as error:result.update(status='failed',error=str(error))
finally:
 try:tx.stop()
 except Exception as error:result['tx_stop_error']=str(error)
 rx.mmio.write(rx.CTRL,0)
 for off,value in saved.items():adc.write(off,value)
 if saved:adc.write(0x4044,1)
 radio.close()
 result['tx_atten_mdb_samples']=readbacks
 result['gpio_after_close']=overlay.registers('axi_ad9361_gpio').read(0)
 result['buffers_quarantined']=bool(tx.inflight or rx.inflight)
 if result['gpio_after_close']!=0 or result['buffers_quarantined'] or 'tx_stop_error' in result:
  result['status']='failed';result['cleanup_acceptance_failed']=True
 save()
if tx.inflight or rx.inflight:
 while True:time.sleep(10)
if owners:
 del txbuf,received
 for owner in owners:owner.freebuffer()
if result['status']!='passed':raise SystemExit(1)
