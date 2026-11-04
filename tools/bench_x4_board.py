"""Stage an isolated immutable benchmark bundle, run as normal SSH user.

No sudo, bitstream, library replacement, MMIO, DMA or RF initialization.
Existing deployed monitor code and radio state are not touched.
"""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import tarfile

import numpy as np

from x2_transport import Transport, ROOT, REMOTE, PYTHON, verified, sha, write_evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = p.parse_args()
    tag = 'x4_pc_r'+str(args.attempt)
    receipt = verified(ROOT/'board/measurements'/(tag+'.json'))
    if receipt['status'] not in ('PASS', 'FAIL_OR_SMOKE') or receipt['smoke_only']:
        raise ValueError('Completed production round required')
    work = ROOT/'build/work'/tag
    bundle = work/'board_benchmark'
    bundle.mkdir(exist_ok=False)
    data = ROOT/'data/synthetic/amc_v2'
    labels = np.load(data/'test/label.npy', mmap_mode='r')
    snrs = np.load(data/'test/snr.npy', mmap_mode='r')
    ids = np.load(data/'test/sample_id.npy', mmap_mode='r')
    iq = np.load(data/'test/iq.npy', mmap_mode='r')
    indices = np.concatenate([np.flatnonzero((labels == label) & (snrs == 10))[:5] for label in range(10)])
    with (bundle/'captures.npz').open('xb') as stream:
        np.savez(stream, iq=iq[indices], label=labels[indices], sample_id=ids[indices])
    exported = work/'model/amc_l1_int8.npz'
    if sha(exported) != receipt['export_sha256']:
        raise ValueError('Export changed since evaluation')
    (bundle/'model.npz').write_bytes(exported.read_bytes())
    for path in sorted((work/'source/src/ps/sentinel/amc').glob('*.py')):
        rel = 'src/ps/sentinel/amc/'+path.name
        if sha(path) != receipt['source_sha256'][rel]:
            raise ValueError('Frozen module changed')
        ast.parse(path.read_text(), feature_version=(3, 8))
        destination = bundle/'ps/sentinel/amc'/path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    # Minimal regular package prevents accidental imports of installed runtime.
    (bundle/'ps/sentinel/__init__.py').write_text('"""Isolated AMC benchmark package."""\n')
    script = ROOT/'board/scripts/bench_x4_inference.py'
    ast.parse(script.read_text(), feature_version=(3, 8))
    (bundle/script.name).write_bytes(script.read_bytes())
    manifest = dict(attempt=args.attempt, export_sha256=sha(exported), files={
        path.relative_to(bundle).as_posix():sha(path) for path in bundle.rglob('*') if path.is_file()})
    write_evidence(bundle/'manifest.json', manifest)
    archive = work/'board_benchmark.tar.gz'
    with tarfile.open(archive, 'x:gz') as tar:
        for path in bundle.rglob('*'):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(bundle).as_posix())
    transport = Transport()
    remote = REMOTE+'/setup/'+tag+'_offline'
    transport.ssh(['mkdir', remote])
    transport.copy(archive, transport.target+':'+remote+'/bundle.tar.gz')
    check = "import hashlib,pathlib,sys;p=pathlib.Path(sys.argv[1]);assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2]"
    transport.ssh(['python3', '-c', check, remote+'/bundle.tar.gz', sha(archive)])
    transport.ssh(['tar', '-xzf', remote+'/bundle.tar.gz', '-C', remote])
    boot_before = transport.ssh(['cat', '/proc/sys/kernel/random/boot_id']).strip()
    text = transport.ssh([PYTHON, '-I', remote+'/'+script.name, '--root', remote], timeout=180)
    log = ROOT/'logs'/('X4_board_r'+str(args.attempt)+'.log')
    log.write_text(text, encoding='utf-8')
    raw = work/'board_result.json'
    transport.copy(transport.target+':'+remote+'/result.json', raw)
    transport.copy(transport.target+':'+remote+'/result.json.sha256', Path(str(raw)+'.sha256'))
    result = verified(raw)
    if result['bundle_sha256'] != sha(bundle/'manifest.json') or result['boot_id'] != boot_before:
        raise ValueError('Board result identity mismatch')
    result['pc_bundle_archive_sha256'] = sha(archive)
    result['benchmark_script_sha256'] = sha(script)
    result['round_evidence_sha256'] = sha(ROOT/'board/measurements'/(tag+'.json'))
    result['log_sha256'] = sha(log)
    write_evidence(ROOT/'board/measurements'/('x4_board_r'+str(args.attempt)+'.json'), result)
    print(json.dumps({key:result[key] for key in ('median_ms', 'max_ms', 'all_under_100ms')}))


if __name__ == '__main__':
    main()
