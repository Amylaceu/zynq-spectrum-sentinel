"""Evaluate G2 board measurements without RF access or optimistic defaults."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from run_x1_board import write_evidence


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values)-1)*fraction
    low = int(position)
    high = min(low+1, len(values)-1)
    return values[low]+(values[high]-values[low])*(position-low)


def evaluate(result, execution):
    ui = result.get('ui', {})
    timings = ui.get('timing_samples_ms', [])
    timings_ok = bool(timings) and all(isinstance(x, (int, float)) and
        math.isfinite(x) and x >= 0 for x in timings)
    median = statistics.median(timings) if timings_ok else None
    p95 = percentile(timings, .95) if timings_ok else None
    fps = [entry.get('display_fps') for entry in result.get('telemetry', [])]
    fps_ok = bool(fps) and all(isinstance(x, (int, float)) and math.isfinite(x) for x in fps)
    stop = execution.get('stop_readback', {})
    duration = result.get('elapsed_total_s', 0)
    checks = dict(
        completed=result.get('status') == 'completed' and execution.get('status') == 'PASS'
                  and execution.get('worker_exit_code') == 0,
        ten_minutes=isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 600,
        version=ui.get('version') == 'v3',
        median=median is not None and median <= 25,
        p95=p95 is not None and p95 <= 40,
        frame_rate=fps_ok and min(fps) >= 28.49,
        zero_errors=ui.get('errors') == 0 and ui.get('submissions', 0) > 0,
        stopped=stop.get('status') == 'PASS' and all(type(stop.get(k)) is int and stop[k] == 0
            for k in ('gpio_data', 'source_ctrl', 'audio_control')),
        receive_only=result.get('RF_TX_requested') is False and result.get('source') == 'rf',
    )
    return dict(status='PASS_METRICS_VISUAL_SEPARATE' if all(checks.values()) else 'FAIL',
        checks=checks, median_ms=median, p95_ms=p95, min_fps=min(fps) if fps_ok else None,
        measured_duration_s=duration, submissions=ui.get('submissions'),
        submit_errors=ui.get('errors'), samples=len(timings),
        measurement_scope=ui.get('timing_scope'),
        human_readability='Requires separate current-run user confirmation',
        tx_on_physical_test='Deferred to G5 configuration B; no transmission in G2')


def checked_run(directory):
    directory = Path(directory)
    verification = directory/'verification.json'
    digest = hashlib.sha256(verification.read_bytes()).hexdigest()
    if Path(str(verification)+'.sha256').read_text().split()[0] != digest:
        raise ValueError('Fetch verification digest mismatch')
    manifest = json.loads(verification.read_text())
    if manifest.get('status') != 'PASS' or manifest.get('kind') != 'monitor':
        raise ValueError('Expected verified monitor evidence')
    for name, expected in manifest['files_sha256'].items():
        target = (directory/name).resolve()
        if not target.is_relative_to(directory.resolve()):
            raise ValueError('Evidence path escapes root')
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('Evidence file digest mismatch: '+name)
    tag = manifest['tag']
    result = json.loads((directory/'measurements'/('monitor_'+tag)/'result.json').read_text())
    execution = json.loads((directory/'measurements'/(tag+'_execution.json')).read_text())
    return evaluate(result, execution)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    value = checked_run(args.directory)
    write_evidence(args.output, value)
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
