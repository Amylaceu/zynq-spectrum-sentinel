"""Build an isolated OTA adapter on the board; no RF/MMIO calls, no sudo."""
import argparse
import json
import tarfile
from pathlib import Path
from x2_transport import ROOT, REMOTE, Transport, sha, write_evidence
from run_x5_board import INSTALL, LIB_SHA


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = p.parse_args()
    tag = 'f3_library_r%d' % args.attempt
    evidence = ROOT/'board/measurements'/(tag+'.json')
    archive = ROOT/'build'/(tag+'.tar.gz')
    log = ROOT/'logs'/('F3_library_r%d.log' % args.attempt)
    if any(x.exists() for x in (evidence, archive, log)):
        raise FileExistsError('Preserve prior build')
    base = ROOT/'src/ps/libad9361_pynq'
    files = {x.relative_to(base).as_posix(): x for pattern in
             ('Makefile', 'Makefile.f3', 'platform/*.c', 'platform/*.h', 'app/*.c', 'app/*.h', 'app/*.map')
             for x in base.glob(pattern)}
    manifest = {name: sha(x) for name, x in files.items()}
    remote = REMOTE+'/setup/'+tag
    t = Transport()
    baseline = REMOTE+'/release/v2/ps/libad9361_pynq/libad9361_pynq.so'
    before = t.ssh(['sha256sum', baseline]).split()[0]
    if before != LIB_SHA:
        raise RuntimeError('Frozen receiver differs')
    with tarfile.open(archive, 'x:gz') as tar:
        for name, path in files.items():
            tar.add(path, arcname=name, recursive=False)
    t.copy(archive, t.target+':'+remote+'.tar.gz')
    t.ssh(['python3', '-c', INSTALL], payload=json.dumps(dict(root=remote,
        archive=remote+'.tar.gz', archive_sha256=sha(archive), files=manifest)))
    record = dict(status='STARTED', remote_root=remote, source_sha256=manifest,
                  archive_sha256=sha(archive), rf_access=False, baseline_before=before)
    try:
        command = ['make', '-C', remote, '-f', 'Makefile.f3', '-j2',
                   'NOOS='+REMOTE+'/third_party/no-OS']
        output = t.ssh(command, timeout=180)
        log.write_text(output, encoding='utf-8')
        symbols = t.ssh(['nm', '-D', '--defined-only', remote+'/libad9361_f3.so'])
        if 'f3_receive_attenuation' in symbols or ' ad9361_set_tx_attenuation' in symbols:
            raise RuntimeError('Unsafe private symbol exported')
        for name in ('z20_f3_start', 'z20_f3_stop', 'z20_f3_heartbeat', 'z20_set_tx_attenuation'):
            if name not in symbols:
                raise RuntimeError('Missing symbol '+name)
        digest = t.ssh(['sha256sum', remote+'/libad9361_f3.so']).split()[0]
        after = t.ssh(['sha256sum', baseline]).split()[0]
        if after != before:
            raise RuntimeError('Frozen receiver changed')
        record.update(status='PASS', library_sha256=digest, baseline_after=after,
                      symbols=symbols, log_sha256=sha(log))
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
        if not log.exists():
            log.write_text(repr(error), encoding='utf-8')
    write_evidence(evidence, record)
    print(json.dumps(record))
    if record['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
