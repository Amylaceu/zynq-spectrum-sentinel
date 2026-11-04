"""Bounded, receive-only feature service. Frozen release remains untouched."""
import argparse
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ps'))
from sentinel.app.features_apps import ApplicationBackend as FeatureBackend
from sentinel.release_support import verify_release, write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--hostlink-bind', required=True)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--panorama-settle-ms', type=int, choices=(50, 150), default=50)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600: parser.error('Duration must be bounded')
    verify_release(ROOT)
    args.out.mkdir(parents=True, exist_ok=False)
    stopped = []
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, lambda *_: stopped.append(True))
    backend = FeatureBackend(ROOT, args.out, hostlink_bind=args.hostlink_bind,
                             stop_requested=lambda: bool(stopped))
    failure = None
    try:
        backend.start()
        backend.config['panorama_settle_s'] = args.panorama_settle_ms/1000.
        backend.baseline_config['panorama_settle_s'] = args.panorama_settle_ms/1000.
        print('J6_READY', flush=True)
        deadline = time.monotonic()+args.seconds
        while not stopped and time.monotonic() < deadline:
            backend.commands(); backend.tick(); time.sleep(.02)
    except BaseException as error:
        failure = repr(error)
        print('J6_SERVICE_FAILED '+failure, flush=True)
        raise
    finally:
        if getattr(backend, 'quarantined', None) is not None:
            backend.mute()
            backend.hw.source.stop()
            write_result(args.out/'quarantine.json', dict(status='DMA_OWNERS_RETAINED', error=failure,
                automatic_reset=False, automatic_retune=False))
            print('DMA_QUARANTINE_HOLD: do not terminate or reset before controlled recovery', flush=True)
            while True:
                time.sleep(1)
        cleanup_error = None
        try:
            backend.close()
        except BaseException as error:
            cleanup_error = repr(error)
            raise
        finally:
            write_result(args.out/'result.json', dict(features=getattr(backend, 'results', []),
                commands=getattr(backend, 'command_audit', []),
                applications=getattr(backend, 'app_results', []),
                telemetry=getattr(backend, 'samples', []),
                quality_samples=getattr(backend, 'quality_samples', []),
                tx_requested=False, closed=getattr(backend, 'closed', False),
                status='FAILED' if failure or cleanup_error else 'COMPLETED',
                error=failure, cleanup_error=cleanup_error))


if __name__ == '__main__': main()
