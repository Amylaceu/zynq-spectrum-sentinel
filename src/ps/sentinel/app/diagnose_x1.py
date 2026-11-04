"""Finite, paired X1 power/list capture; continuous-reception metrics stay separate.

One input FFT frame produces one IIR-Welch output, even with AVG_SHIFT=3.
FRAME_LIMIT drains unselected RF in src_mux. No accepted source is modified.
"""
import argparse
import hashlib
from pathlib import Path
import signal
import time

import numpy as np

from .monitor_x1 import checked_bundle, same_frame_entry
from .runtime_v1 import Session
from ..artifacts import atomic_json, atomic_write
from ..drivers.regs import cfar_x1 as C, spec_ctrl as F, src_ctrl as S
from ..telemetry import read_temperature_c
from ..v1 import wait_until
from ..v1b import V1b


def check_pair(before, after, input_frames, input_samples, spec_after, perf_delta):
    """Reject skipped/extra frames, stale snapshots, and incomplete source drains."""
    expected = (before + input_frames) & 0xffffffff
    if (after != expected or spec_after != expected or input_samples != 2048 * input_frames
            or perf_delta != (2048 * input_frames, input_frames, input_frames)):
        raise RuntimeError('Finite frame association failed: ' + repr(
            (before, after, input_frames, input_samples, spec_after, perf_delta)))


def check_rf_readback(lo, rate):
    """Allow at most 5 Hz LO rounding, consistent with the observed 2 Hz offset.

    This is a register-readback guard, not the station detection tolerance.
    Preserve the actual frequency for all subsequent frequency calculations.
    """
    if abs(lo - 96400000) > 5 or rate != 3840000:
        raise RuntimeError('RF configuration readback mismatch: LO=%r rate=%r' % (lo, rate))
    return {'actual_lo_hz': lo, 'actual_rate_hz': rate}


