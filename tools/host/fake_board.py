"""Deterministic synthetic hostlink source. Never imports hardware drivers."""
import argparse
from pathlib import Path
import sys
import threading
import time
import hashlib
from types import SimpleNamespace
import zlib

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src/ps'),str(ROOT/'tools/host')]
from sentinel.app.hostlink import Hostlink
from sentinel_host.session import Replay
from sentinel.ui_v3.state import UIState
from sentinel.ui_v3.layout import draw_ui_v3, resolve_hit, PAGES
from sentinel.lcd_x5 import pack_ui


class FakeBoard:
    def __init__(self, port=0, session=None):
        self.service = Hostlink('127.0.0.1', dict(spectrum_source='synthetic-test',
            sample_rate_hz=3840000,lo_hz=96050000,fft_size=2048,protocol='hostlink/1'),
            allow_loopback=True,tcp_port=port,http_port=0)
        self.session = session
        self.stop = threading.Event()
        self.ui_state = UIState()

    def __enter__(self):
        self.service.start()
        self.thread = threading.Thread(target=self.run,daemon=True)
        self.thread.start()
        return self

    def __exit__(self,*_):
        self.stop.set()
        self.thread.join(2)
        self.service.close()

    def run(self):
        if self.session:
            previous = 0
            for elapsed,header,payload in Replay(self.session):
                if self.stop.wait(max(0,elapsed-previous)):
                    return
                previous = elapsed
                if header['type'] == 'hello':
                    continue
                fields = {k:v for k,v in header.items() if k not in ('type','seq','t_mono','len')}
                self.service.publish(header['type'],payload,**fields)
            return
        index = 0
        track = SimpleNamespace(key=1, frequency_hz=95800000, bandwidth_hz=150000,
            power=40000, label='FM', confidence=.8, first_seen=0, votes=[])
        while not self.stop.is_set():
            x = np.arange(1024)
            data = (1500+4000*np.exp(-((x-(445+4*np.sin(index/10)))/8)**2)).astype('<i2')
            self.service.publish('spectrum',data.tobytes(),lo_hz=96050000,
                frequency_start_hz=94130000,bin_spacing_hz=3750,
                sample_rate_hz=3840000,spectrum_source='synthetic-test',frame_range=[index,index])
            trace = (data.astype(np.int32)*256//100).astype('<i2')
            edges = np.arange(561)*1024//560
            trace = np.maximum.reduceat(trace, edges[:-1])
            self.service.publish('pl_frame', zlib.compress(trace.tobytes()), profile='x5_frozen',
                codec='zlib-i16le-q88', lo_hz=96050000, source='synthetic-test')
            if index % 2 == 0:
                self.service.publish('detections',targets=[dict(key=1,frequency_hz=95800000,
                    bandwidth_hz=150000,power=40000,label='FM',confidence=.8,first_seen_mono=0)])
            if index % 5 == 0:
                iq = np.exp(2j*np.pi*np.arange(512)/31).astype('<c8')
                self.service.publish('iq',iq.tobytes(),target_key=1)
                self.service.publish('amc',track=1,prediction='FM',score=.8,
                    top5=[dict(label=a, score=b) for a,b in
                          [('FM',.8),('AM',.1),('QPSK',.05),('BPSK',.03),('GFSK',.02)]])
            if index % 10 == 0:
                self.service.publish('telemetry',display_fps=40,temperature_c=50,
                    rx_rssi_dbm=-80,tx_on=False,cpu_single_core_pct=50,rss_bytes=50*1024**2,
                    ps_cpu_pct=42.5, ps_memory_bytes=312*1024**2)
                self.service.publish('event',event_kind='SYNTHETIC',text='Offline test only')
            for _ in range(8):
                request = self.service.poll()
                if request is None:
                    break
                try:
                    _, _, name, args = request
                    if name == 'click':
                        hit = resolve_hit(args['x'], args['y'], [track], self.ui_state.view or 'SIG')
                        action = hit['action']
                        self.ui_state.change(action, hit['rect'], [request[0], request[1]])
                        if action.startswith('tab:'):
                            self.ui_state.view = action.split(':')[1]
                        elif action.startswith('card:') or action == 'spectrum':
                            self.ui_state.selected = 1
                        elif action == 'soft:NEXT':
                            self.ui_state.view = PAGES[(PAGES.index(self.ui_state.view or 'SIG')+1) % 3]
                    elif name == 'set_page':
                        self.ui_state.view = args['page']
                    elif name == 'select_target':
                        self.ui_state.selected = args['key']
                    self.service.reply(request,synthetic=True)
                except ValueError as error:
                    self.service.reply(request, ok=False, error=str(error))
            state = self.ui_state.snapshot()
            right, status = draw_ui_v3([track], view=self.ui_state.view or 'SIG',
                selected=self.ui_state.selected, frame=index, fps=40, temperature_c=50,
                lo_hz=96050000, demo_title='SYNTHETIC TEST', ui_state=state)
            raw = pack_ui(right, status).astype('<u4').tobytes()
            self.service.publish('ui_state', **state)
            self.service.publish('ui_frame', zlib.compress(raw), epoch=index,
                sha256=hashlib.sha256(raw).hexdigest(), source='synthetic-test', request=state['request'])
            index += 1
            self.stop.wait(.095)


def preview_packets():
    """Fixed-seed offline fixtures. Never imported by the real board runtime.

    Source and synthetic flags persist in the headers, screenshots and reports.
    These PCM samples exercise the display only; they are not an FM recording.
    """
    rng = np.random.default_rng(20261104)
    yield dict(type='hello', t_mono=0., mode='monitor', spectrum_source='synthetic-test',
               sample_rate_hz=3840000, lo_hz=96400000), b''
    frequencies = [95800000, 96450000, 97100000]
    tracks = [SimpleNamespace(key=i+1, frequency_hz=f, bandwidth_hz=150000,
        power=40000-i*6000, label=['FM','QPSK','AM'][i], confidence=[.86,.73,.61][i],
        first_seen=0, votes=[]) for i,f in enumerate(frequencies)]
    targets = [dict(key=t.key, frequency_hz=t.frequency_hz, bandwidth_hz=t.bandwidth_hz,
                    power=t.power, label=t.label, confidence=t.confidence, first_seen_mono=0)
               for t in tracks]
    for frame in range(80):
        x = np.arange(1024)
        power = 1700+rng.normal(0,65,1024)
        for center, height in [(352,4800),(525,3600),(700,2600)]:
            power += height*np.exp(-((x-center-2*np.sin(frame/10))/7)**2)
        yield dict(type='spectrum',t_mono=frame/10,lo_hz=96400000,
            frequency_start_hz=94480000,bin_spacing_hz=3750), power.astype('<i2').tobytes()
        edges = np.arange(561)*1024//560
        trace = np.maximum.reduceat((power*256/100).astype('<i2'),edges[:-1])
        yield dict(type='pl_frame', t_mono=frame/10, profile='x5_frozen',
                   lo_hz=96400000,source='synthetic-test'),zlib.compress(trace.tobytes())
        yield dict(type='detections', t_mono=frame/10,targets=targets),b''
        if frame % 4 == 0:
            labels=['AM','FM','BPSK','QPSK','8PSK','16QAM','64QAM','GFSK','CPFSK','PAM4']
            sent=labels[(frame//4)%10]
            predicted='FM' if frame in (12,28) else sent
            yield dict(type='amc',t_mono=frame/10,track=2,prediction=predicted,score=.73,
                       transmitted=sent,synthetic=True), b''
        yield dict(type='telemetry',t_mono=frame/10,display_fps=40+.5*np.sin(frame/8),
            temperature_c=49+frame/120,rx_rssi_dbm=-72+np.sin(frame/9),tx_on=False,
            ps_cpu_pct=42.5,ps_memory_bytes=312*1024**2), b''
    yield dict(type='amc',t_mono=8.,track=1,prediction='FM',score=.86,
        top5=[dict(label=a,score=b) for a,b in [('FM',.86),('AM',.07),('QPSK',.04),('GFSK',.02),('BPSK',.01)]]),b''
    iq=(np.exp(2j*np.pi*np.arange(512)/31)+.04*(rng.normal(size=512)+1j*rng.normal(size=512))).astype('<c8')
    yield dict(type='iq',t_mono=8.,target_key=1),iq.tobytes()
    for i,kind in enumerate(['NEW','LOCK','MOD CHG','SNAP']):
        yield dict(type='event',t_mono=5.+i,event_kind=kind,text='离线合成示例',target_key=1),b''
    yield dict(type='audio',t_mono=8.,source='ps_parallel_demod',synthetic=True,
               sample_rate_hz=48000,sample_start=0), (3000*np.sin(2*np.pi*np.arange(960)/48)).astype('<i2').tobytes()
    state=UIState();state.selected=1;state.view='TGT'
    snapshot=state.snapshot()
    right,status=draw_ui_v3(tracks,view='TGT',selected=1,iq=iq,frame=800,fps=40,
        temperature_c=50,lo_hz=96400000,demo_title='SYNTHETIC PREVIEW',ui_state=snapshot,now=8.)
    raw=pack_ui(right,status).astype('<u4').tobytes()
    yield dict(type='ui_state',t_mono=8.,**snapshot), b''
    yield dict(type='ui_frame',t_mono=8.,epoch=800,sha256=hashlib.sha256(raw).hexdigest(),
               source='synthetic-test'),zlib.compress(raw)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=9000)
    p.add_argument('--session',help='Replay a verified .zsr as hostlink data')
    args=p.parse_args()
    try:
        with FakeBoard(port=args.port,session=args.session) as fake:
            print('SYNTHETIC TEST SERVER 127.0.0.1:%d'%fake.service.tcp_port,flush=True)
            while not fake.stop.wait(.5):
                pass
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
