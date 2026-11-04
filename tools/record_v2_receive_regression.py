"""Summarize immutable 100 MHz RX receipts without changing old failures."""
import statistics

from x2_transport import ROOT, sha, verified, write_evidence


def main():
    directory = ROOT / 'board/measurements'
    execution = verified(directory / 'v2_x5_station_r3_execution.json')
    result = verified(directory / 'v2_x5_station_r3/result.json')
    telemetry = result.get('telemetry', [])
    startup = result.get('receive_startup') or {}
    paths = [directory / (name + '.json') for name in (
        'y3_v2_selftest_r1_execution', 'y3_v2_rx_interface_r1_execution',
        'v2_x5_station_r1_execution', 'v2_x5_station_r2_execution',
        'v2_x5_station_r3_execution')]
    evidence = {p.relative_to(ROOT).as_posix():
                dict(status=verified(p)['status'], sha256=sha(p)) for p in paths}
    checks = dict(
        execution=execution['status'] == 'PASS_EXECUTION',
        completed=result['status'] == 'completed',
        duration=result.get('elapsed_total_s', 0) >= 120,
        raw_packets=bool(execution.get('capture_checks'))
                    and len(execution['capture_checks']) == len(result['records']),
        startup_clean=startup.get('perf_after', {}).get('status', 3) & 3 == 0,
        sample_fifo_clean=bool(telemetry) and all(
            t['processing_status'] & 3 == 0 for t in telemetry),
        tx_muted=bool(telemetry) and all(t['tx_atten_mdb'] == [89750, 89750]
                                      for t in telemetry),
        safe_receive=bool(telemetry) and all(t['rx_rssi_dbm'] <= -30 for t in telemetry),
        stopped=execution.get('postflight', {}).get('status') == 'PASS',
    )
    receipt = dict(
        status='PASS_FUNCTIONAL_RX' if all(checks.values()) else 'FAIL_FUNCTIONAL_RX',
        scope='100 MHz migration functional regression; not Y2 accuracy acceptance',
        checks=checks, image=result['image'], configuration='A',
        elapsed_s=result.get('elapsed_total_s'), captures=len(result['records']),
        telemetry_count=len(telemetry),
        display_fps_median=statistics.median(t['display_fps'] for t in telemetry)
                           if telemetry else None,
        display_fps_min=min((t['display_fps'] for t in telemetry), default=None),
        temperature_c_range=[min(t['temperature_c'] for t in telemetry),
                             max(t['temperature_c'] for t in telemetry)] if telemetry else None,
        classifier_summary=result['summary'], receive_startup=startup,
        human_visual=dict(status='PASS', source='User reply in this chat',
            statement='计数增加、频谱瀑布更新、列表和点图正常'),
        retained_failures=['X1', 'X2', 'X3', 'X4', 'Y2', 'Z10 +1ns', 'T5 +1ns'],
        evidence=evidence,
        result_sha256=sha(directory / 'v2_x5_station_r3/result.json'),
        tests_sha256=sha(ROOT / 'logs/Y3_v2_receive_startup_tests_r3b.log'),
        full_regression=dict(passed=503, capture='disabled for Windows Tcl compatibility',
            log_sha256=sha(ROOT / 'logs/Y3_v2_receive_full_tests_r3b.log')),
        software_sha256={str(p): sha(ROOT / p) for p in (
            'src/ps/sentinel/v2.py', 'src/ps/sentinel/app/runtime_v1.py',
            'src/ps/sentinel/app/monitor_x5.py',
            'src/ps/tests/test_v2_receive_startup.py')},
    )
    output = directory / 'y3_v2_receive_regression_r3.json'
    if output.exists():
        raise FileExistsError(output)
    write_evidence(output, receipt)
    print(receipt['status'], receipt['display_fps_median'], receipt['captures'])


if __name__ == '__main__':
    main()
