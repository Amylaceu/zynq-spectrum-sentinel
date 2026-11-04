"""Real data adapter. Network has no MMIO; power sampler has an exclusive lease.

The sampler alone owns power capture_ctrl/BRAM during this context. It never
touches RF, IQ DMA, CFAR configuration or audio. Close before releasing hardware.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import threading
import time
import zlib
import uuid

import numpy as np

from .hostlink import Hostlink
from ..drivers.regs import lcd_ctrl as L
from ..release_support import write_result
from ..telemetry import SystemMetrics


def add_arguments(parser):
    parser.add_argument('--hostlink', action='store_true')
    parser.add_argument('--hostlink-bind', help='Explicit board LAN IPv4 (or SENTINEL_HOSTLINK_BIND)')


def power_packet(words):
    values = np.asarray(words)
    if values.shape != (2048,) or values.dtype.kind != 'u':
        raise ValueError('Expected 2048 unsigned PL power bins')
    peaks = values.reshape(1024, 2).max(axis=1)
    return np.clip(np.rint(1000*np.log10(np.maximum(peaks, 1))), -32768, 32767).astype('<i2').tobytes()


class RuntimeLink:
    def __init__(self, hw, bit, output, lo_hz, mode='monitor', address=None, token=None, runtime=None):
        self.hw, self.output, self.lo = hw, Path(output), lo_hz
        self.mode = mode
        self.runtime = runtime
        hello = dict(bit_sha256=hashlib.sha256(Path(bit).read_bytes()).hexdigest(),
            release_version='v2', boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            sample_rate_hz=3840000, lo_hz=lo_hz, fft_size=2048,
            spectrum_source='pl_power_snapshot', power_reference='raw_integer_power',
            power_unit='0.01 dB re integer 1', frame_mapping='LCD frame bracket, exact FFT frame unverified',
            end_to_end_latency='NOT_CERTIFIED', mode=mode)
        existing = getattr(runtime, 'hostlink_service', None)
        self.service = existing or Hostlink(address or os.environ.get('SENTINEL_HOSTLINK_BIND', ''),
            hello, mode='resident' if mode == 'resident' else 'demo' if runtime is not None else mode,
            token=token or os.environ.get('SENTINEL_HOSTLINK_TOKEN'))
        if existing:
            self.service.hello = dict(hello, protocol='hostlink/1')
        self.stop = threading.Event()
        self.capture_lock = threading.Lock()
        self.thread = None
        self.error = None
        self.samples = self.capture_time_s = 0
        self.started = self.last_detection = self.last_telemetry = 0.
        self.last_iq = 0.
        self.latest_power = None
        self.latest_iq = None
        self.selected = self.page = None
        self.events_sent = set()
        self.capture_timings = []
        self.last_cpu = None
        self.system_metrics = SystemMetrics()
        self.presenter = None
        self.ui_state = None
        self.readback_records = []
        self.ui_frames = 0
        self._readback_rng = np.random.RandomState(20261104)
        self._readback_next = 1

    def bind_presenter(self, presenter):
        from ..ui_v3.state import UIState
        self.presenter = presenter
        self.ui_state = UIState()
        presenter.ui_state = self.ui_state
        presenter.on_applied = self._ui_applied

    def _ui_applied(self, presenter, epoch, right, status):
        from ..display_twin import submitted_frame, decompress_exact, UI_BYTES
        self.ui_frames += 1
        verify = len(self.readback_records) < 20 and self.ui_frames >= self._readback_next
        payload, fields = submitted_frame(self.hw.lcd, right, status, epoch, readback=verify)
        state = self.ui_state.snapshot()
        fields.update(ui_revision=state['revision'], request=state['request'],
                      applied_mono=time.monotonic(), view=presenter.current_view)
        if verify:
            directory = self.output/'host_twin'
            directory.mkdir(exist_ok=True)
            path = directory/('epoch_%010d.u32' % epoch)
            path.write_bytes(decompress_exact(payload, UI_BYTES))
            Path(str(path)+'.sha256').write_text(fields['sha256']+'  '+path.name+'\n')
            self.readback_records.append(dict(fields, file=str(path.relative_to(self.output))))
            self._readback_next = self.ui_frames+int(self._readback_rng.randint(1, 6))
        self.service.publish('ui_frame', payload, **fields)
        self.service.publish('ui_state', **state)

    def __enter__(self):
        if self.service._thread is None:
            self.service.start()
        if self.runtime is not None:
            self.runtime.hostlink_service = self.service
        self.started = time.monotonic()
        self.thread = threading.Thread(target=self._sample, name='sentinel-power-owner', daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        if self.thread:
            self.thread.join(2)
            if self.thread.is_alive():
                raise RuntimeError('Power sampler still owns hardware')
        if self.runtime is None:
            self.service.close()
        write_result(self.output/'hostlink.json', self.summary())

    @contextmanager
    def paused(self):
        """Owner takes this lease before stopping/reconfiguring the receive source."""
        with self.capture_lock:
            yield

    def _sample(self):
        next_due = time.monotonic()
        try:
            while not self.stop.is_set():
                if self.stop.wait(max(0, next_due-time.monotonic())):
                    break
                with self.capture_lock:
                    if self.stop.is_set():
                        break
                    begin = time.monotonic()
                    first = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
                    token = self.hw.arm_capture()
                    deadline = begin+.5
                    while (self.hw.capture_ctrl.read(8) & 1) != token:
                        if time.monotonic() >= deadline:
                            raise TimeoutError('Power capture acknowledgement timeout')
                        time.sleep(.001)
                    if self.hw.capture_ctrl.read(8) & 2:
                        raise RuntimeError('Power capture framing fault')
                    if hasattr(self.hw.capture, 'array'):
                        words = np.asarray(self.hw.capture.array[:2048], dtype='<u4').copy()
                    else:
                        words = np.asarray([self.hw.capture.read(i*4) for i in range(2048)], dtype='<u4')
                    last = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
                    stamp = time.monotonic()
                    payload = power_packet(words)
                    self.latest_power = (words, stamp, first, last, self.lo)
                    self.service.publish('spectrum', payload, lo_hz=self.lo, sample_rate_hz=3840000,
                        frequency_start_hz=self.lo-1920000, bin_spacing_hz=3750,
                        capture_started_mono=begin, capture_completed_mono=stamp,
                        frame_range=[first, last], frame_mapping='LCD bracket; FFT frame unverified',
                        power_reference='raw_integer_power', power_unit='0.01dB re integer 1')
                    from ..display_twin import power_q88
                    trace = power_q88(words)
                    self.service.publish('pl_frame', zlib.compress(trace.tobytes(), 1),
                        profile='x5_frozen', codec='zlib-i16le-q88', columns=560,
                        lo_hz=self.lo, sample_rate_hz=3840000, frame_range=[first, last],
                        spectrum_source='sampled_power_snapshot', waterfall_source='sampled_trace_history',
                        threshold_source='UNAVAILABLE_NO_MMIO_READBACK', peak_source='NOT_PRESENT_IN_FROZEN_LCD',
                        lcd_frame_exact=False)
                    self.samples += 1
                    duration = time.monotonic()-begin
                    self.capture_time_s += duration
                    if len(self.capture_timings) < 40000:
                        self.capture_timings.append(duration*1000)
                next_due += .1
                if next_due < time.monotonic():
                    next_due = time.monotonic()+.1
        except BaseException as error:
            self.error = error

    def summary(self):
        elapsed = max(.001, time.monotonic()-self.started)
        return dict(self.service.summary(), spectrum_samples=self.samples,
                    spectrum_hz=self.samples/elapsed, elapsed_s=elapsed,
                    capture_total_s=self.capture_time_s, capture_ms=self.capture_timings,
                    capture_error=repr(self.error) if self.error else None,
                    network_cpu_single_core_pct=100*self.service.stats['cpu_s']/elapsed,
                    ui_frames=self.ui_frames, ui_readback_records=self.readback_records,
                    end_to_end_latency='NOT_CERTIFIED_NO_EXACT_PL_FRAME_MAPPING')

    def classification(self, record, iq):
        fields = {k:v for k,v in record.items() if k in ('track', 'prediction', 'score',
                   'voted_label', 'voted_score', 'votes', 'frequency_hz', 'pl_timestamp_cycles',
                   'transmitted', 'top5', 'top5_scope')}
        self.service.publish('amc', **fields)
        now = time.monotonic()
        data = np.asarray(iq[:512], dtype='<c8').copy()
        if len(data) == 512:
            self.latest_iq = (data, now, record['track'])
            if now-self.last_iq >= .5 and (self.selected is None or self.selected == record['track']):
                self.service.publish('iq', data.tobytes(), target_key=record['track'],
                    sample_rate_hz=480000, observed_mono=now,
                    capture_timestamp_cycles=record.get('pl_timestamp_cycles'), samples=512)
                self.last_iq = now

    def update(self, tracks=(), telemetry=None, events=()):
        if self.error is not None:
            raise RuntimeError('hostlink power acquisition failed') from self.error
        if self.service._error is not None:
            raise RuntimeError('hostlink service failed') from self.service._error
        now = time.monotonic()
        targets = [dict(key=t.key, frequency_hz=t.frequency_hz, bandwidth_hz=t.bandwidth_hz,
            power=t.power, first_seen_mono=t.first_seen, label=t.label if t.confidence >= .5 else '?',
            confidence=t.confidence) for t in tracks]
        if now-self.last_detection >= .2:
            self.service.publish('detections', targets=targets)
            self.last_detection = now
        if telemetry is not None and now-self.last_telemetry >= 1:
            self.service.status = dict(telemetry, lo_hz=self.lo, mode=self.mode)
            self.service.status.setdefault('tx_on', False)
            cpu = os.times()
            total = cpu.user+cpu.system
            cpu_percent = None if self.last_cpu is None else 100*(total-self.last_cpu[1])/(now-self.last_cpu[0])
            self.last_cpu = (now, total)
            try:
                rss_pages = int(Path('/proc/self/statm').read_text().split()[1])
                rss_bytes = rss_pages*os.sysconf('SC_PAGE_SIZE')
            except (OSError, ValueError, IndexError, AttributeError):
                rss_bytes = None
            self.service.status.update(cpu_single_core_pct=cpu_percent, rss_bytes=rss_bytes,
                **self.system_metrics.sample(),
                hostlink={k:v for k,v in self.service.summary().items()
                          if k not in ('rejections', 'thread_error')})
            self.service.publish('telemetry', **self.service.status)
            self.last_telemetry = now
        for event in events:
            key = (event.timestamp_utc, event.kind, event.text)
            if key not in self.events_sent:
                self.service.publish('event', timestamp_utc=key[0], event_kind=key[1], text=key[2])
                self.events_sent.add(key)
        if len(self.events_sent) > 128:
            self.events_sent = {(e.timestamp_utc, e.kind, e.text) for e in events}

    def commands(self, tracks, on_stop, on_lo=None, on_listen=None, on_scene=None):
        for _ in range(8):
            request = self.service.poll()
            if request is None:
                break
            _, _, name, args = request
            try:
                fields = {}
                if name == 'get_status':
                    fields['status'] = dict(self.service.status)
                elif name == 'ping':
                    fields['board_mono'] = time.monotonic()
                elif name == 'stop':
                    on_stop()
                elif name == 'scene':
                    if on_scene is None:
                        raise ValueError('Resident scene controller unavailable')
                    fields['scene'] = on_scene(args['id'])
                elif name == 'set_page':
                    self.page = args['page']
                    if self.ui_state is not None:
                        self.ui_state.view = self.page
                        self.ui_state.change('tab:'+self.page, request=[request[0], request[1]])
                elif name == 'select_target':
                    if args['key'] not in {t.key for t in tracks}:
                        raise ValueError('Target no longer visible')
                    self.selected = args['key']
                    if self.ui_state is not None:
                        self.ui_state.selected = self.selected
                        self.ui_state.change('card:'+str(self.selected), request=[request[0], request[1]])
                elif name == 'click':
                    fields.update(self.click(args['x'], args['y'], tracks, request, on_listen))
                elif name == 'listen_target':
                    self.listen_target(args['key'], tracks, on_listen)
                elif name == 'snapshot':
                    fields['snapshot'] = self.snapshot()
                elif name == 'set_lo':
                    if on_lo is None:
                        raise ValueError('LO change unavailable in current segment')
                    on_lo(int(round(args['hz'])))
                    fields['lo_hz'] = self.lo
                elif name == 'listen':
                    if on_listen is None:
                        raise ValueError('Listening unavailable in current segment')
                    on_listen(args['mhz']*1e6)
                if self.ui_state is not None and name in ('click', 'set_page', 'select_target', 'listen_target'):
                    self.presenter.present(tracks, force=True)
                    fields.update(ui_revision=self.ui_state.revision, ui_epoch=self.presenter.last_token)
                self.service.reply(request, **fields)
            except (ValueError, FileNotFoundError) as error:
                self.service.reply(request, ok=False, error=str(error))

    def listen_target(self, key, tracks, on_listen):
        target = next((t for t in tracks if t.key == key), None)
        if (target is None or target.label != 'FM' or target.confidence < .5
                or not 87500000 <= target.frequency_hz <= 108000000):
            raise ValueError('Listening requires a visible identified FM target')
        if on_listen is None:
            raise ValueError('Listening unavailable in current segment')
        on_listen(target.frequency_hz)
        if self.ui_state is not None:
            self.ui_state.listening = True

    def click(self, x, y, tracks, request, on_listen=None):
        if self.presenter is None:
            raise ValueError('Current segment has no interactive presenter')
        from ..ui_v3.layout import resolve_hit
        state = self.ui_state
        hit = resolve_hit(x, y, tracks, self.presenter.current_view or 'SIG', state.page)
        action = hit['action']
        state.hint = ''
        state.change(action, hit['rect'], [request[0], request[1]])
        if action.startswith('tab:'):
            self.page = state.view = action.split(':')[1]
        elif action.startswith('card:'):
            self.selected = state.selected = int(action.split(':')[1])
        elif action == 'spectrum':
            frequency = self.lo-1920000+x*3840000/560
            if not tracks:
                raise ValueError('No visible target to select')
            self.selected = state.selected = min(tracks, key=lambda t: abs(t.frequency_hz-frequency)).key
            self.page = state.view = 'TGT'
        elif action == 'soft:NEXT':
            from ..ui_v3.layout import PAGES
            self.page = state.view = PAGES[(PAGES.index(self.presenter.current_view or 'SIG')+1) % 3]
        elif action == 'soft:SNAP':
            state.hint = 'SAVED '+self.snapshot()
        elif action == 'soft:LISTEN':
            try:
                self.listen_target(state.selected, tracks, on_listen)
            except ValueError as error:
                state.hint = str(error)
                self.presenter.present(tracks, force=True)
                raise
        elif action == 'soft:REC':
            state.hint = 'PCM recording unavailable in this segment'
            self.presenter.present(tracks, force=True)
            raise ValueError(state.hint)
        return dict(action=action)

    def snapshot(self):
        power, iq = self.latest_power, self.latest_iq
        if power is None:
            raise ValueError('No completed power snapshot yet')
        directory = self.output/'host_snapshots'/uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        path = directory/'samples.npz'
        data = dict(power=power[0], power_observed_mono=power[1], lo_hz=power[4])
        if iq is not None:
            data.update(iq=iq[0], iq_observed_mono=iq[1], target_key=iq[2])
        np.savez_compressed(str(path), **data)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        Path(str(path)+'.sha256').write_text(digest+'  '+path.name+'\n')
        write_result(directory/'snapshot.json', dict(power_frame_range=list(power[2:4]),
            file=path.name, sha256=digest, coherent_iq_power=False,
            scope='Independent IQ and power captures; timestamps retained'))
        return str(directory.relative_to(self.output))
