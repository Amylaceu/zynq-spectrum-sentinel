"""Collect a stopped B demo, including failures, without operating hardware."""
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
from x2_transport import Transport, OPTIONS, REMOTE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'demo_[A-Za-z0-9_]+', args.run) or args.out.exists():
        parser.error('Use an existing demo name and a new local output directory')
    remote = REMOTE+'/release/v2'
    script = '''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);run=root/'measurements'/sys.argv[2]
data=json.loads((run/'demo.json').read_text())
if data['status']=='STARTED':raise RuntimeError('Demo still running')
tag=sys.argv[2][5:];execution=root/'measurements'/(tag+'_execution.json')
if not execution.is_file():raise RuntimeError('Supervisor has not finished')
files={p.relative_to(run).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
       for p in run.rglob('*') if p.is_file()}
print(json.dumps(dict(files=files,execution_text=execution.read_text(),
 execution_sha256=hashlib.sha256(execution.read_bytes()).hexdigest(),
 execution_sidecar=pathlib.Path(str(execution)+'.sha256').read_text(),
 log_text=(root/'logs'/(tag+'.log')).read_text())))
'''
    transport = Transport()
    manifest = json.loads(transport.ssh(['python3', '-c', script, remote, args.run]))
    args.out.mkdir(parents=True)
    subprocess.run(['scp', *OPTIONS, '-r', transport.target+':'+remote+'/measurements/'+args.run,
                    str(args.out/'raw')], check=True, timeout=90)
    actual = {p.relative_to(args.out/'raw').as_posix(): sha(p)
              for p in (args.out/'raw').rglob('*') if p.is_file()}
    if actual != manifest['files']:
        raise RuntimeError('Copied evidence differs from board')
    for side in (args.out/'raw').rglob('*.sha256'):
        if sha(Path(str(side)[:-7])) != side.read_text().split()[0]:
            raise RuntimeError('Bad sidecar '+str(side))
    execution = args.out/'execution.json'
    execution.write_bytes(manifest['execution_text'].encode('utf-8'))
    Path(str(execution)+'.sha256').write_text(manifest['execution_sidecar'], encoding='ascii')
    if sha(execution) != manifest['execution_sha256'] or sha(execution) != manifest['execution_sidecar'].split()[0]:
        raise RuntimeError('Supervisor evidence differs')
    log = ROOT/'logs'/('F3_'+args.out.name+'_board.log')
    if log.exists():
        raise FileExistsError(log)
    log.write_text(manifest.pop('log_text'), encoding='utf-8')
    manifest.pop('execution_text'); manifest.pop('execution_sidecar')
    write_result(args.out/'download_manifest.json', dict(manifest, log_sha256=sha(log)))
    data = json.loads((args.out/'raw/demo.json').read_text())
    segments = data['segments']
    complete = data['status']=='PASS' and data.get('completed_cycles')==3 and [
        (s['cycle'],s['number']) for s in segments] == [
        (cycle,number) for cycle in range(1,4) for number in (7,5,6,8)]
    stopped = all(s.get('status')=='PASS' and not s.get('cleanup_errors') and
        not s.get('quarantined') and all(type(s.get('stop_readback',{}).get(k)) is int and
            s['stop_readback'][k]==0 for k in ('gpio_data','source_ctrl','audio_control'))
        for s in segments)
    rf_stop = all(s.get('stop_readback',{}).get('ensm')==2 and
        s.get('stop_readback',{}).get('tx_attenuation_db')==[89.75,89.75]
        for s in segments if s['number'] in (5,6))
    tx = [t for s in segments if s['number'] in (5,6) for t in s.get('telemetry',[])]
    telem = [t for s in segments for t in s.get('telemetry',[])]
    safety = bool(tx) and all(40<=t['tx_atten_db']<=89.75 and t['tx2_atten_db']==89.75 and
        t['rssi_dbm']<=-30 for t in tx)
    captures = all(len(s.get('captures',[]))==(10 if s['number']==5 else 3)
                   for s in segments if s['number'] in (5,6))
    supervisor = json.loads(execution.read_text())
    summary = dict(status='PASS_FUNCTIONAL' if complete and stopped and rf_stop and safety and
        captures and supervisor['status']=='PASS' else 'FAIL',
        host_utc=datetime.now(timezone.utc).isoformat(), board_status=data['status'],
        error=data.get('error'), cycles_completed=data.get('completed_cycles'),
        three_cycles_complete=complete, stops_pass=stopped, rf_stops_pass=rf_stop, safety_pass=safety,
        captures_complete=captures, files_verified=len(actual), wall_seconds=data.get('wall_seconds'),
        cycle_seconds=[sum(s.get('wall_seconds',0) for s in segments if s['cycle']==i)
                       for i in range(1,4)],
        min_tx_atten_db=min((t['tx_atten_db'] for t in tx),default=None),
        max_rssi_dbm=max((t['rssi_dbm'] for t in tx),default=None),
        min_fps=min((t['fps'] for t in telem),default=None),
        max_temperature_c=max((t['temperature_c'] for t in telem),default=None),
        segments=[{k:v for k,v in s.items() if k not in ('telemetry','captures')} for s in segments])
    write_result(args.out/'verification.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='segments'}))
    # Successful collection of FAIL evidence is a successful collection operation.
    return 0


if __name__=='__main__':
    raise SystemExit(main())
