"""Receive-only X5 integration; explicit audited bundle, no implicit RF startup.

Latency begins at the first PS observation of a CFAR track and ends at LCD
UI_APPLIED. This is not an ADC-to-screen latency measurement: CFAR polling
and detection delay before that observation are reported as unmeasured.
"""
import argparse
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
from ..lcd_z2 import draw_ui, displayed_label
from ..telemetry import read_temperature_c
from ..tracker_x5 import TargetTracker
from ..v_z2 import VZ2
from ..ui_events import EventLog


MODEL_SHA256 = '5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish_json(path, value):
    atomic_json(path, value)
    data = (sha(path)+'  '+Path(path).name+'\n').encode('ascii')
    atomic_write(str(path)+'.sha256', lambda stream: stream.write(data))


def checked_inputs(bit, model):
    """Require a signed-by-hash PC acceptance manifest before hardware access."""
    bit, model = Path(bit), Path(model)
    path = bit.parent/'acceptance.json'
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Implementation acceptance digest mismatch')
    acceptance = json.loads(path.read_text())
    if acceptance['status'] != 'PASS' or acceptance.get('image') != 'sentinel_z2':
        raise ValueError('Require audited X5 v1d, not a prior image')
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
                  voted_label=track.label, voted_score=track.confidence,
                  votes=[list(vote) for vote in track.votes], first_label_ms=None)
    return record, capture['iq'], detail.get('symbols')


def display_result(hw, tracker, track, iq, symbols, record, lo_hz, frames, fps, temperature,
                   page, clock=time.monotonic, events=()):
    visible = tracker.visible(clock())
    if all(t.key != track.key for t in visible):
        # Do not attach a latency to a track that was omitted from the page.
        visible = [track]+visible
    selected_index = next(i for i,t in enumerate(visible) if t.key == track.key)
    selected_page = selected_index//4
    token = hw.lcd.submit_ui(*draw_ui(
        visible, selected=track.key, iq=iq, symbols=symbols, lo_hz=lo_hz,
        frame=frames, fps=fps, temperature_c=temperature, page=selected_page, events=events))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--out', required=True, help='New measurement directory')
    parser.add_argument('--lo', type=int, default=98000000)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--fm-truth-hz', type=float, nargs='*', default=[],
                        help='Independently confirmed FM station frequencies, never inferred from predictions')
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0 or not 70000000 <= args.lo <= 512000000:
        parser.error('Invalid duration/LO for configuration A')
    if any(not math.isfinite(f) or abs(f-args.lo) >= 1920000 for f in args.fm_truth_hz):
        parser.error('Truth stations must fall inside the received Nyquist interval')
    acceptance = checked_inputs(args.bit, args.model)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    result_path = output/'result.json'
    result = dict(status='started', source='rf', RF_TX_requested=False,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  image='sentinel_z2', artifacts_sha256=acceptance['artifacts_sha256'],
                  model_sha256=sha(args.model), model_status='X4 FAIL experimental candidate',
                  confidence_scope='Uncalibrated classifier score',
                  requested_lo_hz=args.lo, rate_hz=3840000, channel_rate_hz=480000,
                  bus_phase=3, duration_requested_s=args.seconds,
                  fm_truth_hz=args.fm_truth_hz, truth_tolerance_hz=25000,
                  records=[], telemetry=[], snapshot_misses=0, snapshot_attempts=0)
    tracker = TargetTracker()
    events = EventLog()
    events.add('MODE', 'RX TX OFF')
    predictor = Predictor(args.model, precision='int8')
    stop = [False]
    def stopping(*_):
        stop[0] = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stopping)
    try:
        publish_json(result_path, result)
        with Session(args.bit, 'rf', True, args.lo, 3840000, hw_factory=VZ2) as session:
            hw, radio = session.hw, session.radio
            result['configuration_readback'] = configure_checked(hw, radio, args.lo)
            hw.reset_channelizer()
            hw.lcd.set_bus_phase(3)
            hw.lcd.enable()
            hw.perf.clear()
            hw.perf.arm()
            hw.source.configure('rf', rate=3840000)
            hw.source.start()
            start = last = last_idle_ui = time.monotonic()
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
                if hw.channel_health() or hw.x5_status.read(0) & 0x1f0:
                    raise RuntimeError('Processing/capture continuity error')
                if now-last >= 1:
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
                events.observe(tracker.visible(time.monotonic()))
                track = tracker.next(time.monotonic())
                if track is None:
                    if time.monotonic()-last_idle_ui >= 1:
                        token = hw.lcd.submit_ui(*draw_ui(
                            tracker.visible(time.monotonic()), lo_hz=args.lo,
                            frame=frames, fps=fps, temperature_c=temperature, events=events.latest()))
                        hw.lcd.wait_ui(token)
                        last_idle_ui = time.monotonic()
                    time.sleep(.01)
                else:
                    record, iq, symbols = classify_one(
                        hw, predictor, tracker, track, output, len(result['records']), args.lo)
                    result['records'].append(record)
                    record['cfar_sequence'] = snap.sequence
                    events.observe(tracker.visible(time.monotonic()))
                    display_result(hw, tracker, track, iq, symbols, record, args.lo,
                                   frames, fps, temperature, 0, events=events.latest())
                    print(json.dumps(record), flush=True)
                result['ui_events'] = [dict(timestamp_utc=e.timestamp_utc, kind=e.kind, text=e.text) for e in events.latest()]
                result['summary'] = summarize(result['records'], args.fm_truth_hz, 25000)
                publish_json(result_path, result)
            result['elapsed_total_s'] = time.monotonic()-start
        result.update(status='completed', stopped_by_signal=stop[0])
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        result['summary'] = summarize(result['records'], args.fm_truth_hz, 25000)
        publish_json(result_path, result)


if __name__ == '__main__':
    main()
