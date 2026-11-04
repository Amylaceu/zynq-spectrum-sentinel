"""Validate X0 machine evidence and explicit human display acceptance."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_json(name):
    path = ROOT/name
    sidecar = Path(str(path)+'.sha256')
    if sidecar.read_text(encoding='ascii').split()[0] != sha(path):
        raise ValueError('Evidence hash mismatch: '+name)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    refs = {
        'sd_backup': 'docs/sd_backup_verification.json',
        'monitor': 'board/measurements/n4_monitor_x0_default_temp_r2.json',
        'preflight': 'board/measurements/x0_backup_return_preflight_r1.json',
        'stop_state': 'board/measurements/x0_stop_state_r1.json',
        'visual': 'board/measurements/x0_default_temp_visual_r2.json',
        'uart': 'board/measurements/x0_backup_return_uart_r1.json',
    }
    values = {key: checked_json(name) for key, name in refs.items()}
    backup, run, stop = values['sd_backup'], values['monitor'], values['stop_state']
    require(backup['status'] == 'PASS' and backup['operator_reported_read_complete'], 'Incomplete backup')
    require(backup['image_size_bytes'] == 31266439168, 'Unexpected card size')
    require(run['status'] == 'completed' and not run['stopped_by_signal'], 'Monitor not completed normally')
    require(run['source'] == 'rf' and not run['RF_TX_requested'], 'Expected receive-only run')
    require(run['bus_phase'] == 3 and run['actual_rate_hz'] == 3840000, 'Default/rate mismatch')
    require(abs(run['actual_lo_hz']-96400000) <= 5, 'Unexpected RX frequency')
    samples = run['samples']
    require(len(samples) >= 150 and 179 <= samples[-1]['elapsed_s'] <= 181, 'Insufficient run coverage')
    require(all(b['elapsed_s'] > a['elapsed_s'] and b['display_frames'] > a['display_frames']
                for a, b in zip(samples, samples[1:])), 'Time/display counter did not progress')
    require(all(30 <= s['temperature_c'] <= 85 for s in samples), 'Temperature outside acceptance range')
    require(all(not s['overflow'] for s in samples), 'Sample FIFO overflow')
    require(all(s['tx_atten_mdb'] == [89750,89750] for s in samples), 'TX attenuation changed')
    require(all(s['rx_rssi_dbm'] <= -30 for s in samples), 'RSSI safety limit exceeded')
    require(stop['status'] == 'PASS' and stop['gpio_data'] == 0 and stop['source_ctrl'] & 1 == 0, 'Cleanup readback failed')
    require(len({run['boot_id'], stop['boot_id'], values['preflight']['boot_id']}) == 1, 'Board rebooted during test')
    visual = values['visual']
    require(visual['accepted'] and visual['measurement'] == refs['monitor'], 'Missing human display confirmation')
    tests = ROOT/'logs/X1_offline_full_tests_r3.log'
    require('215 passed' in tests.read_text(encoding='utf-8-sig'), 'Offline regression incomplete')
    old = checked_json('docs/x0_baseline_audit.json')
    for entry in old['checks']:
        require(sha(ROOT/entry['path']) == entry['expected_sha256'], 'N4 historical evidence changed: '+entry['path'])
    source_names = ['src/ps/sentinel/app/monitor.py','src/ps/sentinel/overlay.py',
                    'board/scripts/bench_lcd.py','board/scripts/zss_n4_admin.py',
                    'src/ps/sentinel/telemetry.py','board/scripts/x0_postflight.py']
    result = {
        'status': 'PASS', 'stage': 'X0',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'boot_id': run['boot_id'], 'monitor_exit_code': 0,
        'bus_phase': 3, 'default_phase_argument_omitted': True,
        'telemetry_records': len(samples), 'elapsed_last_s': samples[-1]['elapsed_s'],
        'display_fps_median': statistics.median(s['display_fps'] for s in samples),
        'temperature_min_c': min(s['temperature_c'] for s in samples),
        'temperature_max_c': max(s['temperature_c'] for s in samples),
        'sample_overflow_records': 0,
        'list_capacity_alarm_records': sum(s['list_overflow'] for s in samples),
        'list_capacity_alarm_denominator': 'Periodic telemetry records; not every CFAR frame',
        'rssi_max_dbm': max(s['rx_rssi_dbm'] for s in samples),
        'rf_gpio_after_close': stop['gpio_data'], 'source_ctrl_after_close': stop['source_ctrl'],
        'backup_image_sha256': backup['image_sha256'],
        'filesystem_health_verified': False, 'restore_tested': False,
        'filesystem_warnings_retained': values['preflight']['filesystem_warnings'],
        'pc_regression_count': 215, 'pc_regression_log_sha256': sha(tests),
        'historical_n4_hash_checks': len(old['checks']),
        'source_sha256': {name: sha(ROOT/name) for name in source_names},
        'evidence': {key: {'path': name, 'sha256': sha(ROOT/name)} for key, name in refs.items()},
        'scope': 'X0 backup/default-phase/temperature/recovery acceptance at 3.84MSPS; no X1 board or full-bandwidth acceptance',
    }
    path = ROOT/'board/measurements/x0_acceptance_r2.json'
    require(not path.exists() and not Path(str(path)+'.sha256').exists(), 'Preserve previous acceptance')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+chr(10), encoding='utf-8')
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+chr(10), encoding='ascii')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
