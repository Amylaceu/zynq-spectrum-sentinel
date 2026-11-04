"""X3 bounded measurements on accepted v1b, PYNQ 2.7 / Python 3.8.

Digital tests keep AD9361 in reset. The optional RF window is receive-only.
No existing accepted module or bitstream is replaced by this experiment.
"""
import argparse
import hashlib
import platform
from pathlib import Path
import time

import numpy as np

from .monitor_x1 import checked_bundle
from .runtime_v1 import Session
from .selftest_v1 import finite_frame
from ..artifacts import atomic_json
from ..drivers.regs import cfar_x1 as C, lcd_ctrl as L
from ..lcd_direct import draw_ui
from ..telemetry import read_temperature_c
from ..v1b import V1b

DSP_HZ = 150000000
RATE = 3840000


def system_ticks():
    """Linux aggregate CPU ticks; guest time already belongs to user/nice."""
    values = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return {'total': sum(values), 'idle': values[3] + values[4]}


def window_start():
    return {'wall': time.monotonic(), 'process': time.process_time(), 'ticks': system_ticks()}


def window_end(start):
    ticks = system_ticks()
    wall = time.monotonic() - start['wall']
    total = ticks['total'] - start['ticks']['total']
    idle = ticks['idle'] - start['ticks']['idle']
    return {'wall_s': wall, 'process_cpu_s': time.process_time() - start['process'],
            'system_busy_all_cores_percent': 100 * (total-idle) / total if total else None,
            'process_one_core_percent': 100 * (time.process_time()-start['process']) / wall,
            'cpu_ticks_before': start['ticks'], 'cpu_ticks_after': ticks}


def benchmark(function, count):
    for _ in range(5):
        function()
    window = window_start()
    values = []
    for _ in range(count):
        start = time.perf_counter()
        function()
        values.append(time.perf_counter()-start)
    return {'samples_s': values, 'window': window_end(window)}


