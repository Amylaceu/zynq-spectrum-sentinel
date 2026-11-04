"""Stage a hashed offline runtime experiment under a fresh board directory."""
import argparse
import ast
import json
from pathlib import Path
import tarfile

import numpy as np

from x2_transport import Transport, ROOT, REMOTE, PYTHON, sha, verified, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True, type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    tag = 'x4_cached_board_r%d' % args.attempt
    out = ROOT/'board/measurements'/(tag+'.json')
    work = ROOT/'build/work'/tag
    if out.exists() or work.exists():
        raise FileExistsError('Preserve earlier optimization evidence')
    pc = verified(ROOT/'sim/results/x4_cached_pc_r1.json')
    source = ROOT/'src/ps/sentinel/amc'
    for name, digest in pc['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Source changed since PC equivalence: '+name)
    model = ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    if sha(model) != pc['model_sha256']:
        raise ValueError('Selected model changed')
    bundle = work/'bundle'
    bundle.mkdir(parents=True)
    for path in source.glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
        destination = bundle/'ps/sentinel/amc'/path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    (bundle/'ps/sentinel/__init__.py').write_text('"""Isolated offline experiment."""\n')
    (bundle/'model.npz').write_bytes(model.read_bytes())
    data = ROOT/'data/synthetic/amc_v2/test'
    labels = np.load(data/'label.npy', mmap_mode='r')
    snrs = np.load(data/'snr.npy', mmap_mode='r')
    ids = np.load(data/'sample_id.npy', mmap_mode='r')
    iq = np.load(data/'iq.npy', mmap_mode='r')
    indices = np.concatenate([np.flatnonzero((labels == k) & (snrs == 10))[:5] for k in range(10)])
    with (bundle/'captures.npz').open('xb') as stream:
        np.savez(stream, iq=iq[indices], label=labels[indices], sample_id=ids[indices])
    script = ROOT/'board/scripts/bench_x4_cached.py'
    ast.parse(script.read_text(), feature_version=(3, 8))
    (bundle/script.name).write_bytes(script.read_bytes())
    files = {path.relative_to(bundle).as_posix(): sha(path)
             for path in bundle.rglob('*') if path.is_file()}
    write_evidence(bundle/'manifest.json', dict(files=files, model_sha256=sha(model)))
    archive = work/'bundle.tar.gz'
    with tarfile.open(archive, 'x:gz') as tar:
        for path in bundle.rglob('*'):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(bundle).as_posix())
    transport = Transport()
    remote = REMOTE+'/setup/'+tag
    transport.ssh(['mkdir', remote])
    transport.copy(archive, transport.target+':'+remote+'/bundle.tar.gz')
    check = 'import hashlib,pathlib,sys;assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()==sys.argv[2]'
    transport.ssh(['python3', '-c', check, remote+'/bundle.tar.gz', sha(archive)])
    transport.ssh(['tar', '-xzf', remote+'/bundle.tar.gz', '-C', remote])
    boot = transport.ssh(['cat', '/proc/sys/kernel/random/boot_id']).strip()
    command = ['env', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
               PYTHON, '-I', remote+'/'+script.name, '--root', remote]
    log = ROOT/'logs'/('X4_cached_board_r%d.log' % args.attempt)
    log.write_text(transport.ssh(command, timeout=240), encoding='utf-8')
    raw = work/'result.json'
    transport.copy(transport.target+':'+remote+'/result.json', raw)
    transport.copy(transport.target+':'+remote+'/result.json.sha256', Path(str(raw)+'.sha256'))
    result = verified(raw)
    if result['boot_id'] != boot or result['bundle_sha256'] != sha(bundle/'manifest.json'):
        raise ValueError('Board experiment identity mismatch')
    if result['model_sha256'] != sha(model):
        raise ValueError('Board model mismatch')
    result.update(pc_bundle_archive_sha256=sha(archive), pc_equivalence_sha256=sha(ROOT/'sim/results/x4_cached_pc_r1.json'),
                  sources_sha256={path.relative_to(ROOT).as_posix(): sha(path)
                                  for path in [script, Path(__file__)] + sorted(source.glob('*.py'))},
                  log_sha256=sha(log), sample_ids=ids[indices].tolist())
    write_evidence(out, result)
    print(json.dumps(dict(status=result['status'], timing=result['timing'], speedup=result['median_speedup']), indent=2))


if __name__ == '__main__':
    main()
