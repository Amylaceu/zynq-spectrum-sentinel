"""One authorized guard=8 receive-only trial; frozen X1 entry stays unchanged."""
import argparse
import math
from pathlib import Path
import signal
import time
import json

from .monitor_x1 import checked_bundle, same_frame_entry
from .runtime_v1 import Session
from ..v1b import V1b
from ..artifacts import atomic_json
from ..drivers.regs import cfar_x1 as C, spec_ctrl as F, lcd_ctrl as L
from ..lcd_direct import draw_ui
from ..telemetry import read_temperature_c


CONFIGURATION = dict(mode='CA', n=16, guard=8, average_shift=3,
                     min_width_bins=2, merge_gap_bins=6, alpha=1974,
                     mask_table=[], dc_mask=3)


def configure_checked(hw, radio, lo):
    """Configure only a stopped source; refuse to start on any readback error."""
    hw.source.stop()
    if hw.src_regs.read(0) & 1:
        raise RuntimeError('Upstream source must be stopped')
    if abs(radio.rx_lo-lo) > 5 or radio.rate != 3840000:
        raise RuntimeError('RF rate/LO readback mismatch')
    if radio.tx_atten != (89.75, 89.75):
        raise RuntimeError('TX must remain muted')
    options = dict(CONFIGURATION)
    average = options.pop('average_shift')
    hw.enable_processing(average_shift=average, **options)
    expected = {C.CTRL: 1, C.N_SHIFT: 4, C.GUARD: 8, C.ALPHA: 1974,
                C.DC_MASK: 3, C.MIN_WIDTH: 2, C.MERGE_GAP: 6, C.MASK_COUNT: 0}
    expected.update({C.MASK+4*i: 0 for i in range(16)})
    actual = {offset: hw.cfar.mmio.read(offset) for offset in expected}
    if actual != expected or hw.spec.read(F.AVG_SHIFT) != 3:
        raise RuntimeError('CFAR configuration readback mismatch')
    if hw.cfar.mmio.read(C.STATUS) & 0x0c:
        raise RuntimeError('CFAR framing/configuration error before start')
    return {hex(key): value for key, value in actual.items()}


def check_safety(entry):
    if (entry['tx_atten_mdb'] != [89750, 89750]
            or not math.isfinite(entry['rx_rssi_dbm']) or entry['rx_rssi_dbm'] > -30):
        raise RuntimeError('RF safety readback failed')
    temperature = entry['temperature_c']
    if temperature is None or not math.isfinite(temperature) or not 30 <= temperature <= 85:
        raise RuntimeError('Temperature outside accepted limits')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--lo', type=int, choices=(98000000, 96400000), required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        parser.error('Preserve prior measurements; choose a new output')
    acceptance = checked_bundle(args.bit)
    result = dict(status='started', source='rf', RF_TX_requested=False,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  requested_lo_hz=args.lo, requested_rate_hz=3840000,
                  rf_bandwidth_hz=1500000, bus_phase=3, duration_requested_s=120,
                  configuration=CONFIGURATION, artifacts_sha256=acceptance['artifacts_sha256'],
                  samples=[], telemetry_attempts=0, snapshot_misses=0,
                  authorization='User explicitly authorized one additional guard=8 joint trial',
                  alarm_denominator='Periodic same-frame snapshots; misses retained, not every CFAR frame')
    stop = [False]
    def stopping(*_):
        stop[0] = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stopping)
    try:
        atomic_json(output, result)
        with Session(args.bit, 'rf', True, args.lo, 3840000, hw_factory=V1b) as session:
            hw, radio = session.hw, session.radio
            result.update(actual_lo_hz=radio.rx_lo, actual_rate_hz=radio.rate)
            result['configuration_readback'] = configure_checked(hw, radio, args.lo)
            hw.lcd.set_bus_phase(3)
            hw.lcd.enable()
            hw.perf.clear()
            hw.perf.arm()
            hw.source.configure('rf', rate=3840000)
            hw.source.start()
            start = last = time.monotonic()
            last_frame = hw.lcd.registers.read(L.FRAME_COUNT)
            while not stop[0] and time.monotonic()-start < 120:
                time.sleep(.25)
                radio.check_rssi()
                now = time.monotonic()
                if now-last < 1:
                    continue
                perf = hw.perf.snapshot()
                frames = hw.lcd.registers.read(L.FRAME_COUNT)
                fps = ((frames-last_frame) & 0xffffffff)/(now-last)
                entry = dict(elapsed_s=now-start, display_frames=frames, display_fps=fps,
                             input_samples=perf.samples, fft_frames=perf.fft_frames,
                             overflow=bool(perf.status & 1), latency_cycles=perf.latency_cycles,
                             latency_valid=bool(perf.status & 4), temperature_c=read_temperature_c(),
                             rx_rssi_dbm=radio.rssi(0),
                             tx_atten_mdb=[round(x*1000) for x in radio.tx_atten])
                result['telemetry_attempts'] += 1
                result['samples'].append(entry)
                check_safety(entry)
                if (perf.status & 3 or hw.lcd.registers.read(L.STATUS) & 0x1c
                        or hw.cfar.mmio.read(C.STATUS) & 0x0c):
                    raise RuntimeError('Processing overflow/framing/configuration error')
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
                        raise RuntimeError('Latched CFAR framing/configuration error')
                    if hw.lcd.registers.read(L.UI_APPLIED) == hw.lcd.registers.read(L.UI_EPOCH):
                        hw.lcd.submit_ui(*draw_ui(
                            snap.targets, radio.rx_lo, radio.rate, page=int((now-start)//4),
                            frame=frames, fps=fps, overflow=int(snap.list_overflow),
                            temperature_c=entry['temperature_c']))
                atomic_json(output, result)
                print(json.dumps({key: value for key, value in entry.items() if key != 'targets'}), flush=True)
                last, last_frame = now, frames
            result['elapsed_total_s'] = time.monotonic()-start
        result.update(status='completed', stopped_by_signal=stop[0])
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        atomic_json(output, result)


if __name__ == '__main__':
    main()
