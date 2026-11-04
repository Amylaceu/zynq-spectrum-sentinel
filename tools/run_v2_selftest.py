"""Boot-to-v2 bounded digital regression, reusing the existing tone/replay code.

Only an empty PYNQ PL state is accepted by this cold-start runner. A running
overlay needs its existing stop/postflight workflow. No RF initialization,
transmit, or codec unmute. Password is optional stdin and is never logged.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

import numpy as np

from accept_x2_selftest import verify_tone_peaks
from run_x5_board import INSTALL, payload_files
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files

BOOT_CHECK = '''import fcntl,json,os,pathlib
os.environ['XILINX_XRT']='/usr'
with open('/run/lock/zss_ad9361.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 from pynq import PL
 if PL.bitfile_name:raise RuntimeError('Existing overlay: use its stop workflow')
 print(json.dumps(dict(status='EMPTY_PL_NO_MMIO',bitfile_name=PL.bitfile_name,
     boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential')
    tag = 'y3_v2_selftest_r%d' % args.attempt
    out = ROOT/'board/measurements'/tag
    log = ROOT/'logs'/(tag+'.log')
    archive = ROOT/'build'/(tag+'_runtime.tar.gz')
    receipt = out.with_name(tag+'_execution.json')
    if any(p.exists() for p in (out, log, archive, receipt)):
        raise FileExistsError('Preserve prior self-test')
    files = payload_files('sentinel_v2_100m')
    files['scripts/run_x1_selftest.py'] = ROOT/'board/scripts/run_x1_selftest.py'
    for name in ('in_axis32.hex', 'exp_power_shifted.hex'):
        files['reference/'+name] = ROOT/'data/reference/spectrum'/name
    manifest = {name: sha(path) for name, path in files.items()}
    transport = Transport(password)
    preflight = json.loads(transport.ssh([PYTHON, '-I', '-c', BOOT_CHECK], privileged=True))
    # Installer takes a shared lock file as the ordinary SSH user.
    transport.ssh(['test', '-r', '/run/lock/zss_ad9361.lock'])
    stage = REMOTE+'/setup/'+tag+'_runtime'
    with tarfile.open(archive, 'x:gz') as tar:
        for name, path in files.items():
            tar.add(path, arcname=name, recursive=False)
    transport.ssh(['test', '!', '-e', stage])
    transport.copy(archive, transport.target+':'+stage+'.tar.gz')
    transport.ssh([PYTHON, '-I', '-c', INSTALL], payload=json.dumps(dict(
        root=stage, archive=stage+'.tar.gz', archive_sha256=sha(archive), files=manifest)))
    bit = stage+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    command = ['timeout', '--signal=TERM', '--kill-after=10s', '90s', PYTHON, '-I',
               stage+'/scripts/run_x1_selftest.py', '--image', 'sentinel_v2_100m',
               '--bit', bit, '--references', stage+'/reference',
               '--out', stage+'/measurements/result.json']
    record = dict(status='STARTED', started_utc=datetime.now(timezone.utc).isoformat(),
                  preflight=preflight, remote_bit=bit, remote_root=stage,
                  rf_requested=False, audio_requested=False, command=command,
                  deployment_sha256=manifest, archive_sha256=sha(archive))
    write_evidence(out.with_name(tag+'_start.json'), record)
    try:
        with log.open('xb') as stream:
            proc = subprocess.run(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))],
                input=(password+'\n').encode() if password else b'',
                stdout=stream, stderr=subprocess.STDOUT, timeout=110)
        record['ssh_exit_code'] = proc.returncode
        record['postflight'] = json.loads(transport.ssh([PYTHON, '-I',
            stage+'/scripts/y3_postflight.py', '--bit', bit], privileged=True))
        out.mkdir()
        retrieve_files(transport.target, stage+'/measurements',
                       ['result.json', 'result.json.sha256', 'result.npz'], out, OPTIONS)
        result = verified(out/'result.json')
        if sha(out/'result.npz') != result['raw_archive_sha256']:
            raise ValueError('Raw result hash mismatch')
        (out/'result.npz.sha256').write_text(sha(out/'result.npz')+'  result.npz\n')
        golden = np.array([int(x, 16) for x in files['reference/exp_power_shifted.hex']
                          .read_text().split()], dtype=np.uint32).reshape(4, 2048)
        inputs = np.array([int(x, 16) for x in files['reference/in_axis32.hex']
                          .read_text().split()], dtype=np.uint32).reshape(4, 2048)
        with np.load(out/'result.npz', allow_pickle=False) as raw:
            verify_tone_peaks(raw['single_tone_power'], raw['triple_tone_power'])
            if not all(np.array_equal(raw[k], a) for k, a in
                       (('power', golden), ('golden', golden), ('input_words', inputs))):
                raise ValueError('8192-word replay differs')
        if not (proc.returncode == 0 and result['status'] == 'passed'
                and result['rf_initialized'] is False
                and record['postflight']['status'] == 'PASS'
                and preflight['boot_id'] == result['boot_id'] == record['postflight']['boot_id']):
            raise ValueError('Execution/stop/boot check failed')
        record.update(status='PASS', exact_replay_words=8192,
                      result_sha256=sha(out/'result.json'))
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    finally:
        record['log_sha256'] = sha(log) if log.exists() else None
        write_evidence(receipt, record)
    print(json.dumps(dict(status=record['status'], remote_bit=bit, receipt=str(receipt))))
    if record['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
