"""Run one finite X2 task, preserving hashes, boot identity and stopped state."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys

from x2_transport import (ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence)


def dependency(stem, deployment_digest, directory=None):
    """Select a hashed successful attempt tied to this exact deployment."""
    directory = ROOT/'board/measurements' if directory is None else directory
    for attempt in (3, 2, 1):
        path = directory/('%s_r%d_execution.json' % (stem, attempt))
        if not path.exists():
            continue
        record = verified(path)
        if record['status'] == 'PASS_EXECUTION' and record['deployment_sha256'] == deployment_digest:
            return path, record
    raise ValueError('No successful execution for this deployment: '+stem)


def accepted_dependency(stem, deployment_digest, directory=None, *, screening=False):
    directory = ROOT/'board/measurements' if directory is None else directory
    for attempt in (3, 2, 1):
        path = directory/('%s_r%d_execution.json' % (stem, attempt))
        if not path.exists():
            continue
        record = verified(path)
        if record['status'] != 'PASS_EXECUTION' or record['deployment_sha256'] != deployment_digest:
            continue
        name = path.name.removesuffix('_execution.json')
        acceptance_path = path.with_name(name+'_acceptance.json')
        if not acceptance_path.exists():
            continue
        accepted = verified(acceptance_path)
        measurement = path.with_name(name+'.json')
        if accepted['status'] != ('PASS_SCREENING' if screening else 'PASS'):
            continue
        if (accepted['measurement_sha256'] != sha(measurement)
                or accepted['execution_sha256'] != sha(path)):
            raise ValueError('Independent acceptance mismatched: '+stem)
        return path, record
    raise ValueError('No independently accepted execution for this deployment: '+stem)


def recoverable_library(deployment_digest, library_digest, original_digest, directory=None):
    """Recover only an artifact already hashed by an earlier completed build."""
    directory = ROOT/'board/measurements' if directory is None else directory
    for attempt in (3, 2, 1):
        path = directory/('x2_build_library_r%d_execution.json' % attempt)
        if not path.exists():
            continue
        record = verified(path)
        if (record['deployment_sha256'] == deployment_digest
                and record.get('ssh_exit_code') == 0
                and record.get('library_sha256') == library_digest
                and record.get('original_library_preserved') is True
                and record.get('original_library_sha256') == original_digest):
            return path
    raise ValueError('Existing X2 library has no matching verified build receipt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('build-library', 'selftest', 'monitor'), required=True)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--deployment-attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--rate', type=int, choices=(7680000, 15360000, 24576000, 30720000))
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--screening', action='store_true', help='60-second RX screen; separate evidence names')
    parser.add_argument('--fast-path', action='store_true', help='600-second qualification after screens up to the selected rate')
    args = parser.parse_args()
    if (args.mode == 'monitor') != (args.rate is not None):
        parser.error('--rate required only for monitor')
    if ((args.screening or args.fast_path) and args.mode != 'monitor') or (args.screening and args.fast_path):
        parser.error('Screening and fast-path are separate monitor modes')
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing credential on stdin')
    transport = Transport(password)
    tag = 'x2_%s%s_r%d' % (args.mode.replace('-', '_'), '_'+str(args.rate) if args.rate else '', args.attempt)
    if args.screening:
        tag = tag.replace('x2_monitor_', 'x2_screen_')
    receipt = ROOT/'board/measurements'/(tag+'_execution.json')
    output = ROOT/'board/measurements'/(tag+'.json')
    log = ROOT/'logs'/('X2_'+tag[3:]+'.log')
    if any(p.exists() or Path(str(p)+'.sha256').exists() for p in (receipt, output, log)):
        raise FileExistsError('Preserve attempt '+tag)
    deployment_path = ROOT/('board/measurements/x2_deployment_r%d.json' % args.deployment_attempt)
    deployment = verified(deployment_path)
    if deployment['status'] != 'PASS_DEPLOYMENT':
        raise ValueError('Verified X2 deployment required')
    for name, digest in deployment['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Deployed local source changed: '+name)
    files = dict(deployment['shared_sources']['present'])
    files.update({entry['destination']: entry['sha256'] for entry in deployment['deployment']['files']})
    transport.check_files(files)
    boot = transport.ssh('cat /proc/sys/kernel/random/boot_id').strip()
    preflight = transport.postflight()
    if preflight['status'] != 'PASS' or preflight['boot_id'] != boot:
        raise ValueError('Preflight stopped state/boot mismatch')
    record = dict(started_at_pc=datetime.now(timezone.utc).isoformat(), configuration_a_confirmed=True,
        RF_TX_requested=False, preflight=preflight, boot_id_before=boot,
        screening=args.screening, qualification_path='fast' if args.fast_path else 'standard',
        deployment_sha256=sha(deployment_path), checked_remote_files=files,
        source_sha256={name: sha(ROOT/name) for name in ('tools/run_x2_board.py', 'tools/x2_transport.py')})
    if args.mode == 'build-library':
        directory = REMOTE+'/ps/libad9361_pynq'
        command = ['make', '-C', directory, '-f', 'Makefile.x2', 'libad9361_x2.so',
                   'NOOS=../../third_party/no-OS']
        exists = transport.ssh('if test -e '+directory+'/libad9361_x2.so; then echo EXISTS; else echo NEW_LIBRARY; fi').strip()
        before = transport.ssh(['sha256sum', directory+'/libad9361_pynq.so']).split()[0]
        if exists == 'EXISTS':
            digest = transport.ssh(['sha256sum', directory+'/libad9361_x2.so']).split()[0]
            prior = recoverable_library(sha(deployment_path), digest, before)
            log.write_text('Recovered unchanged library from '+prior.name+'\n', encoding='utf-8')
            record.update(command='verify existing library', ssh_exit_code=0,
                          recovered_execution_sha256=sha(prior), library_sha256=digest)
        else:
            with log.open('xb') as stream:
                process = subprocess.run(['ssh', *OPTIONS, transport.target, shlex.join(command)],
                                         stdout=stream, stderr=subprocess.STDOUT, timeout=180)
            record.update(command=command, ssh_exit_code=process.returncode)
        if record['ssh_exit_code'] == 0:
            record['library_sha256'] = transport.ssh(['sha256sum', directory+'/libad9361_x2.so']).split()[0]
        after = transport.ssh(['sha256sum', directory+'/libad9361_pynq.so']).split()[0]
        record.update(original_library_sha256=before, original_library_preserved=before == after)
        passed = record['ssh_exit_code'] == 0 and before == after
    else:
        library_path, library_record = dependency('x2_build_library', sha(deployment_path))
        record['library_execution_sha256'] = sha(library_path)
        transport.check_files({'ps/libad9361_pynq/libad9361_x2.so': library_record['library_sha256']})
        remote_output = REMOTE+'/measurements/'+output.name
        if transport.ssh('test ! -e '+remote_output+' && echo NEW_OUTPUT').strip() != 'NEW_OUTPUT':
            raise FileExistsError(remote_output)
        command = [PYTHON, '-I', REMOTE+'/scripts/run_x2_'+args.mode+'.py',
                   '--bit', REMOTE+'/overlay/sentinel_v1c/sentinel_v1c.bit', '--out', remote_output]
        if args.mode == 'selftest':
            references = {name: sha(ROOT/'data/reference/spectrum'/name) for name in
                          ('in_axis32.hex', 'exp_power_shifted.hex')}
            transport.check_files({'data/reference/spectrum/'+name: digest for name, digest in references.items()})
            command += ['--references', REMOTE+'/data/reference/spectrum']
        else:
            selftest_path, _ = accepted_dependency('x2_selftest', sha(deployment_path))
            record['selftest_execution_sha256'] = sha(selftest_path)
            previous_rates = (7680000, 15360000, 24576000, 30720000)
            record['previous_rates_execution_sha256'] = {}
            required_rates = previous_rates[:previous_rates.index(args.rate)+(1 if args.fast_path else 0)]
            for rate in required_rates:
                prefix = 'x2_screen' if args.screening or args.fast_path else 'x2_monitor'
                previous_path, _ = accepted_dependency('%s_%d' % (prefix, rate), sha(deployment_path),
                                                       screening=args.screening or args.fast_path)
                record['previous_rates_execution_sha256'][str(rate)] = sha(previous_path)
            command += ['--rate', str(args.rate), '--seconds', '60' if args.screening else '600']
        record['command'] = command
        print('START '+tag+(' %d seconds RX only' % (60 if args.screening else 600) if args.mode == 'monitor' else ' finite digital only'), flush=True)
        with log.open('xb') as stream:
            process = subprocess.Popen(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))], stdin=subprocess.PIPE,
                stdout=stream, stderr=subprocess.STDOUT)
            process.communicate((password+'\n').encode() if password else b'')
        record['ssh_exit_code'] = process.returncode
        passed = process.returncode == 0
        try:
            # Compare the remote result hash before accepting the local copy.
            remote_hash = transport.ssh(['sha256sum', remote_output]).split()[0]
            transport.copy(transport.target+':'+remote_output, output)
            if sha(output) != remote_hash:
                raise ValueError('Retrieved result digest mismatch')
            Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
            data = json.loads(output.read_text())
            record.update(result_sha256=sha(output), result_status=data['status'])
            passed = passed and data['status'] in ('passed', 'completed') and data['boot_id'] == boot
            if args.mode == 'selftest' and data.get('raw_archive_sha256'):
                archive = output.with_suffix('.npz')
                transport.copy(transport.target+':'+remote_output[:-5]+'.npz', archive)
                if sha(archive) != data['raw_archive_sha256']:
                    raise ValueError('Raw self-test archive digest mismatch')
                Path(str(archive)+'.sha256').write_text(sha(archive)+'  '+archive.name+'\n', encoding='ascii')
                record['archive_sha256'] = sha(archive)
        except Exception as error:
            record['retrieval_error'] = str(error)
            passed = False
    try:
        record['postflight'] = transport.postflight()
        passed = passed and record['postflight']['status'] == 'PASS' and record['postflight']['boot_id'] == boot
    except Exception as error:
        record['postflight_error'] = str(error)
        passed = False
    record.update(status='PASS_EXECUTION' if passed else 'FAIL_EXECUTION',
                  ended_at_pc=datetime.now(timezone.utc).isoformat(),
                  log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log))
    write_evidence(receipt, record)
    password = None
    transport.password = None
    print(json.dumps(record, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