def finite_capture(hw, mode, frames=1, capture=True, tone_bin=64):
    if capture and frames != 1:
        raise ValueError('Captured power must be the sole frame in this burst')
    hw.source.stop()
    before = hw.cfar.snapshot().sequence
    if hw.spec.read(F.FRAME_CNT) != before or hw.cfar.mmio.read(C.STATUS) & 3:
        raise RuntimeError('Upstream must be drained before finite capture')
    perf_before = hw.perf.snapshot()
    hw.source.configure(mode, rate=3840000, frames=frames, bins=(tone_bin,))
    wait_until(lambda: hw.src_regs.read(S.FRAME_CNT) == 0 and
               hw.src_regs.read(S.SAMPLE_CNT) == 0, label='source rearm')
    token = hw.arm_capture() if capture else None
    # ARM toggle crosses to the DSP domain. Leave a quiet interval before input.
    time.sleep(.005)
    try:
        hw.source.start()
        expected = (before + frames) & 0xffffffff
        wait_until(lambda: hw.cfar.mmio.read(C.FRAME_COUNT) == expected,
                   timeout=3, label='finite CFAR publication')
        hw.source.stop()
        power = hw.read_capture(token, timeout=1) if capture else None
        time.sleep(.01)
        snapshot = hw.cfar.snapshot()
        perf = hw.perf.snapshot()
        actual_frames = hw.src_regs.read(S.FRAME_CNT)
        delta = (perf.samples - perf_before.samples,
                 (perf.fft_frames - perf_before.fft_frames) & 0xffffffff,
                 (perf.lists - perf_before.lists) & 0xffffffff)
        if actual_frames != frames:
            raise RuntimeError('Source emitted an unexpected frame count')
        check_pair(before, snapshot.sequence, frames, hw.src_regs.read(S.SAMPLE_CNT),
                   hw.spec.read(F.FRAME_CNT), delta)
        if perf.status & 3 or snapshot.status_latch & 0x0c or hw.cfar.mmio.read(C.STATUS) & 0x0f:
            raise RuntimeError('Overflow, framing, configuration, or undrained pipeline')
        return power, snapshot, {'cfar_before': before, 'source_frames': actual_frames,
            'source_samples': hw.src_regs.read(S.SAMPLE_CNT),
            'spec_sequence': hw.spec.read(F.FRAME_CNT), 'perf_delta': list(delta),
            'capture_token': token, 'perf_status': perf.status}
    finally:
        hw.source.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source', choices=('test', 'rf'), required=True)
    parser.add_argument('--frames', type=int, default=96)
    args = parser.parse_args()
    if not 4 <= args.frames <= 128:
        parser.error('Expected 4..128 paired frames')
    output, archive = args.out, args.out.with_suffix('.npz')
    if output.exists() or archive.exists():
        parser.error('Preserve prior diagnostic evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    acceptance = checked_bundle(args.bit)
    result = {'status': 'started', 'source': args.source, 'RF_TX_requested': False,
        'scope': 'Finite gated input; not a continuous RF acceptance run',
        'antenna': 'thin/short 20-512MHz, long feedline; user-confirmed optimal antenna' if args.source == 'rf' else None,
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'configuration': {'average_shift': 3, 'mode': 'CA', 'n': 16, 'guard': 2,
            'alpha': 1974, 'dc_mask': 3, 'min_width_bins': 2, 'merge_gap_bins': 6, 'mask_table': []},
        'lo_hz': 96400000, 'rate_hz': 3840000, 'rf_bandwidth_hz': 1500000,
        'artifacts_sha256': acceptance['artifacts_sha256'],
        'requested_frames': args.frames, 'warmup_frames': 64, 'samples': [],
        'threshold_hit_origin': 'Not captured in hardware; PC golden reconstruction only'}
    powers = []
    def stop(*_):
        raise InterruptedError('Diagnostic interrupted; close the exclusive session')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    try:
        atomic_json(output, result)
        with Session(args.bit, args.source, True, 96400000, 3840000, hw_factory=V1b) as session:
            hw, radio = session.hw, session.radio
            hw.enable_processing(average_shift=3)
            hw.lcd.set_bus_phase(3)
            hw.lcd.enable()
            hw.perf.clear()
            time.sleep(.01)
            def safety():
                temp = read_temperature_c()
                if temp is None or not 30 <= temp <= 85:
                    raise RuntimeError('Invalid SOC temperature')
                entry = {'temperature_c': temp}
                if radio is not None:
                    radio.check_rssi()
                    if radio.tx_atten != (89.75, 89.75):
                        raise RuntimeError('TX attenuation mismatch')
                    entry.update(check_rf_readback(radio.rx_lo, radio.rate))
                    entry.update(rx_rssi_dbm=radio.rssi(0), tx_atten_mdb=[89750, 89750])
                return entry
            safety()
            _, _, result['warmup_association'] = finite_capture(hw, args.source, frames=64, capture=False)
            start = time.monotonic()
            for index in range(args.frames):
                before_safety = safety()
                # Alternating tones in digital test exercise stale-frame rejection.
                tone = (64, -300, 300, -128)[index % 4] if args.source == 'test' else 64
                power, snapshot, association = finite_capture(hw, args.source, tone_bin=tone)
                metadata = safety()
                metadata.update(safety_before=before_safety, test_tone_bin=tone if args.source == 'test' else None)
                powers.append(power)
                result['samples'].append(dict(metadata, index=index, elapsed_s=time.monotonic()-start,
                    association=association, **same_frame_entry(snapshot)))
                atomic_json(output, result)
                print('PAIRED_FRAME %d sequence=%d targets=%d' % (index, snapshot.sequence, len(snapshot.targets)), flush=True)
                if args.source == 'rf':
                    time.sleep(.20)
            result['elapsed_s'] = time.monotonic() - start
        result['status'] = 'completed'
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        if powers:
            atomic_write(archive, lambda stream: np.savez_compressed(stream, power=np.stack(powers)))
            result['raw_archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        atomic_json(output, result)


if __name__ == '__main__':
    main()
