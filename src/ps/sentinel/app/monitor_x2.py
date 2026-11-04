"""Finite receive-only X2 bandwidth acceptance, absolute loss counters retained."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import statistics
import time

from .monitor_x1 import checked_bundle as checked_v1b_bundle, same_frame_entry
from .monitor_x1_guard8 import CONFIGURATION, check_safety
from .runtime_x2 import SessionX2, RATES
from ..artifacts import atomic_json
from ..drivers.regs import cfar_x1 as C, spec_ctrl as F, lcd_ctrl as L
from ..drivers.stream_x2 import VERSION_VALUE
from ..lcd_direct import draw_ui
from ..telemetry import read_temperature_c


def checked_bundle(bit):
    path = Path(bit).parent / 'acceptance.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('X2 implementation acceptance hash mismatch')
    acceptance = checked_v1b_bundle(bit)
    if acceptance.get('stream_version') != VERSION_VALUE:
        raise ValueError('An audited X2 stream statistics contract is required')
    return acceptance


def configure_processing(hw):
    hw.source.stop()
    if hw.src_regs.read(0) & 1:
        raise RuntimeError('Source must be stopped')
    options = dict(CONFIGURATION)
    average = options.pop('average_shift')
    hw.enable_processing(average_shift=average, **options)
    expected = {C.CTRL: 1, C.N_SHIFT: 4, C.GUARD: 8, C.ALPHA: 1974,
                C.DC_MASK: 3, C.MIN_WIDTH: 2, C.MERGE_GAP: 6, C.MASK_COUNT: 0}
    expected.update({C.MASK + 4*i: 0 for i in range(16)})
    actual = {offset: hw.cfar.mmio.read(offset) for offset in expected}
    if actual != expected or hw.spec.read(F.AVG_SHIFT) != average or hw.spec.read(F.DISP_DECIM) != 1:
        raise RuntimeError('X2 processing configuration readback mismatch')
    return {hex(k): v for k, v in actual.items()}


def drain(hw, timeout=3):
    hw.source.stop()
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        time.sleep(.02)
        snap = hw.stream.snapshot()
        snap.require_lossless()
        if (snap.frames_in == snap.frames_out + snap.frame_drop
                and snap.frames_in == hw.cfar.mmio.read(C.FRAME_COUNT) + snap.frame_drop
                and previous is not None and snap.frames_in == previous.frames_in):
            return snap
        previous = snap
    raise TimeoutError('X2 source/pipeline did not drain with exact frame conservation')


def check_processing(hw, perf):
    """Return checked status flags, including errors latched during drain."""
    flags = dict(perf_status=perf.status,
                 lcd_status=hw.lcd.registers.read(L.STATUS),
                 cfar_status=hw.cfar.mmio.read(C.STATUS))
    if flags['perf_status'] & 3 or flags['lcd_status'] & 0x1c or flags['cfar_status'] & 0x0c:
        raise RuntimeError('X2 processing overflow/framing error')
    return flags


def check_rssi_owned(radio):
    """Keep the RF flock until Session stops PL and then closes the radio."""
    for channel in (0, 1):
        radio.guard.check_rssi(radio.rssi(channel))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--rate', required=True, type=int, choices=tuple(RATES))
    parser.add_argument('--seconds', type=int, choices=(60, 600), default=600)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Preserve prior measurements')
    acceptance = checked_bundle(args.bit)
    result = dict(status='started', RF_TX_requested=False, source='rf',
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  requested_rate_hz=args.rate, requested_rf_bandwidth_hz=RATES[args.rate],
                  requested_lo_hz=98000000, duration_requested_s=args.seconds, bus_phase=3,
                  test_scope='screening_60s' if args.seconds == 60 else 'sustained_600s',
                  configuration=CONFIGURATION, artifacts_sha256=acceptance['artifacts_sha256'],
                  samples=[], snapshot_misses=0,
                  counter_policy='Absolute saturated loss counters; no masking or baseline subtraction',
                  spectral_coverage_note='Digital span is Fs; analog RF bandwidth is the configured filter bandwidth')
    stop = [False]
    def stopping(*_):
        stop[0] = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stopping)
    try:
        atomic_json(args.out, result)
        with SessionX2(args.bit, rate=args.rate) as session:
            hw, radio = session.hw, session.radio
            result.update(actual_rate_hz=radio.rate, actual_lo_hz=radio.rx_lo,
                          actual_rf_bandwidth_hz=radio.bandwidth)
            result['configuration_readback'] = configure_processing(hw)
            hw.lcd.set_bus_phase(3)
            hw.lcd.enable()
            hw.perf.clear()
            hw.perf.arm()
            hw.source.configure('rf', rate=args.rate)
            initial = previous = hw.stream.snapshot()
            result['initial_stream'] = initial.__dict__
            initial.require_lossless()
            if initial.frames_in or initial.frames_out or initial.frame_drop:
                raise RuntimeError('New image must begin with zero frame counters')
            hw.source.start()
            start = last = time.monotonic()
            last_frame = hw.lcd.registers.read(L.FRAME_COUNT)
            perf_before = hw.perf.snapshot()
            while not stop[0] and time.monotonic()-start < args.seconds:
                time.sleep(.20)
                check_rssi_owned(radio)
                now = time.monotonic()
                if now-last < 1:
                    continue
                stream = hw.stream.snapshot()
                perf = hw.perf.snapshot()
                frames = hw.lcd.registers.read(L.FRAME_COUNT)
                fps = ((frames-last_frame) & 0xffffffff)/(now-last)
                entry = dict(elapsed_s=now-start, stream=stream.__dict__,
                             display_frames=frames, display_fps=fps,
                             input_samples=perf.samples, fft_frames=perf.fft_frames,
                             latency_cycles=perf.latency_cycles, perf_status=perf.status,
                             temperature_c=read_temperature_c(), rx_rssi_dbm=radio.rssi(0),
                             tx_atten_mdb=[round(x*1000) for x in radio.tx_atten])
                result['samples'].append(entry)
                stream.require_lossless()
                stream.require_monotonic(previous)
                check_safety(entry)
                entry.update(check_processing(hw, perf))
                try:
                    snap = hw.cfar.snapshot(retries=8)
                except RuntimeError as error:
                    if 'changed during read' not in str(error):
                        raise
                    result['snapshot_misses'] += 1
                    entry.update(snapshot_available=False, snapshot_error=str(error))
                else:
                    entry.update(snapshot_available=True, **same_frame_entry(snap))
                    if snap.status_latch & 0x0c:
                        raise RuntimeError('Latched CFAR framing error')
                    if hw.lcd.registers.read(L.UI_APPLIED) == hw.lcd.registers.read(L.UI_EPOCH):
                        hw.lcd.submit_ui(*draw_ui(snap.targets, radio.rx_lo, radio.rate,
                            page=int((now-start)//4), frame=frames, fps=fps,
                            overflow=int(snap.list_overflow), temperature_c=entry['temperature_c']))
                atomic_json(args.out, result)
                print(json.dumps({k: v for k, v in entry.items() if k != 'targets'}), flush=True)
                last, last_frame, previous = now, frames, stream
            end = time.monotonic()
            perf_after = hw.perf.snapshot()
            final = drain(hw)
            result['final_processing_status'] = check_processing(hw, hw.perf.snapshot())
            check_rssi_owned(radio)
            final.require_monotonic(previous)
            result.update(elapsed_total_s=end-start, final_stream=final.__dict__,
                          stopped_by_signal=stop[0], input_samples_begin=perf_before.samples,
                          input_samples_end=perf_after.samples,
                          measured_samples_per_second=(perf_after.samples-perf_before.samples)/(end-start),
                          median_display_fps=statistics.median(s['display_fps'] for s in result['samples']))
            if stop[0] or end-start < args.seconds:
                raise RuntimeError('Measurement window interrupted')
            if abs(result['measured_samples_per_second']/args.rate-1) > .01:
                raise RuntimeError('Measured sample throughput differs by more than 1%')
            if result['median_display_fps'] < 15:
                raise RuntimeError('Median display rate below 15 fps')
        result['status'] = 'completed'
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        atomic_json(args.out, result)


if __name__ == '__main__':
    main()