def cpu_baselines():
    """Current vectorized CPU kernels, explicitly distinct from historical P5."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(372)
    x = (rng.normal(size=2048) + 1j*rng.normal(size=2048)).astype(np.complex64)
    power = np.rint(rng.exponential(2**18, 2048)).astype(np.uint32)
    # Same integer CA detector as sim/golden/cfar.py, no SciPy dependency.
    def detect():
        values = power.astype(np.uint64)
        left = np.zeros_like(values)
        right = np.zeros_like(values)
        for offset in range(9, 25):
            left += np.roll(values, offset)
            right += np.roll(values, -offset)
        threshold = np.minimum((((left+right) >> 5)*1974) >> 8, 0xffffffff).astype(np.uint32)
        hits = (values > threshold).astype(np.uint8)
        hits[1021:1028] = 0
        return threshold, hits
    threshold, hits = detect()
    points = [(i, int(80+60*np.sin(i*.07))) for i in range(720)]
    waterfall = Image.fromarray(rng.integers(0, 256, (200, 720, 3), dtype=np.uint8))
    def render():
        image = Image.new('RGB', (800, 480))
        ImageDraw.Draw(image).line(points, fill=(0, 255, 255))
        image.paste(waterfall, (0, 160))
        return image
    return {'seed':372, 'numpy':np.__version__, 'python':platform.python_version(),
            'detector_parameters':{'n':16, 'guard':8, 'alpha':1974, 'dc_mask':3},
            'detector_scope':'Integer CA thresholds/hits only; excludes X1 clustering/top-32',
            'detector_fixture':{'power':power.tolist(), 'threshold':threshold.tolist(), 'hits':hits.tolist()},
            'fft2048':benchmark(lambda:np.fft.fft(x), 1000),
            'cfar2048':benchmark(detect, 200),
            'pillow800x480_render_only':benchmark(render, 200),
            'render_scope':'CPU render only, no framebuffer copy/LCD transport or RX; not display fps'}


def digital(result, bit, output):
    with Session(bit, 'test', True, hw_factory=V1b) as session:
        hw = session.hw
        hw.enable_processing(average_shift=0, guard=8, min_width_bins=0)
        hw.lcd.set_bus_phase(3)
        hw.lcd.enable()
        hw.source.stop()
        time.sleep(.01)
        hw.perf.clear()
        time.sleep(.01)  # CLEAR is an asynchronous token; never arm in the same transaction.
        baseline = hw.perf.snapshot()
        if baseline.samples or baseline.markers_done or baseline.status:
            raise RuntimeError('Performance clear did not settle')
        result['latency'] = {'clock_hz':DSP_HZ, 'rate_hz':RATE, 'average_shift':0,
                             'definition':'First accepted IQ sample after arm to next list-ready pulse; includes frame acquisition',
                             'samples':[]}
        for index in range(1000):
            before = hw.perf.snapshot()
            if before.status & 0x1b:
                raise RuntimeError('Pipeline not drained before marker')
            hw.perf.arm()
            time.sleep(.001)
            offset = 32 + index % 128
            power, targets, perf = finite_frame(hw, 'test', bins=(offset,), rate=RATE)
            peak = int(np.argmax(power))
            entry = {'iteration':index, 'expected_peak_bin':1024+offset, 'peak_bin':peak,
                     'before':before.__dict__, 'after':perf.__dict__}
            result['latency']['samples'].append(entry)
            if (perf.markers_done != index+1 or perf.samples-before.samples != 2048
                    or perf.fft_frames-before.fft_frames != 1 or perf.lists-before.lists != 1
                    or perf.status != 4 or perf.latency_cycles <= 0 or peak != 1024+offset
                    or len(targets) != 1):
                raise RuntimeError('Marker/frame association or finite-tone selfcheck failed')
            if (index+1) % 100 == 0:
                atomic_json(output, result)
                print('X3_LATENCY %d/1000' % (index+1), flush=True)
        # Steady-state throughput is measured independently of the host's single-frame loop.
        hw.source.configure('test', rate=RATE)
        hw.source.start()
        try:
            time.sleep(.1)
            first = hw.perf.snapshot()
            time.sleep(3)
            last = hw.perf.snapshot()
        finally:
            hw.source.stop()
        if last.status & 3:
            raise RuntimeError('Digital throughput overflow/framing error')
        result['digital_throughput'] = {'before':first.__dict__, 'after':last.__dict__,
                                         'clock_hz':DSP_HZ, 'requested_rate_hz':RATE,
                                         'scope':'Accepted test-source IQ and post-Welch power-frame events, AVG_SHIFT=0'}


def receive_window(result, bit, seconds, output):
    with Session(bit, 'rf', True, 96400000, RATE, hw_factory=V1b) as session:
        hw, radio = session.hw, session.radio
        hw.enable_processing(average_shift=3, guard=8, min_width_bins=2, merge_gap_bins=6)
        hw.lcd.set_bus_phase(3)
        hw.lcd.enable()
        hw.source.configure('rf', rate=RATE)
        hw.source.start()
        result['receive'] = {'actual_rate_hz':radio.rate, 'actual_lo_hz':radio.rx_lo,
                             'rf_bandwidth_hz':1500000, 'bus_phase':3, 'samples':[],
                             'ui_period_s':1, 'scope':'PL spectrum/waterfall; PS updates text/list once per second'}
        start = window_start()
        previous = time.monotonic()
        frames = hw.lcd.registers.read(L.FRAME_COUNT)
        while time.monotonic()-start['wall'] < seconds:
            time.sleep(.25)
            radio.check_rssi()
            now = time.monotonic()
            if now-previous < 1:
                continue
            current = hw.lcd.registers.read(L.FRAME_COUNT)
            perf = hw.perf.snapshot()
            sample = {'elapsed_s':now-start['wall'], 'display_frames':current,
                      'display_frame_delta':(current-frames)&0xffffffff, 'interval_s':now-previous,
                      'perf':perf.__dict__, 'rssi_dbm':radio.rssi(0),
                      'tx_atten_mdb':[round(x*1000) for x in radio.tx_atten],
                      'temperature_c':read_temperature_c()}
            result['receive']['samples'].append(sample)
            if (perf.status & 3 or hw.lcd.registers.read(L.STATUS) & 0x1c
                    or hw.cfar.mmio.read(C.STATUS) & 0x0c
                    or sample['tx_atten_mdb'] != [89750,89750] or sample['rssi_dbm'] > -30
                    or sample['temperature_c'] is None or not 30 <= sample['temperature_c'] <= 85):
                raise RuntimeError('Receive safety/processing readback failed')
            try:
                snapshot = hw.cfar.snapshot(retries=8)
            except RuntimeError as error:
                if 'changed during read' not in str(error):
                    raise
                sample['snapshot_missed'] = True
            else:
                if snapshot.status_latch & 0x0c:
                    raise RuntimeError('Latched CFAR error')
                sample.update(snapshot_missed=False, list_overflow=snapshot.list_overflow)
                if hw.lcd.registers.read(L.UI_APPLIED) == hw.lcd.registers.read(L.UI_EPOCH):
                    hw.lcd.submit_ui(*draw_ui(snapshot.targets, radio.rx_lo, radio.rate,
                        page=int(sample['elapsed_s']//4), frame=current,
                        fps=sample['display_frame_delta']/sample['interval_s'],
                        overflow=int(snapshot.list_overflow), temperature_c=sample['temperature_c']))
            previous, frames = now, current
            atomic_json(output, result)
        result['receive']['cpu_window'] = window_end(start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--receive-seconds', type=int, default=30)
    args = parser.parse_args()
    if args.out.exists() or not 10 <= args.receive_seconds <= 120:
        parser.error('Choose new output and a bounded 10..120-second receive window')
    acceptance = checked_bundle(args.bit)
    result = {'status':'started', 'configuration_a_confirmed':True, 'RF_TX_requested':False,
              'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'artifacts_sha256':acceptance['artifacts_sha256'],
              'measurement_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        atomic_json(args.out, result)
        result['cpu'] = cpu_baselines()
        atomic_json(args.out, result)
        digital(result, args.bit, args.out)
        atomic_json(args.out, result)
        receive_window(result, args.bit, args.receive_seconds, args.out)
        result['status'] = 'completed'
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        atomic_json(args.out, result)
    print('X3_MEASUREMENT_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
