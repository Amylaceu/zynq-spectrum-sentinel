"""Finite test-tone and bit-exact golden replay acceptance; RF remains in reset."""
import argparse,hashlib,time
from pathlib import Path
import numpy as np
from .runtime_v1 import Session
from ..v1 import wait_until
from ..drivers.regs import src_ctrl as S
from ..drivers.regs import cfar_ctrl as C
from ..artifacts import atomic_json,atomic_write
from ..cma import allocate_owned

def bin_error(a,b):return min((a-b)%2048,(b-a)%2048)

def finite_frame(h,mode,bins=(64,),amps=(8192,),replay=None,rate=30720000):
    h.source.stop()
    h.source.configure(mode,rate=rate,bins=bins,amplitudes=amps,frames=1)
    before=h.cfar.mmio.read(C.FRAME_COUNT);token=h.arm_capture()
    dma=h.checked.registers('axi_dma_replay');owner=None
    try:
        if replay is not None:
            owner=allocate_owned(8192+128);owner[:]=0xa5
            owner[64:-64].view(np.uint32)[:]=np.asarray(replay,dtype=np.uint32);owner.flush()
            dma.write(0,4);wait_until(lambda:not(dma.read(0)&4),label='replay reset')
            dma.write(0,1);dma.write(0x18,int(owner.physical_address)+64);dma.write(0x1c,0)
            dma.write(0x28,8192)
        h.source.start();power=h.read_capture(token)
        wait_until(lambda:h.cfar.mmio.read(C.FRAME_COUNT)!=before,label='CFAR list')
        if replay is not None:
            wait_until(lambda:bool(dma.read(4)&2),label='replay completion')
            if dma.read(4)&0x70:raise RuntimeError('Replay DMA error')
            owner.invalidate()
            if not (np.all(owner[:64]==0xa5) and np.all(owner[-64:]==0xa5)):raise RuntimeError('Replay buffer boundary changed')
        h.source.stop()
        perf=h.perf.snapshot()
        if perf.status&3 or h.cfar.mmio.read(C.STATUS)&0x0c:raise RuntimeError('Overflow or framing error')
        _,targets=h.cfar.targets()
        return power,targets,perf
    finally:
        h.source.stop()
        if owner is not None:
            # Reset and await reset completion before freeing the DMA-owned allocation.
            dma.write(0,4)
            wait_until(lambda:not(dma.read(0)&4),label='replay release')
            owner.freebuffer()

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',choices=['test'],default='test')
    p.add_argument('--bit',default='/home/xilinx/sentinel/overlay/sentinel_v1/sentinel_v1.bit')
    p.add_argument('--load-overlay',action='store_true');p.add_argument('--out',default='measurements/n4_selftest.json')
    args=p.parse_args();output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'started','RF_TX_requested':False,'tests':[],'format':'int16 IQ, FFTshift 2048 bins; AVG_SHIFT=0 for exact raw power reference'}
    result['bit_sha256']=hashlib.sha256(Path(args.bit).read_bytes()).hexdigest()
    atomic_json(output,result)
    try:
        with Session(args.bit,'test',args.load_overlay) as session:
            h=session.hw;h.enable_processing(average_shift=0);h.lcd.enable();h.perf.clear()
            h.perf.arm();single,targets,perf=finite_frame(h,'test')
            peak=int(np.argmax(single));error=bin_error(peak,1088)
            result['tests'].append({'name':'single_tone','peak_bin':peak,'expected_bin':1088,'error_bins':error})
            if error>1:raise AssertionError('Single-tone peak exceeds1bin')
            triple,targets,perf=finite_frame(h,'test',(-300,64,300),(4096,4096,4096))
            peaks=[t.peak_bin for t in targets];expected=[724,1088,1324]
            result['tests'].append({'name':'three_tones','peaks':peaks,'target_count':len(targets),'expected_peaks':expected})
            if len(targets)!=3 or any(min(bin_error(x,y) for x in peaks)>1 for y in expected):raise AssertionError('Three-tone target test failed')
            root=Path('/home/xilinx/sentinel/data/reference/spectrum')
            inputs=np.array([int(x,16) for x in (root/'in_axis32.hex').read_text().split()],dtype=np.uint32).reshape(4,2048)
            golden=np.array([int(x,16) for x in (root/'exp_power_shifted.hex').read_text().split()],dtype=np.uint32).reshape(4,2048)
            actual=[]
            for i in range(4):
                power,_,perf=finite_frame(h,'replay',replay=inputs[i]);actual.append(power)
                mismatches=int(np.count_nonzero(power!=golden[i]))
                result['tests'].append({'name':'golden_replay','frame':i,'words':2048,'mismatches':mismatches})
                atomic_json(output,result)
                if mismatches:raise AssertionError('Replay power is not bit-exact')
            data=np.stack(actual);samplefile=output.with_suffix('.npz')
            atomic_write(samplefile,lambda stream:np.savez_compressed(stream,power=data,golden=golden,input_words=inputs,single_tone_power=single,triple_tone_power=triple))
            result['raw_archive_sha256']=hashlib.sha256(samplefile.read_bytes()).hexdigest()
            result['perf']=perf.__dict__;result['status']='passed'
    except BaseException as error:
        result.update(status='failed',error=str(error));raise
    finally:atomic_json(output,result)
    print(result,flush=True)

if __name__=='__main__':main()
