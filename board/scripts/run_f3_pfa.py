"""TX-disabled fixed-CFAR idle-band observations, frozen overlay only."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import sys
import time
os.environ['XILINX_XRT'] = '/usr'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ps'))
from sentinel.v2 import V2
from sentinel.app.runtime_v1 import Session
from sentinel.app.monitor_x1_guard8 import configure_checked, CONFIGURATION
from sentinel.artifacts import atomic_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit', required=True)
    p.add_argument('--library', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(output)
    os.environ['SENTINEL_RF_LIBRARY'] = args.library
    def stop(*_):
        raise KeyboardInterrupt('Graceful stop requested')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    result = dict(status='STARTED', RF_TX_requested=False, configuration=CONFIGURATION,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), bands=[])
    with open('/run/lock/zss_release_v2.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            for lo in (2305000000, 2345000000, 2385000000):
                with Session(args.bit, 'rf', False, lo, 3840000, hw_factory=V2) as session:
                    hw, radio = session.hw, session.radio
                    configure_checked(hw, radio, lo)
                    hw.lcd.set_bus_phase(2)
                    hw.lcd.enable()
                    hw.source.configure('rf', rate=3840000)
                    hw.source.start()
                    time.sleep(.1)
                    samples, seen = [], set()
                    for _ in range(100):
                        radio.check_rssi()
                        if radio.tx_atten != (89.75, 89.75) or hw.channel_health():
                            raise RuntimeError('Safety or processing fault')
                        snap = hw.cfar.snapshot(retries=12)
                        if snap.sequence not in seen:
                            seen.add(snap.sequence)
                            samples.append(dict(sequence=snap.sequence, hit_count=snap.hit_count,
                                target_count=len(snap.targets), rssi_dbm=radio.rssi(0)))
                        time.sleep(.02)
                    band = dict(lo_hz=lo, samples=samples, unmasked_bins_per_frame=2041,
                        measured_hit_fraction=sum(x['hit_count'] for x in samples)/(2041*len(samples)))
                    result['bands'].append(band)
                    print('F3_PFA', band, flush=True)
                result['gpio_after_band'] = hw.checked.registers('axi_ad9361_gpio').read(0)
                hw.src_regs.write(0, 0)
                result['source_after_band'] = hw.src_regs.read(0)
                if result['gpio_after_band'] or result['source_after_band']:
                    raise RuntimeError('Safe stop readback')
            alpha = 1974/256
            result['iid_exponential_nominal_pfa'] = (1+alpha/32)**-32
            result['scope'] = ('Observed PL hit fraction in presumed-idle antenna-connected bands. '
                'External emitters not excluded. Fixed AVG_SHIFT=3 means the iid exponential '
                'nominal reference is not a calibrated operating Pfa.')
            result['calibrated_pfa_certified'] = False
            result['status'] = 'PASS'
        except BaseException as error:
            result.update(status='FAIL', error=repr(error))
        finally:
            atomic_json(output, result)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
