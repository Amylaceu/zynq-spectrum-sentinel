"""Bounded RX-only snapshots, CPU FFT and J22 LCD display on the board."""
import argparse
import ctypes as ct
import fcntl
import hashlib
import json
import os
import signal
import time
from pathlib import Path
os.environ['XILINX_XRT']='/usr'
import numpy as np
from sentinel.overlay import SentinelOverlay
from sentinel.rf.ad9361 import bind_library
from sentinel.mmio import make_mmio
from sentinel.quad_spi import QuadSpi
from sentinel.cma import allocate_owned
from sentinel.dma import AdiDmac
from sentinel.lcd_framebuffer import LcdFramebuffer
from sentinel.lcd_spectrum import spectrum, SpectrumScreen

p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=900)
args=p.parse_args()
if not 10<=args.seconds<=3600:raise ValueError('Duration must be10..3600 seconds')
root=Path('/home/xilinx/sentinel');target=root/'measurements/lcd_live_receive.json'
result=dict(status='starting',rf_transmission_requested=False,frames=0,
            display='400x240 RGB332 doubled to800x480',processing='board CPU FFT; gapped RX snapshots')
def save():
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
def check(ret,label):
    if ret<0:raise RuntimeError(label+': '+str(ret))
stop=False
def halt(*_):
    global stop
    stop=True
signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
save();lib=None;dma=None;owner=None
try:
    lock=open('/run/lock/zss_ad9361.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    bit=root/'overlay/live_z20_lcd/live_z20_lcd.bit'
    overlay=SentinelOverlay(str(bit),download=True)
    if not overlay.overlay.is_loaded():raise RuntimeError('New image not loaded')
    result['bit_sha256']=hashlib.sha256(bit.read_bytes()).hexdigest()
    gpio=overlay.registers('axi_ad9361_gpio');gpio.write(0,0)
    memory=overlay.overlay.mem_dict['axi_lcd_bram']
    if memory['phys_addr']!=0x42000000 or memory['addr_range']!=262144:
        raise RuntimeError('LCD memory aperture mismatch')
    display=LcdFramebuffer(make_mmio(memory['phys_addr'],memory['addr_range']),overlay.registers('axi_lcd_control'))
    screen=SpectrumScreen()
    f=np.linspace(82.64e6,113.36e6,2048);db=np.full(2048,-100.)
    image,pixels=screen.draw(f,db,0,state='INITIALIZING',fps=0)
    display.present(pixels)
    gpio.write(0,1);time.sleep(.02)
    spi=QuadSpi(overlay.registers('axi_ad9361_spi'),mode=1);spi.reset()
    ids=[spi.read_register(0x037) for _ in range(10)]
    result['product_ids']=ids
    gpio.write(0,0)
    if len(set(ids))!=1 or any((v&0xf8)!=8 for v in ids):raise RuntimeError('Chip identity mismatch')
    lock.close()
    lib=bind_library(str(root/'ps/libad9361_pynq/libad9361_pynq.so'))
    check(lib.z20_ad9361_open(),'init')
    check(lib.z20_configure_receive(98000000,30720000,24000000),'configure RX')
    rate=ct.c_uint32();lo=ct.c_uint64();mode=ct.c_uint32()
    check(lib.z20_get_sample_rate(ct.byref(rate)),'rate')
    check(lib.z20_get_rx_lo(ct.byref(lo)),'LO')
    check(lib.z20_get_ensm_mode(ct.byref(mode)),'ENSM')
    if rate.value!=30720000 or abs(lo.value-98000000)>3 or mode.value!=1:
        raise RuntimeError('Receive settings mismatch')
    attenuation=[]
    for ch in (0,1):
        a=ct.c_uint32();check(lib.z20_get_tx_attenuation(ch,ct.byref(a)),'attenuation');attenuation.append(a.value)
    if attenuation!=[89750,89750]:raise RuntimeError('TX attenuation mismatch')
    result.update(sample_rate_hz=rate.value,rx_lo_hz=lo.value,tx_attenuation_mdb=attenuation)
    if lib.z20_read_register(0x3f4)&1:raise RuntimeError('BIST enabled unexpectedly')
    n=65536;owner=allocate_owned(n*8+128);owner[:]=0xa5
    received=owner[64:-64]
    dma=AdiDmac(overlay.registers('axi_ad9361_adc_dma'),'rx',allocator=lambda _:received)
    start=time.monotonic();time.sleep(.3)
    while not stop and time.monotonic()-start<args.seconds:
        iteration=time.monotonic()
        dma.recv(n*8,timeout_s=2);owner.invalidate()
        if not np.all(owner[:64]==0xa5) or not np.all(owner[-64:]==0xa5):raise RuntimeError('DMA guard corruption')
        words=np.asarray(received).view('<i2').reshape(n,4).copy()
        if words.min()<-2048 or words.max()>2047 or np.std(words[:,0])==0:raise RuntimeError('Invalid RX data')
        f,db=spectrum(words,rate.value,lo.value)
        gain=ct.c_int32();check(lib.z20_get_rx_gain(0,ct.byref(gain)),'gain')
        frame=result['frames']+1
        image,pixels=screen.draw(f,db,frame,gain.value,fps=result.get('update_fps',0))
        state=display.present(pixels)
        result.update(status='running',frames=frame,lcd_status=state,
                      update_fps=1/max(time.monotonic()-iteration,.001),
                      rx_gain_db=gain.value,guards_ok=True,
                      latest_spectrum_range_db=[float(db.min()),float(db.max())])
        if frame==1 or frame%10==0:
            image.resize((800,480),resample=0).save(root/'measurements/lcd_live_preview.png')
            np.savez(root/'measurements/lcd_live_spectrum.npz',frequency_hz=f,dbfs_bin=db)
            save()
    result['status']='stopped'
except Exception as error:
    result.update(status='failed',error=str(error))
finally:
    if dma is not None:dma.mmio.write(dma.CTRL,0)
    if lib is not None:lib.z20_ad9361_close()
    if 'gpio' in globals():
        gpio.write(0,0);result['gpio_after_close']=gpio.read(0)
    result['buffers_quarantined']=bool(dma and dma.inflight)
    try:
        if 'screen' in globals() and 'display' in globals():
            image,pixels=screen.draw(f,db,result['frames'],state='RX STOPPED' if result['status']=='stopped' else 'RX ERROR')
            display.present(pixels);image.resize((800,480),resample=0).save(root/'measurements/lcd_live_preview.png')
    except Exception as error:result['display_close_error']=str(error)
    save()
if dma is not None and dma.inflight:
    while True:time.sleep(10)
if owner is not None:
    del received;owner.freebuffer()
if result['status']=='failed':raise SystemExit(1)
