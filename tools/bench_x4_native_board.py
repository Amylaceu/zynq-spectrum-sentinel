"""Freeze and run isolated CPU-only native runtime experiment on PYNQ."""
import argparse
import ast
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import tarfile
import numpy as np
from x2_transport import Transport,ROOT,REMOTE,PYTHON,sha,verified,write_evidence

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',required=True,type=int,choices=(1,2,3))
    args=parser.parse_args()
    tag='x4_native_board_r%d'%args.attempt
    work=ROOT/'build/work'/tag
    out=ROOT/'board/measurements'/(tag+'.json')
    if work.exists() or out.exists(): raise FileExistsError('Preserve previous evidence')
    bundle=work/'bundle';bundle.mkdir(parents=True)
    source=ROOT/'src/ps/sentinel/amc'
    frozen=verified(ROOT/'board/measurements/x4_cached_board_r3.json')
    model=ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    if sha(model)!=frozen['model_sha256']:raise ValueError('Model changed')
    for path in source.rglob('*'):
        if path.suffix not in ('.py','.c'):continue
        if path.suffix=='.py':ast.parse(path.read_text(),feature_version=(3,8))
        dest=bundle/'ps/sentinel/amc'/path.relative_to(source)
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (bundle/'ps/sentinel/__init__.py').write_text('')
    for name,digest in frozen['sources_sha256'].items():
        if not name.startswith('src/ps/sentinel/amc/'):continue
        data=subprocess.check_output(['git','show','cb2c15d:'+name],cwd=ROOT)
        import hashlib
        assert hashlib.sha256(data).hexdigest()==digest
        dest=bundle/'frozen'/Path(name).name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(data)
    (bundle/'model.npz').write_bytes(model.read_bytes())
    data=ROOT/'data/synthetic/amc_v2/test'
    labels=np.load(data/'label.npy',mmap_mode='r');snrs=np.load(data/'snr.npy',mmap_mode='r')
    ids=np.load(data/'sample_id.npy',mmap_mode='r');iq=np.load(data/'iq.npy',mmap_mode='r')
    # 13 SNRs: five per class at 10 dB, one at -4/0/4 dB, two at other SNRs.
    # Exactly 26 per class = 260 total, chosen before observing predictions.
    indices=np.concatenate([np.flatnonzero((labels==k)&(snrs==s))[:(5 if s==10 else 1 if s in (-4,0,4) else 2)]
                            for k in range(10) for s in range(-4,21,2)])
    assert len(indices)==260
    benchmark=np.flatnonzero(snrs[indices]==10)
    with (bundle/'captures.npz').open('xb') as stream:
        np.savez(stream,iq=iq[indices],label=labels[indices],snr=snrs[indices],
                 sample_id=ids[indices],benchmark_indices=benchmark)
    script=ROOT/'board/scripts/bench_x4_native.py'
    ast.parse(script.read_text(),feature_version=(3,8))
    (bundle/script.name).write_bytes(script.read_bytes())
    files={p.relative_to(bundle).as_posix():sha(p) for p in bundle.rglob('*') if p.is_file()}
    write_evidence(bundle/'manifest.json',dict(files=files,frozen_commit='cb2c15d',model_sha256=sha(model)))
    archive=work/'bundle.tar.gz'
    with tarfile.open(archive,'x:gz') as tar:
        for p in bundle.rglob('*'):
            if p.is_file():tar.add(p,arcname=p.relative_to(bundle).as_posix())
    t=Transport();remote=REMOTE+'/setup/'+tag
    t.ssh(['mkdir',remote]);t.copy(archive,t.target+':'+remote+'/bundle.tar.gz')
    check='import hashlib,pathlib,sys;assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()==sys.argv[2]'
    t.ssh(['python3','-c',check,remote+'/bundle.tar.gz',sha(archive)])
    t.ssh(['tar','-xzf',remote+'/bundle.tar.gz','-C',remote])
    boot=t.ssh(['cat','/proc/sys/kernel/random/boot_id']).strip()
    compiler=t.ssh(['gcc','--version'])
    compile_args=['gcc','-std=c99','-O2','-fPIC','-shared','-fno-fast-math','-ffp-contract=off',
                  '-Wall','-Wextra','-Werror',remote+'/ps/sentinel/amc/native/gardner.c',
                  '-o',remote+'/libsentinel_gardner.so','-lm']
    compiler+=t.ssh(compile_args,timeout=60)
    log=ROOT/'logs'/('X4_native_board_r%d.log'%args.attempt)
    text=t.ssh(['env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',
                PYTHON,'-I',remote+'/'+script.name,'--root',remote],timeout=300)
    log.write_text(text,encoding='utf-8')
    raw=work/'result.json'
    t.copy(t.target+':'+remote+'/result.json',raw)
    t.copy(t.target+':'+remote+'/result.json.sha256',Path(str(raw)+'.sha256'))
    t.copy(t.target+':'+remote+'/libsentinel_gardner.so',work/'libsentinel_gardner.so')
    result=verified(raw)
    assert result['boot_id']==boot and result['model_sha256']==sha(model)
    assert result['manifest_sha256']==sha(bundle/'manifest.json')
    assert result['library_sha256']==sha(work/'libsentinel_gardner.so')
    result.update(recorded_at_pc_utc=datetime.now(timezone.utc).isoformat(),
                  compiler=compiler,compile_args=compile_args,
                  source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in
                    [Path(__file__),script]+[p for p in source.rglob('*') if p.suffix in ('.py','.c')]},
                  archive_sha256=sha(archive),log_sha256=sha(log))
    write_evidence(out,result)
    print(text,flush=True)

if __name__=='__main__':main()
