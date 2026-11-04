"""Receive-only I1 service, preserving the original demo/monitor fallback."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ps'))

from sentinel.app.resident import ReceiveBackend, ResidentController
from sentinel.app.resident_control import LocalControl
from sentinel.release_support import verify_release, write_result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=3600)
    parser.add_argument('--hostlink-bind')
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 3600:
        parser.error('Bounded service duration must be 1..3600 seconds')
    verify_release(ROOT)
    args.out.mkdir(parents=True, exist_ok=False)
    controller = [None]
    stopping = [False]
    def stop(*_):
        stopping[0] = True
        if controller[0]:
            controller[0].stopping = True
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    result = dict(status='STARTED', started_utc=datetime.now(timezone.utc).isoformat(),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        tx_requested=False, arm_ota=False, antenna='S1', rate_hz=3840000,
        rf_bandwidth_hz=1500000, lifecycle='one Session until final close')
    backend = ReceiveBackend(ROOT, args.out, hostlink_bind=args.hostlink_bind,
                             stop_requested=lambda: stopping[0])
    begin = time.monotonic()
    last_save = 0.
    try:
        backend.start()
        controller[0] = owner = ResidentController(backend)
        result['startup_s'] = time.monotonic()-begin
        result['initial_readback'] = backend.readback()
        with LocalControl(owner.dispatch) as control:
            print('RESIDENT_READY '+str(args.out), flush=True)
            while not stopping[0] and not owner.stopping and time.monotonic()-begin < args.seconds:
                control.poll()
                if owner.stopping:
                    break
                backend.tick()
                if backend.link:
                    backend.link.commands(backend.tracker.visible(time.monotonic()), stop,
                                          on_scene=owner.switch)
                if time.monotonic()-last_save >= 1:
                    result.update(status='RUNNING', scene=owner.scene,
                        transitions=owner.transitions, telemetry=backend.samples,
                        classifications=backend.records, quality_samples=backend.quality_samples,
                        lifecycle=backend.runtime.evidence)
                    write_result(args.out/'result.json', result)
                    last_save = time.monotonic()
                time.sleep(.01)
        result['status'] = 'COMPLETED'
    except BaseException as error:
        result.update(status='FAILED', error=repr(error))
        raise
    finally:
        try:
            if controller[0]:
                controller[0].close()
            else:
                backend.close()
        except BaseException as error:
            result.update(status='FAILED_CLEANUP', cleanup_error=repr(error))
            raise
        finally:
            result.update(elapsed_s=time.monotonic()-begin,
                telemetry=backend.samples, classifications=backend.records,
                quality_samples=backend.quality_samples,
                transitions=controller[0].transitions if controller[0] else [],
                lifecycle=backend.runtime.evidence if backend.runtime else None)
            write_result(args.out/'result.json', result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
