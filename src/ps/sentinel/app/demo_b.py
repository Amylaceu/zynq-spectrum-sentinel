"""B-direct demo: live RX, ten OTA waveforms, RF+noise, measured performance.

This worker is launched only by the release supervisor after explicit 'yes'.
It never relabels known transmitted classes as model predictions.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import ctypes as ct
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time
import numpy as np
from ..amc.infer_np import Predictor
from ..artifacts import atomic_write
from ..capture_x5 import select_channel
from ..cma import allocate_owned
from ..dma import AdiCyclicTx
from ..drivers.regs import lcd_ctrl as L
from ..ui_v3.presenter import Presenter
from ..release_support import verify_release, write_result, sha
from ..rf.f3 import F3Radio, attenuation_steps
from ..telemetry import read_temperature_c
from ..tracker_x5 import Track
from ..v2 import V2
from .runtime_v1 import Session
from .monitor_x1_guard8 import configure_checked

SEGMENTS = ((7, 'ENVIRONMENT', 20), (5, 'TEN MOD OTA', 60),
            (6, 'QPSK RF+NOISE', 30), (8, 'PERFORMANCE', 15))
_predictor = None


def infer(model, iq):
    global _predictor
    if _predictor is None:
        _predictor = Predictor(model)
    prediction = _predictor.predict(iq, fs=480000)[0]
    return {k:prediction[k] for k in ('label', 'confidence', 'class_index', 'coarse',
                                    'top5', 'top5_scope')}


def stop_transmit_path(radio, tx, hw):
    """Mute and stop RF/DMA even when a demo segment exits with an exception."""
    if radio is None:
        # Open did not acquire radio ownership. Never disturb another owner.
        return {}, []
    errors = []

    def attempt(label, operation):
        try:
            operation()
        except BaseException as error:
            errors.append(label+': '+repr(error))

    if radio is not None:
        attempt('mute', radio.mute)
    if tx is not None:
        attempt('tx_dma_stop', lambda: tx.stop(timeout_s=.6))
    attempt('noise_amplitude_zero', lambda: hw.src_regs.write(0x20, 0))
    attempt('source_stop', lambda: hw.src_regs.write(0, 0))

    readback = {}
    if radio is not None:
        attempt('rf_stop', radio.stop)
        try:
            mode = ct.c_uint32()
            radio._check(radio.lib.z20_get_ensm_mode(ct.byref(mode)), 'ENSM stop')
            readback['ensm'] = mode.value
            readback['tx_attenuation_db'] = list(radio.tx_atten)
            if readback['ensm'] != 2 or readback['tx_attenuation_db'] != [89.75, 89.75]:
                errors.append('rf_readback: attenuation/ENSM did not return to safe state')
        except BaseException as error:
            errors.append('rf_readback: '+repr(error))
        attempt('rf_close', radio.close)

    try:
        readback['gpio_data'] = hw.checked.registers('axi_ad9361_gpio').read(0)
        readback['source_ctrl'] = hw.src_regs.read(0)
        readback['noise_amplitude'] = hw.src_regs.read(0x20)
        readback['audio_control'] = hw.audio.control.read(0)
        if any(readback[name] for name in ('gpio_data', 'source_ctrl', 'noise_amplitude', 'audio_control')):
            errors.append('pl_readback: nonzero GPIO/source/noise/audio state')
    except BaseException as error:
        errors.append('pl_readback: '+repr(error))
    return readback, errors


def prepare_performance(hw, image_reloaded=True):
    """Start a measurement epoch after loading the unchanged accepted image."""
    if hw.src_regs.read(0) & 1:
        raise RuntimeError('Stop the source before performance startup cleanup')
    if hw.checked.registers('axi_ad9361_gpio').read(0) != 0:
        raise RuntimeError('Performance segment requires RF held in reset')
    # RF is in reset: its data clock may be stopped, so the ADC-only
    # initialization helper is inappropriate here. Use the F2 full-image
    # startup path; no fault is cleared while a measurement is running.
    hw.reset_channelizer()
    hw.perf.clear()
    snapshot = hw.perf.snapshot()
    if snapshot.status & 3:
        raise RuntimeError('RX startup fault persists in performance segment')
    hw.perf.arm()
    return dict(frozen_image_reloaded=image_reloaded, initial_status=snapshot.status)


def performance_panel(right, resources, rate_hz, latency_us):
    """Render measured counters and accepted implementation resources in PS."""
    from PIL import Image, ImageDraw, ImageFont
    picture = Image.fromarray(right)
    pen = ImageDraw.Draw(picture)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', 12)
    except OSError:
        font = ImageFont.load_default()
    pen.fontmode = '1'
    pen.rectangle((0, 23, 239, 399), fill=0)
    lines = ['FROZEN 100 MHz DESIGN', 'Configured: 3.840 MSPS',
             'Measured: %.3f MSPS' % (rate_hz/1e6),
             'PL marker: '+('%.2f us' % latency_us if latency_us is not None else 'PENDING'),
             'Input -> next CFAR list', 'Not RF-to-label latency',
             'LUT: %d / 53200' % resources['Slice LUTs'],
             'FF: %d / 106400' % resources['Slice Registers'],
             'BRAM: %g / 140' % resources['Block RAM Tile'],
             'DSP: %d / 220' % resources['DSPs'], 'RF RESET / INTERNAL TEST']
    for index, line in enumerate(lines):
        pen.text((5, 28+index*24), line, font=font, fill=1 if index < 6 else 2)
    return np.asarray(picture, dtype=np.uint8)


class Display:
    def __init__(self, hw, out, segment, health, record, seconds=None, ui='v3', link=None):
        self.hw, self.out, self.segment, self.health, self.record = hw, out, segment, health, record
        self.start = self.last = time.monotonic()
        self.deadline = None if seconds is None else self.start+seconds
        self.frame = hw.lcd.registers.read(L.FRAME_COUNT)
        self.tracks, self.iq = [], None
        self.sent = 'NONE'
        self.noise_amp = 0
        self.tx_active = False
        self.mode = 'OTA RF+NOISE'
        self.performance_resources = None
        self.perf_last = None
        self.record.setdefault('telemetry', [])
        self.presenter = Presenter(hw.lcd, ui)
        self.link = link
        if self.link is not None:
            self.link.bind_presenter(self.presenter)

    def tick(self, remaining):
        state = self.health()
        fault = self.hw.channel_health()
        if fault:
            self.record['processing_fault_code'] = int(fault)
            raise RuntimeError('Processing fault during demo: %#x' % fault)
        now = time.monotonic()
        if self.deadline is not None:
            remaining = max(0, self.deadline-now)
        if now-self.last < .35:
            return
        temperature = read_temperature_c()
        if temperature is None or not 0 <= temperature < 85:
            raise RuntimeError('Temperature invalid/outside demo limit')
        frame = self.hw.lcd.registers.read(L.FRAME_COUNT)
        fps = ((frame-self.frame) & 0xffffffff)/(now-self.last)
        if fps < 1:
            raise RuntimeError('LCD stopped advancing')
        record = dict(elapsed_s=now-self.start, frame=frame, fps=fps, temperature_c=temperature,
                      tx_active=self.tx_active, noise_amp=self.noise_amp, **state)
        self.record['telemetry'].append(record)
        if self.link is not None:
            def stopping():
                raise KeyboardInterrupt('hostlink graceful stop')
            self.link.commands(self.tracks, stopping)
            self.link.update(self.tracks, telemetry=dict(record, tx_on=self.tx_active),
                             events=self.presenter.events.latest())
            self.link.service.publish('demo', group='B', segment=int(self.segment.split()[0]), title=self.segment,
                remaining_s=remaining, sent_label=self.sent,
                predicted_label=self.tracks[0].label if self.tracks else None)
        if self.performance_resources is not None:
            snapshot = self.hw.perf.snapshot()
            if snapshot.status & 3:
                raise RuntimeError('Performance fault in displayed measurement')
            old_samples, old_cycles = self.perf_last
            elapsed_cycles = snapshot.cycles-old_cycles
            rate = (snapshot.samples-old_samples)*100000000/max(1, elapsed_cycles)
            latency = snapshot.latency_cycles/100 if snapshot.status & 4 else None
            record.update(measured_sample_rate_hz=rate, pipeline_marker_us=latency,
                          performance=snapshot.__dict__)
            self.perf_last = snapshot.samples, snapshot.cycles
            self.presenter.right_transform = lambda right: performance_panel(
                right, self.performance_resources, rate, latency)
        self.presenter.present(self.tracks, iq=self.iq, selected=0, lo_hz=2450000000,
            frame=frame, fps=fps, temperature_c=temperature,
            model_status='SENT '+self.sent+' | MODEL SCORE UNCALIBRATED',
            demo_title=self.segment, demo_remaining_s=remaining,
            demo_mode='OTA TX' if self.tx_active else 'MONITOR',
            view='STAT' if self.tx_active else 'SIG', sent_label=self.sent if self.tx_active else None,
            accuracy=(sum(c['transmitted'] == c['prediction']['label'] for c in self.record.get('captures', [])),
                      len(self.record.get('captures', []))) if self.tx_active else None,
            tx_active=self.tx_active, tx_atten_db=state.get('tx_atten_db'))
        self.record['ui'] = self.presenter.summary()
        self.health()
        self.last, self.frame = now, frame

    def wait(self, deadline):
        while time.monotonic() < deadline:
            self.tick(deadline-time.monotonic())
            time.sleep(.025)


def receive_segment(root, bit, directory, seconds, record, performance=False, runtime=None, ui='v3'):
    os.environ['SENTINEL_RF_LIBRARY'] = str(root/'ps/libad9361_pynq/libad9361_pynq.so')
    # F2's tested source-mode transition reloads this exact accepted image.
    # This resets partial FFT/PFB frames and stopped-clock ADC sticky latches.
    # It does not run synthesis/place/route or modify the frozen bitstream.
    session_factory = runtime.session if runtime is not None else Session
    with session_factory(bit, 'test' if performance else 'rf', performance, 2450000000, 3840000, hw_factory=V2) as s:
        hw = s.hw
        link = None
        try:
            if performance:
                hw.audio.disable(release_pins=True)
                hw.enable_processing(average_shift=3, mode='CA', n=16, guard=8, alpha=1974,
                                     dc_mask=3, min_width_bins=2, merge_gap_bins=6)
                record['receive_startup'] = prepare_performance(hw, image_reloaded=runtime is None)
            else:
                configure_checked(hw, s.radio, 2450000000)
            hw.lcd.set_bus_phase(2); hw.lcd.enable()
            hw.source.configure('test' if performance else 'rf', rate=3840000)
            hw.source.start()
            if runtime is not None:
                runtime.wait_frames(hw)
                runtime.mark_content_started()
            def health():
                if performance:
                    if hw.checked.registers('axi_ad9361_gpio').read(0):
                        raise RuntimeError('RF reset released during performance test')
                    return dict(rf_reset=True)
                s.radio.check_rssi()
                if s.radio.tx_atten != (89.75, 89.75):
                    raise RuntimeError('Receive-only TX attenuation changed')
                return dict(tx_atten_db=89.75, rssi_dbm=s.radio.rssi(0))
            if getattr(runtime, 'hostlink_address', None):
                from .hostlink_runtime import RuntimeLink
                link = RuntimeLink(hw, bit, directory, 2450000000, mode='demo',
                    address=runtime.hostlink_address, runtime=runtime).__enter__()
            display = Display(hw, directory, '8 PERFORMANCE' if performance else '7 ENVIRONMENT', health, record, seconds, ui=ui, link=link)
            if performance:
                display.sent = 'INTERNAL TEST - NO RF'
                display.mode = 'PERFORMANCE / INTERNAL'
                acceptance = json.loads((Path(bit).parent/'acceptance.json').read_text())
                display.performance_resources = acceptance['resources']
                display.perf_last = (0, 0)
                record['resources'] = acceptance['resources']
                record['latency_scope'] = 'Internal input marker to next list, not RF-to-label latency'
            else:
                display.mode = '2.4GHz RECEIVE ONLY'
            display.wait(time.monotonic()+seconds)
        finally:
            try:
                if link is not None:
                    link.__exit__(None, None, None)
            finally:
                # Clear both enable and mode even if hostlink cleanup fails.
                hw.src_regs.write(0, 0)
                hw.src_regs.write(0x20, 0)
                record['source_after_stop'] = hw.src_regs.read(0)
    record['stop_readback'] = dict(gpio_data=hw.checked.registers('axi_ad9361_gpio').read(0),
        source_ctrl=hw.src_regs.read(0), audio_control=hw.audio.control.read(0))
    if any(record['stop_readback'].values()):
        raise RuntimeError('Receive/performance stop readback')


def transmit_segment(root, bit, directory, number, seconds, pool, record, runtime=None, ui='v3'):
    # Constructor only maps the already accepted bitstream. No reprogramming.
    if runtime is not None and runtime.hw is None:
        # Single-segment runs also download under Session's hardware lock.
        with runtime.session(bit, 'test', False, 2450000000, 3840000):
            pass
    hw = runtime._hardware(bit) if runtime is not None else V2(bit, download=False)
    if not hw.overlay.is_loaded() or any((hw.src_regs.read(0), hw.audio.control.read(0),
                                        hw.checked.registers('axi_ad9361_gpio').read(0))):
        raise RuntimeError('Existing session/overlay mismatch')
    manifest = json.loads((root/'data/f3_ota/manifest.json').read_text())
    radio, tx, owner, buf = None, None, None, None
    model = str(root/'ps/models/weights/amc_v2/round_3/model.npz')
    record['captures'] = []
    link = None
    try:
        radio = F3Radio(root/'ps/libad9361_pynq/libad9361_f3.so').open(gain=30)
        adc = hw.checked.registers('axi_ad9361')
        for channel in range(4):
            adc.write(0x400+channel*64, 0x51)
            adc.write(0x418+channel*64, 0)
            adc.write(0x4414+channel*64, 0)
            adc.write(0x4418+channel*64, 2)
        adc.write(0x4044, 1)
        radio.start(); hw.prepare_receive(); radio.health()
        configure_checked(hw, radio, 2450000000)
        hw.reset_channelizer()
        hw.source.configure('noise', rate=3840000)
        hw.src_regs.write(0x20, 0)
        if hw.src_regs.read(0x20) != 0:
            raise RuntimeError('Initial noise amplitude did not clear')
        hw.lcd.set_bus_phase(2); hw.lcd.enable(); hw.source.start()
        if runtime is not None:
            runtime.evidence['rf_initializations'] += 1
            runtime.wait_frames(hw)
        tx = AdiCyclicTx(hw.checked.registers('axi_ad9361_dac_dma'))
        if getattr(runtime, 'hostlink_address', None):
            from .hostlink_runtime import RuntimeLink
            link = RuntimeLink(hw, bit, directory, 2450000000, mode='demo',
                address=runtime.hostlink_address, runtime=runtime).__enter__()
        display = Display(hw, directory, '5 TEN MOD OTA' if number == 5 else '6 QPSK RF+NOISE', radio.health, record, seconds, ui=ui, link=link)
        entries = manifest['waveforms'] if number == 5 else [manifest['waveforms'][1]]
        for entry in entries:
            display.tracks, display.iq = [], None
            display.sent = entry['label']
            radio.health()
            path = root/'data/f3_ota'/entry['filename']
            if sha(path) != entry['sha256']:
                raise ValueError('Waveform digest mismatch')
            with np.load(path, allow_pickle=False) as data:
                words = data['words'].copy()
            if (words.shape != (262144, 4) or words.dtype != np.dtype('<i2') or words[:, 2:].any()
                    or np.abs(words.astype(np.int32)).max() > 16368 or np.any(words.astype(np.int32) % 16)):
                raise ValueError('Unsafe TX waveform')
            radio.health()
            owner = allocate_owned(words.nbytes+128); owner[:] = 0xa5
            buf = owner[64:-64]; buf.view('<i2')[:] = words.reshape(-1); owner.flush()
            tx.start(buf)
            for attenuation in attenuation_steps():
                radio.set_attenuation(attenuation)
            display.tx_active = True
            dwell = time.monotonic()+seconds/len(entries)
            amplitudes = (0,) if number == 5 else (0, 8192, 32768)
            for amplitude in amplitudes:
                noise_start = time.monotonic()
                hw.src_regs.write(0x20, amplitude)
                if hw.src_regs.read(0x20) != amplitude:
                    raise RuntimeError('Noise amplitude mismatch')
                display.noise_amp = amplitude
                radio.health(); time.sleep(.03)
                for _ in range(2):
                    hw.channel_capture.acquire(select_channel(240000), source=3, timeout_s=.6)
                    radio.health()
                packet = hw.channel_capture.acquire(select_channel(240000), source=3, timeout_s=.6)
                radio.health()
                display.iq = packet['iq']
                future = pool.submit(infer, model, packet['iq'])
                timeout = time.monotonic()+5
                while not future.done():
                    display.tick(max(0, dwell-time.monotonic()))
                    if time.monotonic() > timeout:
                        raise TimeoutError('Bounded inference worker deadline')
                    time.sleep(.025)
                prediction = future.result()
                now = time.monotonic()
                track = Track(0, 2450240000, 120000, 0, now, now)
                track.label, track.confidence = prediction['label'], float(prediction['confidence'])
                display.tracks = [track]
                display.presenter.classification(track.label)
                if link is not None:
                    link.classification(dict(track=0, prediction=track.label, score=track.confidence,
                        top5=prediction.get('top5', []), top5_scope=prediction.get('top5_scope'),
                        transmitted=entry['label'],
                        voted_label=track.label, voted_score=track.confidence,
                        votes=[[track.label, track.confidence]], frequency_hz=track.frequency_hz,
                        pl_timestamp_cycles=packet['timestamp_cycles']), packet['iq'])
                filename = 'capture_%02d.npz' % len(record['captures'])
                target = directory/filename
                atomic_write(target, lambda stream: np.savez_compressed(stream, words=packet['raw_words']))
                Path(str(target)+'.sha256').write_text(sha(target)+'  '+filename+'\n')
                radio.health()
                record['captures'].append(dict(transmitted=entry['label'], prediction=prediction,
                    noise_amp=amplitude, capture_file=filename, sha256=sha(target)))
                endpoint = dwell if number == 5 else noise_start+seconds/len(amplitudes)
                display.wait(endpoint)
            radio.mute(); display.tx_active = False
            tx.stop(timeout_s=.6)
            if not (np.all(owner[:64] == 0xa5) and np.all(owner[-64:] == 0xa5)):
                raise RuntimeError('TX DMA guard changed')
            del buf; buf = None; owner.freebuffer(); owner = None
        radio.mute(); radio.stop()
        mode = ct.c_uint32()
        radio._check(radio.lib.z20_get_ensm_mode(ct.byref(mode)), 'ENSM stop')
        record['stop_attenuation_db'], record['stop_ensm'] = radio.tx_atten, mode.value
        if radio.tx_atten != (89.75, 89.75) or mode.value != 2:
            raise RuntimeError('RF stop readback mismatch')
    finally:
        active_error = sys.exc_info()[1]
        link_error = None
        try:
            if link is not None:
                link.__exit__(None, None, None)
        except BaseException as error:
            link_error = repr(error)
        record['stop_readback'], cleanup_errors = stop_transmit_path(radio, tx, hw)
        if link_error is not None:
            cleanup_errors.append('hostlink cleanup: '+link_error)
        record['cleanup_errors'] = cleanup_errors
        quarantine = bool((tx and tx.inflight) or hw.channel_capture.engine.inflight)
        record['quarantined'] = quarantine
        if quarantine:
            write_result(directory/'result.json', dict(record, status='FAIL_QUARANTINED'))
            # The supervisor must not release potentially active DMA buffers
            # by repeatedly interrupting the retaining process.
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, signal.SIG_IGN)
            while True:
                time.sleep(1)  # retain DMA owners until documented reset recovery
        if owner is not None:
            del buf
            owner.freebuffer()
        if cleanup_errors and active_error is None:
            raise RuntimeError('Demo safe stop failed: '+'; '.join(cleanup_errors))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    p.add_argument('--hostlink', action='store_true')
    p.add_argument('--hostlink-bind')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--antenna-confirmed', choices=('yes',), required=True)
    p.add_argument('--segment', type=int, choices=(5, 6, 7, 8))
    p.add_argument('--cycles', type=int, choices=(1, 2, 3), default=1)
    p.add_argument('--isolated', action='store_true', help='Original per-segment hardware construction/download fallback')
    p.add_argument('--loop', action='store_true')
    args = p.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    verify_release(root)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    result = dict(status='STARTED', group='B', antenna='B-direct confirmed', segments=[], completed_cycles=0,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    def stop(*_):
        raise KeyboardInterrupt('Graceful stop requested')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    bit = str(root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit')
    start = time.monotonic()
    runtime = None
    if not args.isolated:
        from .runtime_v2 import SentinelRuntime
        runtime = SentinelRuntime(root)
        if args.hostlink:
            runtime.hostlink_address = args.hostlink_bind
            if not runtime.hostlink_address:
                p.error('Explicit hostlink LAN address required')
    elif args.hostlink:
        p.error('hostlink requires persistent runtime')
    result['runtime_mode'] = 'isolated' if args.isolated else 'persistent'
    selected = [s for s in SEGMENTS if args.segment is None or s[0] == args.segment]
    pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'))
    try:
        # Warm process/model before opening RF or starting its watchdog.
        pool.submit(infer, str(root/'ps/models/weights/amc_v2/round_3/model.npz'),
                    np.exp(2j*np.pi*np.arange(4096)/31).astype(np.complex64)).result(timeout=30)
        cycle = 0
        while args.loop or cycle < args.cycles:
            cycle += 1
            for number, title, seconds in selected:
                record = dict(number=number, cycle=cycle, title=title, status='STARTED')
                directory = output/('cycle_%d_segment_%d' % (cycle, number)); directory.mkdir()
                result['segments'].append(record)
                write_result(output/'demo.json', result)
                before = time.monotonic()
                try:
                    if number in (5, 6):
                        transmit_segment(root, bit, directory, number, seconds, pool, record, runtime=runtime, ui=args.ui)
                    else:
                        receive_segment(root, bit, directory, seconds, record, number == 8, runtime=runtime, ui=args.ui)
                    record['status'] = 'PASS'
                except BaseException as error:
                    record.update(status='FAIL', error=repr(error)); raise
                finally:
                    record['wall_seconds'] = time.monotonic()-before
                    write_result(directory/'result.json', record)
                    write_result(output/'demo.json', result)
                print('F3_SEGMENT', cycle, number, record['status'], record['wall_seconds'], flush=True)
            result['completed_cycles'] = cycle
        result['status'] = 'PASS'
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        try:
            pool.shutdown(wait=True)
            if runtime is not None:
                runtime.close()
                result['runtime'] = runtime.evidence
                if runtime.hw is not None:
                    result['final_stop_readback'] = runtime.stopped_readback()
        except BaseException as error:
            result.update(status='FAIL', final_cleanup_error=repr(error))
        finally:
            result['wall_seconds'] = time.monotonic()-start
            write_result(output/'demo.json', result)
    return 0 if result['status'] == 'PASS' else 1
