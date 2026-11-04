"""Deploy immutable F3 probe and collect evidence; credential only via stdin."""
import argparse
import ast
from datetime import datetime, timezone
import json
import shlex
import subprocess
import sys
import tarfile
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from run_x5_board import INSTALL, LIB_SHA


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('preflight', 'watchdog', 'calibrate', 'capture', 'pd', 'pfa'))
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    p.add_argument('--sudo-stdin', action='store_true')
    p.add_argument('--presentation-antenna', choices=('S1', 'S2'),
                   help='I0 confirmed hardware; use a separate evidence namespace')
    args = p.parse_args()
    if args.presentation_antenna and args.mode != 'calibrate':
        p.error('Presentation antenna checks only reuse bounded calibration')
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    tag = ('i0_%s_ota_r%d' % (args.presentation_antenna.lower(), args.attempt)
           if args.presentation_antenna else 'f3_%s_r%d' % (args.mode, args.attempt))
    evidence = ROOT/'board/measurements'/(tag+'_execution.json')
    output = ROOT/'board/measurements'/tag
    archive = ROOT/'build'/(tag+'.tar.gz')
    log = ROOT/'logs'/((tag.upper()+'.log') if args.presentation_antenna else
                      'F3_%s_r%d.log' % (args.mode, args.attempt))
    if any(x.exists() for x in (evidence, output, archive, log)):
        raise FileExistsError('Preserve previous probe')
    library = verified(ROOT/'board/measurements/f3_library_r1.json')
    if library['status'] != 'PASS':
        raise RuntimeError('Library not accepted')
    files = {'ps/'+x.relative_to(ROOT/'src/ps').as_posix(): x
             for x in (ROOT/'src/ps/sentinel').rglob('*.py')}
    files['scripts/run_f3_probe.py'] = ROOT/'board/scripts/run_f3_probe.py'
    if args.mode == 'pfa':
        files['scripts/run_f3_pfa.py'] = ROOT/'board/scripts/run_f3_pfa.py'
    if args.mode == 'capture':
        for path in (ROOT/'data/reference/f3_ota').glob('*'):
            files['data/f3_ota/'+path.name] = path
    for path in files.values():
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
    manifest = {name: sha(path) for name, path in files.items()}
    remote = REMOTE+'/setup/'+tag
    t = Transport(password)
    baseline = REMOTE+'/release/v2/ps/libad9361_pynq/libad9361_pynq.so'
    if t.ssh(['sha256sum', baseline]).split()[0] != LIB_SHA:
        raise RuntimeError('Frozen receiver changed')
    with tarfile.open(archive, 'x:gz') as tar:
        for name, path in files.items():
            tar.add(path, arcname=name, recursive=False)
    t.copy(archive, t.target+':'+remote+'.tar.gz')
    t.ssh(['python3', '-c', INSTALL], payload=json.dumps(dict(root=remote,
        archive=remote+'.tar.gz', archive_sha256=sha(archive), files=manifest)))
    bit = REMOTE+'/release/v2/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    command = [PYTHON, '-I', remote+'/scripts/run_f3_probe.py', args.mode,
               '--bit', bit, '--library', library['remote_root']+'/libad9361_f3.so',
               '--library-sha256', library['library_sha256'],
               '--out', remote+'/measurements/result.json']
    command += (['--presentation-antenna-confirmed', args.presentation_antenna]
                if args.presentation_antenna else ['--antenna-b-direct-confirmed'])
    if args.mode == 'pfa':
        command = [PYTHON, '-I', remote+'/scripts/run_f3_pfa.py', '--bit', bit,
                   '--library', baseline, '--out', remote+'/measurements/result.json']
    record = dict(status='STARTED', started_utc=datetime.now(timezone.utc).isoformat(),
                  remote_root=remote, files_sha256=manifest, command=command)
    write_evidence(output.with_name(tag+'_start.json'), record)
    with log.open('xb') as stream:
        proc = subprocess.run(['ssh', *OPTIONS, t.target, shlex.join(t.privileged(command))],
            input=(password+'\n').encode() if password else None,
            stdout=stream, stderr=subprocess.STDOUT, timeout=240)
    record['exit_code'] = proc.returncode
    output.mkdir()
    try:
        t.copy(t.target+':'+remote+'/measurements/result.json', output/'result.json')
        digest = t.ssh(['sha256sum', remote+'/measurements/result.json']).split()[0]
        if sha(output/'result.json') != digest:
            raise RuntimeError('Result digest mismatch')
        (output/'result.json.sha256').write_text(digest+'  result.json\n')
        result = json.loads((output/'result.json').read_text())
        for item in result.get('modulation_captures', []):
            name = item['filename']
            if '/' in name or '\\' in name or not name.startswith('class_'):
                raise ValueError('Unsafe evidence filename')
            t.copy(t.target+':'+remote+'/measurements/'+name, output/name)
            if sha(output/name) != item['sha256']:
                raise RuntimeError('Class capture digest mismatch')
            (output/(name+'.sha256')).write_text(item['sha256']+'  '+name+'\n')
        if result.get('capture_sha256'):
            t.copy(t.target+':'+remote+'/measurements/result.npz', output/'result.npz')
            if sha(output/'result.npz') != result['capture_sha256']:
                raise RuntimeError('IQ digest mismatch')
            (output/'result.npz.sha256').write_text(sha(output/'result.npz')+'  result.npz\n')
        record['result_sha256'] = digest
        record['status'] = 'PASS' if proc.returncode == 0 and result['status'] == 'PASS' else 'FAIL'
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    record['baseline_after'] = t.ssh(['sha256sum', baseline]).split()[0]
    record['log_sha256'] = sha(log)
    if record['baseline_after'] != LIB_SHA:
        record['status'] = 'FAIL'
    write_evidence(evidence, record)
    print(json.dumps(record))
    if record['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
