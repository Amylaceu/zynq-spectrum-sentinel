"""Measure one LCD timing phase; human visual acceptance is deliberately separate."""
import argparse,time,signal
from pathlib import Path
from sentinel.app.runtime_v1 import Session
from sentinel.drivers.regs import lcd_ctrl as L
from sentinel.artifacts import atomic_json
from sentinel.lcd_direct import draw_ui
from sentinel.telemetry import read_temperature_c

p=argparse.ArgumentParser();p.add_argument('--phase',type=int,choices=(25,12,8,6,4,3,2),default=3)
p.add_argument('--seconds',type=float,default=10);p.add_argument('--out',required=True)
p.add_argument('--hold-seconds',type=float,default=600,help='Keep this phase/source visible for human inspection; no automatic phase advance')
a=p.parse_args()
if a.seconds<10:raise ValueError('Measure at least10seconds')
output=Path(a.out);output.parent.mkdir(parents=True,exist_ok=True)
stop=[False]
def stopping(*_):stop[0]=True
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stopping)
r={'status':'started','bus_phase':a.phase,'human_visual_acceptance':'pending','RF_TX_requested':False,'source':'PL three-tone'}
try:
    with Session('/home/xilinx/sentinel/overlay/sentinel_v1/sentinel_v1.bit','test',False) as s:
        h=s.hw;h.enable_processing();h.lcd.enable();h.lcd.set_bus_phase(a.phase)
        h.source.configure('test',bins=(-300,64,300),amplitudes=(4096,4096,4096));h.source.start()
        time.sleep(2);f0=h.lcd.registers.read(L.FRAME_COUNT);start=time.monotonic();time.sleep(a.seconds)
        elapsed=time.monotonic()-start;f1=h.lcd.registers.read(L.FRAME_COUNT);p=h.perf.snapshot()
        if p.status&3 or h.lcd.registers.read(L.STATUS)&0x1c:raise RuntimeError('Processing error during benchmark')
        r.update(status='measured_pending_human',elapsed_s=elapsed,display_frames=(f1-f0)&0xffffffff,
            display_fps=((f1-f0)&0xffffffff)/elapsed,fft_frames=p.fft_frames,perf_status=p.status)
        atomic_json(output,r);print(r,flush=True)
        # A fixed three-tone spectrum looks motionless even when frames advance.
        # Publish the PL frame counter during the human inspection period.
        deadline=time.monotonic()+a.hold_seconds
        last_frame=f1;ui_updates=0;frame_advances=0
        while not stop[0] and time.monotonic()<deadline:
            time.sleep(1)
            frame=h.lcd.registers.read(L.FRAME_COUNT)
            if frame!=last_frame:frame_advances+=1
            perf=h.perf.snapshot()
            if perf.status&3 or h.lcd.registers.read(L.STATUS)&0x1c:
                raise RuntimeError("Processing error during visual hold")
            if h.lcd.registers.read(L.UI_APPLIED)==h.lcd.registers.read(L.UI_EPOCH):
                # At the full-rate test source, CFAR lists publish faster than
                # Python can make a coherent MMIO snapshot. List readout is
                # validated separately in the lower-rate RF monitor.
                h.lcd.submit_ui(*draw_ui([],98000000,30720000,
                    page=ui_updates//4,frame=frame,fps=r["display_fps"],
                    temperature_c=read_temperature_c()))
                ui_updates+=1
            last_frame=frame
            r.update(dynamic_ui_updates=ui_updates,dynamic_frame_advances=frame_advances,
                dynamic_last_frame=frame,visual_mode="PL frame counter in LCD status bar")
            atomic_json(output,r)
        h.lcd.set_bus_phase(25)
except BaseException as e:r.update(status='failed',error=str(e));raise
finally:atomic_json(output,r)
print(r,flush=True)
