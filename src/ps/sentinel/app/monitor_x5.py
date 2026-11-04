"""Receive-only X5/v2 integration; explicit audited bundle, no implicit RF startup.

Latency begins at the first PS observation of a CFAR track and ends at LCD
UI_APPLIED. This is not an ADC-to-screen latency measurement: CFAR polling
and detection delay before that observation are reported as unmeasured.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import signal
import time

import numpy as np

from .runtime_v1 import Session
from .monitor_x1_guard8 import configure_checked, check_safety
from ..amc.infer_np import Predictor
from ..artifacts import atomic_json, atomic_write
from ..capture_x5 import select_channel
from ..drivers.regs import lcd_ctrl as L
from ..drivers.regs import cfar_x1 as C
from ..lcd_x5 import draw_ui, displayed_label
from ..telemetry import read_temperature_c
from ..tracker_x5 import TargetTracker
from ..v1d import V1d
from ..v2 import V2
from ..v_y3 import checked_y3_bundle
from ..params import clock_hz_for_image
from ..listen_y3 import FMListener, validate_listen
from ..ui_v3.presenter import Presenter
from .hostlink_runtime import RuntimeLink, add_arguments as hostlink_arguments


MODEL_SHA256 = '5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish_json(path, value):
    atomic_json(path, value)
    data = (sha(path)+'  '+Path(path).name+'\n').encode('ascii')
    atomic_write(str(path)+'.sha256', lambda stream: stream.write(data))


def checked_inputs(bit, model, image='sentinel_v1d'):
    """Require a signed-by-hash PC acceptance manifest before hardware access."""
    bit, model = Path(bit), Path(model)
    if image not in ('sentinel_v1d', 'sentinel_v2_100m') or bit.stem != image:
        raise ValueError('Explicit image must match the selected bitstream')
    path = bit.parent/'acceptance.json'
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Implementation acceptance digest mismatch')
    acceptance = json.loads(path.read_text())
    if acceptance['status'] != 'PASS' or acceptance.get('image') != image:
        raise ValueError('Require independently audited '+image+' image')
    if image == 'sentinel_v2_100m':
        # Verify the explicit formal/development policy, reviewed receipt,
        # exact HWH clock and memory map before accessing hardware.
        checked_y3_bundle(bit, image=image)
    for suffix in ('bit', 'hwh'):
        item = bit.with_suffix('.'+suffix)
        if sha(item) != acceptance['artifacts_sha256'].get(item.name):
            raise ValueError('Image does not match implementation acceptance')
    if sha(model) != MODEL_SHA256:
        raise ValueError('Require frozen X4 round-3 experimental candidate')
    return acceptance


def save_capture(directory, index, capture):
    path = directory/('capture_%05d.npz' % index)
    if path.exists():
        raise FileExistsError(path)
    atomic_write(path, lambda stream: np.savez_compressed(
        stream, words=capture['raw_words'], iq=capture['iq'],
        fs_hz=np.int64(capture['fs_hz']),
        timestamp_cycles=np.uint64(capture['timestamp_cycles'])))
    digest = sha(path)
    atomic_write(str(path)+'.sha256', lambda stream: stream.write(
        (digest+'  '+path.name+'\n').encode('ascii')))
    return path.name, digest


def classify_one(hw, predictor, tracker, track, directory, index, lo_hz, clock=time.monotonic):
    """Acquire real PL data, retain it before inference, then apply per-track vote."""
    tracker.mark_attempt(track.key, clock())
    selection = select_channel(track.frequency_hz-lo_hz)
    start = clock()
    capture = hw.channel_capture.acquire(selection, source=0)
    acquired = clock()
    filename, digest = save_capture(directory, index, capture)
    infer_start = clock()
    predictions = predictor.predict(capture['iq'], fs=capture['fs_hz'])
    if len(predictions) != 1:
        raise ValueError('Expected one prediction per 4096-sample capture')
    prediction = predictions[0]
    inferred = clock()
    tracker.record(track.key, prediction, inferred)
    detail = prediction.get('detail') or {}
    record = dict(index=index, track=track.key, frequency_hz=track.frequency_hz,
                  bandwidth_hz=track.bandwidth_hz, first_seen_monotonic_s=track.first_seen,
                  capture_filename=filename, capture_sha256=digest,
                  pl_timestamp_cycles=capture['timestamp_cycles'],
                  channel=selection.channel, fcw=selection.fcw,
                  residual_hz=selection.residual_hz, capture_ms=1000*(acquired-start),
                  inference_ms=1000*(inferred-infer_start), prediction=prediction['label'],
                  coarse=prediction['coarse'], score=float(prediction['confidence']),
                  top5=prediction.get('top5', []),
                  top5_scope=prediction.get('top5_scope'),
                  voted_label=track.label, voted_score=track.confidence,
                  votes=[list(vote) for vote in track.votes], first_label_ms=None)
    return record, capture['iq'], detail.get('symbols')


def display_result(hw, tracker, track, iq, symbols, record, lo_hz, frames, fps, temperature,
                   page, clock=time.monotonic, model_status=None, ui_context=None,
                   presenter=None):
    visible = tracker.visible(clock())
    if all(t.key != track.key for t in visible):
        # Do not attach a latency to a track that was omitted from the page.
        visible = [track]+visible
    selected_index = next(i for i,t in enumerate(visible) if t.key == track.key)
    selected_page = selected_index//4
    options = dict(
        selected=track.key, iq=iq, symbols=symbols, lo_hz=lo_hz,
        frame=frames, fps=fps, temperature_c=temperature, page=selected_page,
        **(ui_context or {}),
        **({'model_status': model_status} if model_status is not None else {}))
    if presenter is not None:
        token = presenter.present(visible, **options)
        if token is None:
            record.update(ui_deferred=True, displayed_label=None, first_label_ms=None)
            return
        # STAT counts are not a displayed target label/latency measurement.
        if presenter.rendered_labels.get(track.key) != displayed_label(track):
            record.update(ui_epoch=token, displayed_label=None, first_label_ms=None)
            return
    else:
        token = hw.lcd.submit_ui(*draw_ui(visible, **options))
        hw.lcd.wait_ui(token)
    applied = clock()
    first = track.display_latency_ms is None
    if first:
        track.display_latency_ms = 1000*(applied-track.first_seen)
    record.update(ui_epoch=token, ui_applied_monotonic_s=applied,
                  first_label_ms=track.display_latency_ms if first else None,
                  displayed_label=displayed_label(track), displayed_page=selected_page)


def summarize(records, truth_hz, tolerance_hz):
    latencies = [r['first_label_ms'] for r in records if r.get('first_label_ms') is not None]
    truth = [r for r in records if any(abs(r['frequency_hz']-f) <= tolerance_hz for f in truth_hz)]
    return dict(first_observed_to_applied_median_ms=float(np.median(latencies)) if latencies else None,
                first_label_tracks=len(latencies), fm_truth_captures=len(truth),
                fm_raw_fraction=sum(r['prediction'] == 'FM' for r in truth)/len(truth) if truth else None,
                fm_voted_fraction=sum(r['voted_label'] == 'FM' for r in truth)/len(truth) if truth else None,
                fm_displayed_fraction=sum(r.get('displayed_label') == 'FM' for r in truth)/len(truth) if truth else None,
                fm_status='MEASURED' if truth else 'NOT_EVALUATED_NO_INDEPENDENT_TRUTH',
                latency_scope='First PS CFAR observation to LCD APPLIED; earlier detection delay unmeasured')


def main(argv=None, runtime=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--image', choices=('sentinel_v1d', 'sentinel_v2_100m'),
                        default='sentinel_v1d')
    parser.add_argument('--model', required=True)
    parser.add_argument('--out', required=True, help='New measurement directory')
    parser.add_argument('--lo', type=int, default=98000000)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--bus-phase', type=int, choices=(2, 3), default=3)
    parser.add_argument('--quality-station-hz', type=int,
                        help='Confirmed stereo FM for F1 startup pilot check')
    parser.add_argument('--noise-events', type=Path)
    parser.add_argument('--demo-title', help='F2 PS-only segment heading/countdown')
    parser.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    hostlink_arguments(parser)
    parser.add_argument('--listen', type=float, help='FM station Hz; v2 only, e.g. 95.8e6')
    parser.add_argument('--volume', type=float, default=-21, help='Analog OUT1/OUT2 dB')
    parser.add_argument('--fm-truth-hz', type=float, nargs='*', default=[],
                        help='Independently confirmed FM station frequencies, never inferred from predictions')
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds <= 0 or not 70000000 <= args.lo <= 512000000:
        parser.error('Invalid duration/LO for configuration A')
    if any(not math.isfinite(f) or abs(f-args.lo) >= 1920000 for f in args.fm_truth_hz):
        parser.error('Truth stations must fall inside the received Nyquist interval')
    if args.quality_station_hz is not None:
        if args.noise_events is None or not 87500000 <= args.quality_station_hz <= 108000000:
            parser.error('F1 quality check requires an FM station and evidence directory')
        select_channel(args.quality_station_hz-args.lo)
    try:
        validate_listen(args.image, args.listen, args.lo, args.volume)
    except ValueError as error:
        parser.error(str(error))
    acceptance = checked_inputs(args.bit, args.model, image=args.image)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    result_path = output/'result.json'
    result = dict(status='started', source='rf', RF_TX_requested=False,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  image=args.image, dsp_clock_hz=clock_hz_for_image(args.image),
                  artifacts_sha256=acceptance['artifacts_sha256'],
                  model_sha256=sha(args.model), model_status='X4 FAIL experimental candidate',
                  confidence_scope='Uncalibrated classifier score',
                  requested_lo_hz=args.lo, rate_hz=3840000, channel_rate_hz=480000,
                  bus_phase=args.bus_phase, duration_requested_s=args.seconds,
                  fm_truth_hz=args.fm_truth_hz, truth_tolerance_hz=25000,
                  records=[], telemetry=[], snapshot_misses=0, snapshot_attempts=0)
    result['audio'] = {'status': 'disabled'}
    audio_label = ('LISTEN %.3fM / X4 EXP / TX OFF' % (args.listen / 1e6)
                   if args.listen is not None else None)
    tracker = TargetTracker()
    predictor = (runtime.predictor(args.model, precision='int8') if runtime is not None
                 else Predictor(args.model, precision='int8'))
    stop = [False]
    presenter = None
    link = None
    def stopping(*_):
        stop[0] = True
        if runtime is not None:
            runtime.stop_requested = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stopping)
    try:
        publish_json(result_path, result)
        factory = V2 if args.image == 'sentinel_v2_100m' else V1d
        session_factory = runtime.session if runtime is not None else Session
        with session_factory(args.bit, 'rf', True, args.lo, 3840000, hw_factory=factory) as session, ExitStack() as cleanup:
            hw, radio = session.hw, session.radio
            result['receive_startup'] = getattr(session, 'receive_startup', None)
            result['configuration_readback'] = configure_checked(hw, radio, args.lo)
            hw.reset_channelizer()
            audio_cleanup = cleanup.enter_context(ExitStack())
            listener = None
            if args.listen is not None:
                listener = audio_cleanup.enter_context(FMListener(
                    hw, args.listen, args.lo, result['audio'], volume_db=args.volume))
            hw.lcd.set_bus_phase(args.bus_phase)
            hw.lcd.enable()
            presenter = Presenter(hw.lcd, args.ui)
            def fault_snapshot():
                return dict(perf=hw.perf.snapshot().__dict__,
                            pfb_capture_status=hw.x5_status.read(0),
                            cfar_status=hw.cfar.mmio.read(C.STATUS),
                            lcd_status=hw.lcd.registers.read(L.STATUS),
                            source_control=hw.src_regs.read(0))
            result['before_source_start'] = fault_snapshot()
            hw.perf.clear()
            hw.perf.arm()
            hw.source.configure('rf', rate=3840000)
            hw.source.start()
            if runtime is not None:
                runtime.wait_frames(hw)
            if args.quality_station_hz is not None:
                from ..release_support import startup_quality
                result['startup_quality'] = startup_quality(
                    hw, radio, args.quality_station_hz, args.lo, args.noise_events)
                if not result['startup_quality']['quality_pass']:
                    audio_label = 'RF NOISY - check antenna/power'
            if listener is not None:
                listener.wait_ready(radio.check_rssi)
            if args.hostlink or getattr(runtime, 'hostlink_address', None):
                link = cleanup.enter_context(RuntimeLink(hw, args.bit, output, args.lo,
                    address=args.hostlink_bind or getattr(runtime, 'hostlink_address', None),
                    mode='monitor', runtime=runtime))
                link.bind_presenter(presenter)
            start = last = last_idle_ui = time.monotonic()
            if runtime is not None:
                runtime.mark_content_started()
            def demo_ui():
                options = (dict(demo_title=args.demo_title, demo_mode='MONITOR', view='TGT',
                             demo_remaining_s=max(0, args.seconds-(time.monotonic()-start)))
                        if args.demo_title else {})
                if link is not None:
                    options['pc_connected'] = link.service.connected
                    if link.page is not None:
                        options['view'] = link.page
                return options
            def change_lo(value):
                nonlocal listener
                if not 70000000 <= value <= 512000000:
                    raise ValueError('Configuration A limits LO to 70-512 MHz; change antenna locally first')
                if args.demo_title:
                    raise ValueError('Demo frequency is owned by local segment')
                with link.paused():
                    if listener is not None:
                        audio_cleanup.close()
                        listener = None
                    hw.source.stop()
                    radio.rx_lo = value
                    configure_checked(hw, radio, value)
                    hw.prepare_receive()
                    hw.perf.arm()
                    hw.source.configure('rf', rate=3840000)
                    tracker.tracks.clear()
                    args.lo = link.lo = value
                    link.service.hello['lo_hz'] = value
                    hw.source.start()
            def remote_listen(station):
                nonlocal listener
                if args.demo_title:
                    raise ValueError('Demo audio is controlled locally')
                # A confirmed stereo station is required by the existing gate.
                config = Path(args.bit).resolve().parents[2]/'config.yaml'
                from ..release_support import load_config, startup_quality
                cfg = load_config(config)
                item = next((s for s in cfg['stations'] if s['frequency_hz'] == round(station)), None)
                if item is None:
                    raise ValueError('Station is not in confirmed stereo list')
                change_lo(item['lo_hz'])
                quality = startup_quality(hw, radio, station, args.lo, output/'noise_events')
                if not quality['quality_pass']:
                    raise ValueError('Stereo quality gate failed; remains muted')
                listener = audio_cleanup.enter_context(FMListener(hw, station, args.lo, result['audio'],
                    volume_db=cfg['volume_db']))
                listener.wait_ready(radio.check_rssi)
            last_frame = hw.lcd.registers.read(L.FRAME_COUNT)
            frames, fps = last_frame, 0.0
            while not stop[0] and time.monotonic()-start < args.seconds:
                radio.check_rssi()
                now = time.monotonic()
                temperature = read_temperature_c()
                entry = dict(elapsed_s=now-start, temperature_c=temperature,
                             rx_rssi_dbm=radio.rssi(0),
                             tx_atten_mdb=[round(x*1000) for x in radio.tx_atten])
                check_safety(entry)
                if link is not None:
                    visible = tracker.visible(now)
                    link.commands(visible, stopping, on_lo=change_lo, on_listen=remote_listen)
                    if stop[0]:
                        break
                health = hw.channel_health()
                capture_status = hw.x5_status.read(0)
                if health or capture_status & 0x1f0:
                    result['continuity_error'] = dict(health=health,
                        capture_status=capture_status, elapsed_s=now-start,
                        registers=fault_snapshot())
                    raise RuntimeError('Processing/capture continuity error')
                if now-last >= 1:
                    if listener is not None:
                        entry['audio'] = listener.sample()
                    perf = hw.perf.snapshot()
                    frames = hw.lcd.registers.read(L.FRAME_COUNT)
                    fps = ((frames-last_frame) & 0xffffffff)/(now-last)
                    entry.update(display_frames=frames, display_fps=fps,
                                 input_samples=perf.samples, fft_frames=perf.fft_frames,
                                 processing_status=perf.status)
                    result['telemetry'].append(entry)
                    last, last_frame = now, frames
                result['snapshot_attempts'] += 1
                try:
                    snap = hw.cfar.snapshot(retries=8)
                except RuntimeError as error:
                    if 'changed during read' not in str(error):
                        raise
                    result['snapshot_misses'] += 1
                    time.sleep(.01)
                    continue
                if snap.status_latch & 0x0c:
                    raise RuntimeError('Latched CFAR fault')
                tracker.update(snap.targets, args.lo, 3840000, time.monotonic())
                track = tracker.next(time.monotonic())
                if link is not None:
                    link.update(tracker.visible(time.monotonic()), telemetry=dict(entry,
                        display_fps=fps, processing_status=health, audio=result['audio'].get('status')),
                        events=presenter.events.latest())
                    if args.demo_title:
                        link.service.publish('demo', group='A', segment=2, title=args.demo_title,
                            remaining_s=max(0, args.seconds-(time.monotonic()-start)))
                    if link.selected is not None:
                        track = next((t for t in tracker.visible(time.monotonic()) if t.key == link.selected), track)
                if track is None:
                    if time.monotonic()-last_idle_ui >= .2:
                        presenter.present(
                            tracker.visible(time.monotonic()), lo_hz=args.lo,
                            frame=frames, fps=fps, temperature_c=temperature,
                            **demo_ui(),
                            **({'model_status': audio_label} if audio_label is not None else {}))
                        last_idle_ui = time.monotonic()
                    time.sleep(.01)
                else:
                    record, iq, symbols = classify_one(
                        hw, predictor, tracker, track, output, len(result['records']), args.lo)
                    result['records'].append(record)
                    record['cfar_sequence'] = snap.sequence
                    presenter.classification(record['prediction'])
                    if link is not None:
                        link.classification(record, iq)
                    display_result(hw, tracker, track, iq, symbols, record, args.lo,
                                   frames, fps, temperature, 0, model_status=audio_label,
                                   ui_context=demo_ui(), presenter=presenter)
                    print(json.dumps(record), flush=True)
                result['summary'] = summarize(result['records'], args.fm_truth_hz, 25000)
                result['ui'] = presenter.summary()
                publish_json(result_path, result)
            result['elapsed_total_s'] = time.monotonic()-start
        result.update(status='stopped_early' if stop[0] else 'completed', stopped_by_signal=stop[0])
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        if presenter is not None:
            result['ui'] = presenter.summary()
        if link is not None:
            result['hostlink'] = link.summary()
        result['summary'] = summarize(result['records'], args.fm_truth_hz, 25000)
        publish_json(result_path, result)


if __name__ == '__main__':
    main()
