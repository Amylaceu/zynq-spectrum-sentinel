"""Audit retrieved G1 A-demo evidence without contacting hardware.

Functional completion and quantitative acceptance are deliberately separate.
Refuse corrupt/missing sidecars; do not discard the cold first cycle.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.release_support import write_result


def checked(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Evidence digest mismatch: '+str(path))
    return json.loads(path.read_text())


def evaluate(directory):
    directory = Path(directory)
    demo = checked(directory/'demo.json')
    if demo.get('group') != 'A':
        raise ValueError('Only group A measured here; B must be separately verified')
    records = []
    for segment in demo['segments']:
        evidence = (directory/segment['evidence_dir']/'result.json').resolve()
        if directory.resolve() not in evidence.parents:
            raise ValueError('Segment evidence escapes measurement directory')
        result = checked(evidence)
        records.append(result)
        if segment.get('result_sha256') != hashlib.sha256(
                (directory/segment['evidence_dir']/'result.json').read_bytes()).hexdigest():
            raise ValueError('Demo references a different segment result')
    controls = ('gpio_data', 'source_ctrl', 'audio_control')
    def stopped(value):
        return value.get('status') == 'PASS' and all(
            type(value.get(k)) is int and value[k] == 0 for k in controls)
    safe = bool(demo['segments']) and all(stopped(s.get('stop_readback', {}))
                                          for s in demo['segments'])
    final_safe = stopped(demo.get('final_stop_readback', {}))
    runtime = demo.get('runtime', {})
    rf = [s for s in runtime.get('segments', []) if s['source'] == 'rf']
    tx_safe = bool(rf) and all(s.get('tx_attenuation_before_reset_db') == [89.75, 89.75] for s in rf)
    cycles = [c['wall_seconds'] for c in demo.get('cycles_timing', [])]
    audio = [r for s, r in zip(demo['segments'], records) if s['number'] == 3]
    underflows = [r['audio_before_stop']['underflows'] for r in audio]
    functionality = (demo['status'] == 'PASS' and demo.get('completed_cycles') == 3
        and len(demo['segments']) == 12 and safe and final_safe and tx_safe and len(audio) == 3
        and all(s.get('exit_code') == 0 and r.get('status') in ('PASS', 'completed')
                for s, r in zip(demo['segments'], records))
        and all(r.get('audible_seconds', 0) > 0 for r in audio) and not any(underflows))
    segments = runtime.get('segments', [])
    startup = [s['content_started_monotonic_s']-s['started_monotonic_s']
               for s in segments if 'content_started_monotonic_s' in s]
    # Switching includes prior cleanup and all work before the next content
    # starts, not merely the Python call that initiates configuration.
    content = [s for s in segments if 'content_started_monotonic_s' in s]
    requested = [s['duration_requested_s'] for s in demo['segments']]
    transitions = [max(0.0, content[i]['content_started_monotonic_s']
                       -content[i-1]['content_started_monotonic_s']-requested[i-1])
                   for i in range(1, len(content))] if len(content) == len(requested) else []
    wav = demo.get('wav_recording', {})
    metrics = dict(cycle_seconds=cycles, mean_cycle_seconds=statistics.mean(cycles) if cycles else None,
        each_cycle_le_110s=len(cycles) == 3 and all(
            math.isfinite(c) and 95 <= c <= 110 for c in cycles),
        startup_seconds=startup, transition_seconds=transitions,
        transition_median_seconds=statistics.median(transitions) if transitions else None,
        transition_max_seconds=max(transitions) if transitions else None,
        transition_target_pass=bool(transitions) and statistics.median(transitions) <= 3 and max(transitions) <= 6,
        audio_underflows=underflows, audible_seconds=[r.get('audible_seconds') for r in audio],
        wav_status=wav.get('status'), wav_target_pass=False,
        overlay_loads=runtime.get('overlay_loads'), model_loads=runtime.get('model_loads'),
        model_warmups=runtime.get('model_warmups'), rf_initializations=runtime.get('rf_initializations'))
    return dict(step='showcase/G1', group='A', status='FAIL',
        functional_status='PASS' if functionality else 'FAIL', metrics=metrics,
        all_segment_stop_readbacks_pass=safe, final_stop_readback_pass=final_safe,
        receive_tx_attenuation_readbacks_pass=tx_safe,
        b_group_status='NOT_TESTED_CONFIGURATION_A',
        wav_limitation='Frozen PL has no actual playback PCM readback; no substitute WAV created',
        cold_start_included=True, historical_failures_preserved=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve original evidence; choose a new output')
    result = evaluate(args.directory)
    write_result(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
