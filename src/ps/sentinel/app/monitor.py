"""PL spectrum/CFAR monitor with fixed SSD1963 UI (no RF transmit)."""
import argparse,time,signal
from pathlib import Path
from .runtime_v1 import Session
from ..lcd_direct import draw_ui
from ..drivers.regs import lcd_ctrl as L
from ..artifacts import atomic_json
from ..telemetry import read_temperature_c

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bit',default='/home/xilinx/sentinel/overlay/sentinel_v1/sentinel_v1.bit')
    p.add_argument('--source',choices=['rf','test','replay'],default='test')
    p.add_argument('--lo',type=float,default=98e6);p.add_argument('--rate',type=float,default=3.84e6)
    p.add_argument('--bus-phase',type=int,default=3);p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--load-overlay',action='store_true');p.add_argument('--out',default='measurements/n4_monitor.json')
    args=p.parse_args()
    if not 1<=args.bus_phase<=255 or args.seconds<=0:p.error('Invalid bus phase or duration')
    result={'status':'started','source':args.source,'RF_TX_requested':False,'bus_phase':args.bus_phase,
            'requested_lo_hz':args.lo,'requested_rate_hz':args.rate,
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'samples':[]}
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    stop=[False]
    def stopping(*_):stop[0]=True
    for s in (signal.SIGINT,signal.SIGTERM):signal.signal(s,stopping)
    try:
        # Persist the startup checkpoint before any overlay or MMIO access.
        # A stalled board must not look like a test that was never launched.
        atomic_json(output,result)
        with Session(args.bit,args.source,args.load_overlay,args.lo,args.rate) as session:
            if session.radio is not None:
                result['actual_lo_hz']=session.radio.rx_lo
                result['actual_rate_hz']=session.radio.rate
            h=session.hw;h.enable_processing();h.lcd.set_bus_phase(args.bus_phase);h.lcd.enable()
            h.perf.clear();h.perf.arm()
            replay=None;replay_index=0
            if args.source=='replay':
                import numpy as np
                from .selftest_v1 import finite_frame
                replay=np.array([int(x,16) for x in Path('/home/xilinx/sentinel/data/reference/spectrum/in_axis32.hex').read_text().split()],dtype=np.uint32).reshape(-1,2048)
                result['replay_pacing']='Finite frames scheduled by PS; not a continuous real-time RF stream'
            else:
                h.source.configure(args.source,rate=args.rate,bins=(-300,64,300),amplitudes=(4096,4096,4096));h.source.start()
            start=last=time.monotonic();last_frames=h.lcd.registers.read(L.FRAME_COUNT)
            while not stop[0] and time.monotonic()-start<args.seconds:
                if replay is not None:
                    finite_frame(h,'replay',replay=replay[replay_index%len(replay)],rate=args.rate);replay_index+=1
                else:time.sleep(.25)
                now=time.monotonic()
                if session.radio is not None:session.radio.check_rssi()
                if now-last<1:continue
                perf=h.perf.snapshot();frames=h.lcd.registers.read(L.FRAME_COUNT)
                fps=((frames-last_frames)&0xffffffff)/(now-last)
                sequence,targets=h.cfar.targets(retries=8)
                temperature=read_temperature_c()
                if perf.status&3 or h.lcd.registers.read(L.STATUS)&0x1c or h.cfar.mmio.read(0x34)&0x0c:raise RuntimeError('Processing overflow/framing error')
                if h.lcd.registers.read(L.UI_APPLIED)==h.lcd.registers.read(L.UI_EPOCH):
                    h.lcd.submit_ui(*draw_ui(targets,args.lo,args.rate,page=int((now-start)//4),frame=frames,fps=fps,overflow=perf.status&1,temperature_c=temperature))
                entry={'elapsed_s':now-start,'display_frames':frames,'display_fps':fps,'fft_frames':perf.fft_frames,
                    'input_samples':perf.samples,'cfar_sequence':sequence,'targets':[t.__dict__ for t in targets],
                    'list_overflow':bool(h.cfar.mmio.read(0x34)&0x10),'overflow':bool(perf.status&1),'latency_cycles':perf.latency_cycles,'latency_valid':bool(perf.status&4),
                    'temperature_c':temperature}
                if session.radio is not None:
                    atten=session.radio.tx_atten
                    if atten!=(89.75,89.75):raise RuntimeError('TX attenuation changed')
                    entry['tx_atten_mdb']=[round(x*1000) for x in atten]
                    entry['rx_rssi_dbm']=session.radio.rssi(0)
                result['samples'].append(entry);atomic_json(output,result)
                print(entry,flush=True);last,last_frames=now,frames
            result['status']='completed';result['stopped_by_signal']=stop[0]
    except BaseException as error:
        result.update(status='failed',error=str(error));raise
    finally:atomic_json(output,result)

if __name__=='__main__':main()
