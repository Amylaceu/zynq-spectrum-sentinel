"""Finite 3.84 MSPS RX PN9/delay-window regression of a loaded v2 image."""
import argparse
import ctypes as ct
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys


def window(values, position):
    if values[position] != 0:
        return 0
    low = high = position
    while low > 0 and values[low-1] == 0:
        low -= 1
    while high < 15 and values[high+1] == 0:
        high += 1
    return high-low+1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or os.geteuid() != 0:
        parser.error('Require sudo and a new evidence path')
    os.environ['XILINX_XRT'] = '/usr'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    from sentinel.v_y3 import checked_y3_bundle
    from sentinel.rf.ad9361 import AD9361
    from pynq import Overlay, MMIO
    checked_y3_bundle(args.bit, image='sentinel_v2_100m')
    with open('/run/lock/zss_ad9361.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        overlay = Overlay(str(args.bit), download=False)
        if not overlay.is_loaded():
            raise RuntimeError('Required accepted image is not loaded')
        registers = {name: MMIO(base, 4096) for name, base in
                     (('gpio', 0x41200000), ('source', 0x43c00000),
                      ('audio', 0x41260000), ('adc', 0x79020000))}
        if (registers['gpio'].read(0) != 0 or registers['source'].read(0) & 1
                or registers['audio'].read(0) != 0):
            raise RuntimeError('Prior hardware session has not stopped')
    result = dict(status='started', image='sentinel_v2_100m', sample_rate_hz=3840000,
                  rf_transmission_requested=False, audio_requested=False,
                  configuration='A',
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  bit_sha256=hashlib.sha256(args.bit.read_bytes()).hexdigest())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    radio = AD9361(lib=str(args.library))
    try:
        # The C library owns the same exclusive lock throughout open/close.
        radio.open(rate=3840000, rx_lo=96400000, bandwidth=1500000)
        radio.check_rssi()
        result['tx_attenuation_db_before'] = list(radio.tx_atten)
        if radio.rate != 3840000 or radio.tx_atten != (89.75, 89.75):
            raise RuntimeError('Unexpected RX rate or TX attenuation')
        result['pn_before'] = radio.bist_prbs(500)
        saved = radio.lib.z20_read_register(6)
        radio._check(saved, 'read RX delay')
        table = (ct.c_uint32*256)(*([0xffffffff]*256))
        radio._check(radio.lib.z20_scan_rx_delays(10, table), 'RX delay scan')
        restored = radio.lib.z20_read_register(6)
        grid = [list(table[i*16:(i+1)*16]) for i in range(16)]
        clock, data = saved >> 4, saved & 15
        result.update(saved_delay_register=saved, restored_delay_register=restored,
            status_grid_clock_rows_data_columns=grid,
            passing_points=sum(value == 0 for value in table),
            data_axis_window_at_saved_clock=window(grid[clock], data),
            clock_axis_window_at_saved_data=window([row[data] for row in grid], clock),
            observation_ms_per_point=10, settle_ms_per_point=5,
            pn_after=radio.bist_prbs(500), tx_attenuation_db_after=list(radio.tx_atten),
            adc_status=registers['adc'].read(0x5c),
            adc_clock_frequency_register=registers['adc'].read(0x54))
        if not (saved == restored and result['pn_before'] == [0]*4
                and result['pn_after'] == [0]*4
                and result['data_axis_window_at_saved_clock'] >= 3
                and result['adc_status'] & 1
                and result['adc_clock_frequency_register'] > 0
                and result['tx_attenuation_db_after'] == [89.75, 89.75]):
            raise RuntimeError('RX interface regression failed')
        result['status'] = 'PASS'
    except Exception as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        radio.close()
        result.update(gpio_after_close=registers['gpio'].read(0),
                      source_control_after=registers['source'].read(0),
                      audio_control_after=registers['audio'].read(0))
        if result['gpio_after_close'] or result['source_control_after'] & 1 or result['audio_control_after']:
            result.update(status='FAIL', cleanup_error='Hardware did not stop')
        args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        args.out.with_name(args.out.name+'.sha256').write_text(
            hashlib.sha256(args.out.read_bytes()).hexdigest()+'  '+args.out.name+'\n')
    print(json.dumps(result), flush=True)
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
