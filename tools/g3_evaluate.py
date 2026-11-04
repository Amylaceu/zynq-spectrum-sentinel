"""Evaluate preserved G3 evidence, without touching hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from run_x1_board import write_evidence


def checked(path):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Evidence checksum mismatch: '+str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def load_run(directory):
    manifest = checked(directory/'verification.json')
    if manifest['status'] != 'PASS' or manifest['kind'] != 'monitor':
        raise ValueError('Expected verified monitor evidence')
    for name, expected in manifest['files_sha256'].items():
        target = (directory/name).resolve()
        if not target.is_relative_to(directory.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('Raw evidence mismatch: '+name)
    tag = manifest['tag']
    result = json.loads((directory/'measurements'/('monitor_'+tag)/'result.json').read_text())
    execution = json.loads((directory/'measurements'/(tag+'_execution.json')).read_text())
    link_path = directory/'measurements'/('monitor_'+tag)/'hostlink.json'
    return result, execution, checked(link_path) if link_path.exists() else None


def evaluate(baseline, enabled, execution, link, validation, wire):
    base_fps = [x['display_fps'] for x in baseline['telemetry']]
    enabled_fps = [x['display_fps'] for x in enabled['telemetry']]
    decrease = statistics.median(base_fps)-statistics.median(enabled_fps)
    errors = {r['header'].get('request_seq') for r in validation['responses'] if r['header']['type'] == 'error'}
    replies = [r['header'] for r in validation['responses'] if r['header']['type'] == 'reply']
    stop = execution.get('stop_readback', {})
    # perf_mon snap_status: bit0 overflow_seen, bit1 error_seen, bit2 latency_valid.
    # A value of 4 is a valid latency sample, not an overflow.
    processing_faults = [x['processing_status'] & 3 for x in enabled['telemetry']]
    checks = dict(
        normal_exit=enabled['status'] == 'completed' and execution['status'] == 'PASS' and execution['worker_exit_code'] == 0,
        duration=enabled['elapsed_total_s'] >= 420,
        lcd_decrease=decrease <= 1,
        network_cpu=link['network_cpu_single_core_pct'] <= 15,
        zero_overflow=not any(processing_faults) and 'continuity_error' not in enabled,
        network_healthy=link['capture_error'] is None and link['thread_error'] is None,
        reconnects=len(validation['reconnects']) == 10 and all(x['disconnected_s'] >= 30 for x in validation['reconnects']),
        whitelist={5, 6, 7, 8} <= errors and link['rejected'] == 4 and len(link['rejections']) == 4,
        status_and_snapshot=any('snapshot' in x and x.get('ok') is True for x in replies)
            and any('status' in x and x.get('ok') is True for x in replies),
        web=validation['web_page_ok'] and validation['sse_first_line'] == ': ready' and validation['sse_message'].startswith('data:'),
        receive_only=enabled['RF_TX_requested'] is False and all(x['tx_atten_mdb'] == [89750,89750] for x in enabled['telemetry']),
        stopped=stop.get('status') == 'PASS' and all(type(stop.get(k)) is int and stop[k] == 0 for k in ('gpio_data','source_ctrl','audio_control')),
        pl_to_pc_150ms=False,
    )
    kinds = {}
    for row in wire:
        kind = row['header']['type']
        kinds[kind] = kinds.get(kind, 0)+1
    return dict(status='PASS' if all(checks.values()) else 'FAIL',
        functional_status='PASS' if all(v for k,v in checks.items() if k != 'pl_to_pc_150ms') else 'FAIL',
        checks=checks, baseline_median_fps=statistics.median(base_fps),
        enabled_median_fps=statistics.median(enabled_fps), lcd_median_decrease_fps=decrease,
        enabled_min_fps=min(enabled_fps), network_cpu_single_core_pct=link['network_cpu_single_core_pct'],
        spectrum_hz=link['spectrum_hz'], spectrum_samples=link['spectrum_samples'],
        max_queue_bytes=link['max_queue_bytes'], producer_drops=link['producer_drops'], client_drops=link['client_drops'],
        duration_s=enabled['elapsed_total_s'], messages_by_type=kinds,
        pl_to_pc_latency='NOT_CERTIFIED_NO_EXACT_PL_FRAME_MAPPING_OR_CLOCK_CALIBRATION',
        reconnect_scope='Ten PC socket disconnects >=30s; physical cable not unplugged',
        historical_failures_preserved=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    baseline, _, _ = load_run(a.directory/'baseline_raw')
    enabled, execution, link = load_run(a.directory/'enabled_raw')
    validation = checked(a.directory/'validation.json')
    manifest = checked(a.directory/'manifest.json')
    for name, expected in manifest['files_sha256'].items():
        if hashlib.sha256((a.directory/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Wire evidence checksum mismatch')
    wire = [json.loads(line) for line in (a.directory/'wire.jsonl').read_text().splitlines()]
    value = evaluate(baseline, enabled, execution, link, validation, wire)
    write_evidence(a.output, value)
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
