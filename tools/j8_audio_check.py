"""Bounded FM diagnosis through the real host window; no recording or TX."""
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from product import app_instance
from sentinel_host.application_v61 import Window
from sentinel.release_support import write_result, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frequency', type=int, default=95800000)
    parser.add_argument('--seconds', type=int, choices=range(15, 121), default=60)
    parser.add_argument('--keep-window', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = app_instance(); w = Window(ROOT); w.show(); w.connect_board()
    report = dict(status='RUNNING', frequency_hz=args.frequency, recording=False,
                  listening='PENDING_USER', started_mono=time.monotonic())

    def save():
        report['gui_errors'] = list(w.data_errors)
        write_result(args.output/'result.json', report)

    def pump(seconds, done=lambda: False):
        end = time.monotonic()+seconds
        while time.monotonic() < end and not done():
            app.processEvents(); time.sleep(.01)
        app.processEvents()

    try:
        pump(10, lambda: bool(w.model.hello))
        if not w.model.hello: raise ConnectionError('No board hello')
        # First obtain a matching stop response even if another UI was closed.
        before = len(w.results); w.stop_feature()
        pump(12, lambda: len(w.results) > before and not w.pending)
        if len(w.results) <= before or not w.results[-1].get('restored'):
            raise RuntimeError('Initial stop not confirmed')
        before = len(w.results); w.start_feature('F8', frequency=args.frequency)
        pump(20, lambda: len(w.results) > before and not w.pending and not w.app_busy)
        if len(w.results) <= before or w.results[-1]['status'] != 'DONE':
            raise RuntimeError('FM startup failed: '+str(w.last_result))
        report['startup'] = w.results[-1]; save()
        # A listening comparison must not also scan/tune through the live UI.
        # The top-level Stop/Escape remains available throughout the check.
        for box, _, _, _ in w.cards.values(): box.setEnabled(False)
        for panel in w.app_controls.values(): panel.setEnabled(False)
        print('FM_LISTENING', args.frequency, flush=True)
        samples = {}
        for _ in range(args.seconds):
            pump(1)
            for _, sample in w.model.telemetry:
                if sample.get('scene') == 'F8':
                    samples[sample['seq']] = sample
            report['telemetry'] = list(samples.values())
            save()
        path = args.output/'F8.png'; w.grab().save(str(path))
        report['screenshot'] = dict(file=path.name, sha256=sha(path))
        values = report['telemetry']
        report['observed_muted_samples'] = sum(not t.get('audio', {}).get('output_unmuted') for t in values)
        report['max_underflows'] = max((t.get('audio', {}).get('underflows', 0) for t in values), default=None)
        counts = [t.get('audio', {}).get('pcm_samples', 0) for t in values]
        report['audio_counter_restarts'] = sum(b < a for a, b in zip(counts, counts[1:]))
        report['status'] = 'DIGITAL_CHECK_COMPLETED_LISTENING_PENDING'
    except Exception as error:
        report.update(status='FAIL', error=repr(error)); print('FM_FAILED', repr(error), flush=True)
    finally:
        before = len(w.results); w.stop_feature()
        pump(12, lambda: len(w.results) > before and not w.pending and not w.app_busy)
        report['stop'] = w.results[-1] if len(w.results) > before else None
        if not report['stop'] or not report['stop'].get('restored'):
            report['status'] = 'FAIL_STOP_UNCONFIRMED'
        save(); print('FM_FINISHED', report['status'], flush=True)
        for box, _, _, _ in w.cards.values(): box.setEnabled(True)
        for panel in w.app_controls.values(): panel.setEnabled(True)
    if args.keep_window: app.exec()
    else: w.close(); app.processEvents()


if __name__ == '__main__': main()
