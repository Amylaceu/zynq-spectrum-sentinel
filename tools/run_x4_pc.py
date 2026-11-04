"""Freeze source, generate/train/export/evaluate one immutable X4 round.

Launch in background from PowerShell. No board access, credentials or radio.
Each round gets its own sources/checkpoint/logs; previous evidence is never
overwritten. A smoke run does not consume a production accuracy attempt.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--data', default='data/synthetic/amc_v2')
    args = parser.parse_args()
    tag = ('x4_smoke_r' if args.smoke else 'x4_pc_r')+str(args.attempt)
    work = ROOT/'build/work'/tag
    receipt = ROOT/'board/measurements'/(tag+'.json')
    if work.exists() or receipt.exists():
        raise FileExistsError('Round already exists; preserve it')
    source = work/'source'
    source.mkdir(parents=True)
    files = []
    for directory in ('sim/golden', 'src/ps/models', 'src/ps/sentinel/amc'):
        files.extend(sorted((ROOT/directory).glob('*.py')))
    files.append(Path(__file__).resolve())
    inputs = {}
    for path in files:
        rel = path.relative_to(ROOT)
        destination = source/rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        inputs[rel.as_posix()] = sha(destination)
    save(work/'frozen_sources.json', inputs)
    record = dict(step='X4', attempt=args.attempt, smoke_only=args.smoke,
                  started_utc=datetime.now(timezone.utc).isoformat(), source_sha256=inputs,
                  python=sys.version, status='ERROR', stages=[])
    data = ROOT/args.data
    model = work/'model'
    exported = model/'amc_l1_int8.npz'
    evaluation = ROOT/'board/measurements'/(tag+'_evaluation.json')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS=str(args.threads),
               MKL_NUM_THREADS=str(args.threads), PYTHONUTF8='1')

    def run(name, module, arguments):
        log = ROOT/'logs'/(tag.replace('x4_', 'X4_')+'_'+name+'.log')
        if log.exists():
            raise FileExistsError(str(log))
        command = [sys.executable, '-u', '-m', module]+list(map(str, arguments))
        print('START '+name, flush=True)
        with log.open('x', encoding='utf-8') as stream:
            process = subprocess.run(command, cwd=source, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, check=False)
        record['stages'].append(dict(name=name, exit_code=process.returncode,
                                     log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log)))
        if process.returncode:
            raise RuntimeError(name+' failed: '+str(process.returncode))
        print('COMPLETE '+name, flush=True)

    try:
        if not (data/'manifest.json').exists():
            run('dataset', 'src.ps.models.make_dataset_v2',
                ['--out', data, '--workers', 4, '--per-cell', 10 if args.smoke else 2000])
        # Dataset must have been generated using exactly this shared frontend.
        manifest = json.loads((data/'manifest.json').read_text())
        for rel, digest in manifest['sources'].items():
            if inputs.get(rel) != digest:
                raise ValueError('Frozen source differs from dataset: '+rel)
        run('train', 'src.ps.models.amc_l1',
            ['--data', data, '--out', model, '--epochs', args.epochs,
             '--threads', args.threads, '--seed', 20261102+args.attempt]+(['--smoke'] if args.smoke else []))
        run('export', 'src.ps.models.export_int8_v2',
            ['--checkpoint', model/'amc_l1_fp32.pt', '--out', exported])
        run('evaluation', 'src.ps.models.amc_v2_eval',
            ['--data', data, '--l1', model/'amc_l1_fp32.pt', '--export', exported,
             '--out', evaluation, '--threads', args.threads])
        result = json.loads(evaluation.read_text())
        record['status'] = 'SMOKE_ONLY' if args.smoke else result['pc_status']
        record['evaluation_sha256'] = sha(evaluation)
        record['dataset_sha256'] = sha(data/'manifest.json')
        record['export_sha256'] = sha(exported)
    except BaseException as error:
        record['error'] = str(error)
        traceback.print_exc()
    finally:
        record['frozen_sources_unchanged'] = all(sha(source/rel) == digest for rel,digest in inputs.items())
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save(receipt, record)
        print('X4_RESULT '+record['status'], flush=True)
    if record['status'] == 'ERROR':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
