"""Download completed F2 demo evidence and verify every copied file hash."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.release_support import sha, write_result
from x2_transport import Transport, OPTIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='demo_<timestamp>_<id> directory name')
    parser.add_argument('--out', type=Path, required=True, help='New local evidence directory')
    args = parser.parse_args()
    if not re.fullmatch(r'demo_[A-Za-z0-9_]+', args.run):
        parser.error('Invalid demo run name')
    if args.out.exists():
        parser.error('Preserve previous downloads')
    remote = '/home/xilinx/sentinel/release/v2'
    transport = Transport()
    script = '''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);run=root/'measurements'/sys.argv[2]
data=json.loads((run/'demo.json').read_text())
if data['status']=='STARTED':raise RuntimeError('Demo still running; wait before collecting')
tag=sys.argv[2][5:];execution=root/'measurements'/(tag+'_execution.json')
if not execution.is_file():raise RuntimeError('Supervisor postflight still pending')
files={p.relative_to(run).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
       for p in run.rglob('*') if p.is_file()}
print(json.dumps(dict(files=files,execution=json.loads(execution.read_text()),
    execution_sha256=hashlib.sha256(execution.read_bytes()).hexdigest(),
    execution_sidecar=pathlib.Path(str(execution)+'.sha256').read_text(),
    supervisor_log=(root/'logs'/(tag+'.log')).read_text())))
'''
    manifest = json.loads(transport.ssh(['python3', '-c', script, remote, args.run]))
    args.out.mkdir(parents=True)
    subprocess.run(['scp', *OPTIONS, '-r', transport.target+':'+remote+'/measurements/'+args.run,
                    str(args.out/'raw')], check=True, timeout=90)
    actual = {p.relative_to(args.out/'raw').as_posix(): sha(p)
              for p in (args.out/'raw').rglob('*') if p.is_file()}
    if actual != manifest['files']:
        raise RuntimeError('Downloaded evidence differs from stopped board files')
    for path in (args.out/'raw').rglob('*.sha256'):
        original = Path(str(path)[:-7])
        if sha(original) != path.read_text().split()[0]:
            raise RuntimeError('Result sidecar mismatch: '+str(path))
    if manifest['execution_sha256'] != manifest['execution_sidecar'].split()[0]:
        raise RuntimeError('Supervisor result sidecar mismatch')
    record = json.loads((args.out/'raw/demo.json').read_text())
    segments = record['segments']
    complete = (record['status'] == 'PASS' and record.get('completed_cycles') == 3
                and [(s['cycle'], s['number']) for s in segments] ==
                [(cycle, number) for cycle in range(1, 4) for number in range(1, 5)])
    safe = all(s['stop_readback']['status'] == 'PASS'
               and all(s['stop_readback'][k] == 0 for k in ('gpio_data','source_ctrl','audio_control'))
               for s in segments)
    telemetry, audio, durations = [], [], []
    for segment in segments:
        result = json.loads((args.out/'raw'/segment['evidence_dir']/'result.json').read_text())
        if segment['number'] == 2:
            telemetry.extend(result['telemetry'])
        if segment['number'] == 3:
            audio.append(dict(cycle=segment['cycle'], audible_seconds=result['audible_seconds'],
                duration_s=result['elapsed_total_s'], underflows=result['audio_before_stop']['underflows'],
                final_codec_muted=result.get('final_codec_muted'), safe_stop_errors=result['safe_stop_errors']))
        if segment['number'] == 4:
            assert result['final_rf_gpio'] == 0
    for cycle in range(1, 4):
        durations.append(sum(s['duration_wall_s'] for s in segments if s['cycle'] == cycle))
    audio_pass = len(audio) == 3 and all(a['audible_seconds'] > 0 and a['underflows'] == 0
        and a['final_codec_muted'] is True and not a['safe_stop_errors'] for a in audio)
    rf_pass = bool(telemetry) and all(t['tx_atten_mdb'] == [89750, 89750]
        and t['rx_rssi_dbm'] <= -30 and 30 <= t['temperature_c'] <= 85
        and t['processing_status'] & 3 == 0 for t in telemetry)
    full_wall = (datetime.fromisoformat(record['finished_utc'])-
                 datetime.fromisoformat(record['started_utc'])).total_seconds()
    summary = dict(status='PASS_FUNCTIONAL' if complete and safe and audio_pass and rf_pass
                   and manifest['execution']['status']=='PASS' else 'FAIL',
        host_utc=datetime.now(timezone.utc).isoformat(), files_verified=len(actual),
        three_complete_cycles=complete, segment_stops_pass=safe, audio=audio,
        audio_pass=audio_pass, receive_safety_pass=rf_pass,
        three_cycle_wall_seconds=full_wall, mean_cycle_wall_seconds=full_wall/3,
        segment_process_wall_seconds_per_cycle=durations,
        duration_scope='Sum of segment workers; excludes supervisor postflight between segments',
        min_monitor_fps=min((t['display_fps'] for t in telemetry), default=None),
        max_monitor_temperature_c=max((t['temperature_c'] for t in telemetry), default=None),
        processing_error_samples=sum(bool(t['processing_status'] & 3) for t in telemetry),
        manifest=manifest, human_result='board/measurements/f2_human_r1.json',
        outstanding=['Continuous WAV recording', 'Original ~1.5 minute wall-clock target',
                     'Green TX OFF and full-width top heading unavailable in frozen LCD palette/layout'])
    write_result(args.out/'verification.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='manifest'}, indent=2))
    return 0 if summary['status']=='PASS_FUNCTIONAL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
