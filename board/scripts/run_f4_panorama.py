"""F4 receive-only finite snapshots on the frozen 100 MHz image (Python 3.8)."""
import argparse
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=('A', 'D'), required=True)
    parser.add_argument('--antenna-confirmed', action='store_true')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--profile', choices=('legacy', 'fast'), default='legacy')
    parser.add_argument('--keep-iq', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/'ps'))
    os.environ['XILINX_XRT'] = '/usr'
    os.environ['SENTINEL_RF_LIBRARY'] = str(root/'ps/libad9361_pynq/libad9361_pynq.so')
    from sentinel.panorama_capture import (validate_request, GuardedSnapshots,
                                          scan_session, write_json)
    from sentinel.app.runtime_v1 import Session
    from sentinel.v2 import V2
    centers = validate_request(args.group, args.antenna_confirmed, args.limit, args.profile)
    args.output.mkdir(parents=True, exist_ok=False)
    result = None
    snapshots = None
    started = time.monotonic()
    try:
        bit = root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
        with Session(str(bit), source='rf', rate=3840000, lo=96050000,
                     load=False, hw_factory=V2) as session:
            if session.hw.audio.control.read(0) != 0:
                raise RuntimeError('Stop audio before raw snapshots')
            snapshots = GuardedSnapshots(session.hw.checked.registers('axi_ad9361_adc_dma'))
            result = scan_session(session, args.output, args.group, centers, snapshots,
                                  profile=args.profile, keep_iq=args.keep_iq)
        result['stopped'] = dict(gpio=session.hw.checked.registers('axi_ad9361_gpio').read(0),
                               source=session.hw.src_regs.read(0),
                               audio=session.hw.audio.control.read(0))
        if any(result['stopped'].values()):
            result.update(status='FAIL', cleanup_error='Nonzero stopped readback')
    except BaseException as error:
        if result is None:
            result = dict(status='FAIL', group=args.group, error=repr(error))
        else:
            result.update(status='FAIL', outer_error=repr(error))
    result['elapsed_s'] = time.monotonic()-started
    result['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    write_json(args.output/'result.json', result)
    print('F4_FINISHED '+result['status'], flush=True)
    if snapshots is not None and snapshots.dma.inflight:
        # Preserve CMA ownership. Recovery requires an explicit documented reset.
        print('F4_QUARANTINED_DO_NOT_RESET_DURING_TEST', flush=True)
        while True:
            time.sleep(10)
    if result['status'] != 'PASS_SNAPSHOT_SCAN':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
