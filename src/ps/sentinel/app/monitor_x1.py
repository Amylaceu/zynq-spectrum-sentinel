"""X1 receive-only comparison with same-frame CFAR metadata and raw evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import time

from .runtime_v1 import Session
from ..v1b import V1b
from ..artifacts import atomic_json
from ..drivers.regs import lcd_ctrl as L, cfar_x1 as C
from ..lcd_direct import draw_ui
from ..telemetry import read_temperature_c


def checked_bundle(bit):
    bit = Path(bit)
    acceptance = json.loads((bit.parent/'acceptance.json').read_text())
    if acceptance.get('status') != 'PASS' or acceptance.get('cfar_version') != C.VERSION_VALUE:
        raise RuntimeError('A routed, audited X1 artifact bundle is required')
    for suffix in ('bit','hwh','xsa'):
        path = bit.with_suffix('.'+suffix)
        if hashlib.sha256(path.read_bytes()).hexdigest() != acceptance['artifacts_sha256'].get(path.name):
            raise RuntimeError('Accepted artifact hash mismatch: '+path.name)
    return acceptance


def same_frame_entry(snapshot):
    return {'cfar_sequence': snapshot.sequence, 'status_latch': snapshot.status_latch,
            'hit_count': snapshot.hit_count, 'raw_count': snapshot.raw_count,
            'filtered_count': snapshot.filtered_count, 'candidate_count': snapshot.candidate_count,
            'list_overflow': snapshot.list_overflow,
            'targets': [t.__dict__ for t in snapshot.targets]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--lo', type=int, choices=(98000000,96400000), required=True)
    p.add_argument('--seconds', type=int, default=120)
    p.add_argument('--average-shift', type=int, default=3)
    p.add_argument('--min-width', type=int, default=2)
    p.add_argument('--merge-gap', type=int, default=6)
    p.add_argument('--alpha', type=int, default=1974)
    p.add_argument('--mask', action='append', default=[], help='Inclusive start:stop FFT bins')
    p.add_argument('--capture-power', action='store_true', help='Save one real power frame for diagnostics')
    args = p.parse_args()
    output = Path(args.out)
    if output.exists():
        p.error('Preserve prior measurements; choose a new output')
    if not 10 <= args.seconds <= 300 or not 0 <= args.average_shift <= 15:
        p.error('Invalid duration or averaging')
    if not 0 <= args.min_width <= 2048 or not 0 <= args.merge_gap <= 255 or not 0 <= args.alpha <= 65535:
        p.error('Invalid CFAR parameter')
    try:
        masks = [tuple(map(int, item.split(':'))) for item in args.mask]
        if len(masks) > 16 or any(len(pair)!=2 or not 0 <= pair[0] <= pair[1] < 2048 for pair in masks):
            raise ValueError('Invalid mask')
    except ValueError:
        p.error('Masks require inclusive bins start:stop within 0..2047')
    acceptance = checked_bundle(args.bit)
    result = {'status':'started', 'source':'rf', 'RF_TX_requested':False,
              'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'requested_lo_hz':args.lo, 'requested_rate_hz':3840000,
              'rf_bandwidth_hz':1500000, 'bus_phase':3, 'duration_requested_s':args.seconds,
              'configuration':{'average_shift':args.average_shift,'min_width_bins':args.min_width,
                               'merge_gap_bins':args.merge_gap,'alpha':args.alpha,'mask_table':masks,'dc_mask':3},
              'artifacts_sha256':acceptance['artifacts_sha256'],
              'samples':[], 'telemetry_attempts':0, 'snapshot_misses':0,
              'alarm_denominator':'Periodic same-frame snapshots; misses retained, not every CFAR frame'}
    stop = [False]
    def stopping(*_):
        stop[0] = True
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig, stopping)
    try:
        atomic_json(output,result)
        with Session(args.bit,'rf',True,args.lo,3840000,hw_factory=V1b) as session:
            h, radio = session.hw, session.radio
            result.update(actual_lo_hz=radio.rx_lo, actual_rate_hz=radio.rate)
            h.enable_processing(average_shift=args.average_shift, min_width_bins=args.min_width,
                                merge_gap_bins=args.merge_gap, alpha=args.alpha, mask_table=masks)
            h.lcd.set_bus_phase(3)
            h.lcd.enable()
            h.perf.clear()
            h.perf.arm()
            h.source.configure('rf',rate=3840000)
            h.source.start()
            if args.capture_power:
                token = h.arm_capture()
                result['diagnostic_power_frame'] = h.read_capture(token).tolist()
            start = last = time.monotonic()
            last_frame = h.lcd.registers.read(L.FRAME_COUNT)
            while not stop[0] and time.monotonic()-start < args.seconds:
                time.sleep(.25)
                radio.check_rssi()
                now = time.monotonic()
                if now-last < 1:
                    continue
                perf = h.perf.snapshot()
                frames = h.lcd.registers.read(L.FRAME_COUNT)
                fps = ((frames-last_frame)&0xffffffff)/(now-last)
                result['telemetry_attempts'] += 1
                entry = {'elapsed_s':now-start,'display_frames':frames,'display_fps':fps,
                         'input_samples':perf.samples,'fft_frames':perf.fft_frames,
                         'overflow':bool(perf.status&1),'latency_cycles':perf.latency_cycles,
                         'latency_valid':bool(perf.status&4),'temperature_c':read_temperature_c(),
                         'rx_rssi_dbm':radio.rssi(0),
                         'tx_atten_mdb':[round(x*1000) for x in radio.tx_atten]}
                result['samples'].append(entry)
                if perf.status&3 or h.lcd.registers.read(L.STATUS)&0x1c or h.cfar.mmio.read(C.STATUS)&0x0c:
                    raise RuntimeError('Processing overflow/framing/configuration error')
                if entry['tx_atten_mdb'] != [89750,89750] or entry['rx_rssi_dbm'] > -30:
                    raise RuntimeError('RF safety readback failed')
                if entry['temperature_c'] is None or not 30 <= entry['temperature_c'] <= 85:
                    raise RuntimeError('Temperature outside accepted limits')
                try:
                    snap = h.cfar.snapshot(retries=8)
                except RuntimeError as error:
                    if 'changed during read' not in str(error):
                        raise
                    result['snapshot_misses'] += 1
                    entry.update(snapshot_available=False,snapshot_error=str(error))
                else:
                    entry.update(snapshot_available=True,**same_frame_entry(snap))
                    if snap.status_latch&0x0c:
                        raise RuntimeError('Latched CFAR framing/configuration error')
                    if h.lcd.registers.read(L.UI_APPLIED)==h.lcd.registers.read(L.UI_EPOCH):
                        pixels = draw_ui(snap.targets,radio.rx_lo,radio.rate,page=int((now-start)//4),
                                         frame=frames,fps=fps,overflow=int(snap.list_overflow),
                                         temperature_c=entry['temperature_c'])
                        h.lcd.submit_ui(*pixels)
                atomic_json(output,result)
                print(json.dumps({k:v for k,v in entry.items() if k!='targets'}),flush=True)
                last, last_frame = now, frames
            result['elapsed_total_s'] = time.monotonic()-start
        result.update(status='completed',stopped_by_signal=stop[0])
    except BaseException as error:
        result.update(status='failed',error=str(error))
        raise
    finally:
        atomic_json(output,result)


if __name__ == '__main__':
    main()
