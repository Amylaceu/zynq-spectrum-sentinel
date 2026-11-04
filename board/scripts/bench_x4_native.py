"""Offline native Gardner validation against frozen pre-change runtime."""
import argparse
import ctypes
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def compare(left, right, differences):
    if isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            compare(left[key],right[key],differences)
    elif isinstance(left, list):
        assert len(left)==len(right)
        for a,b in zip(left,right): compare(a,b,differences)
    elif isinstance(left, np.ndarray):
        assert left.shape==right.shape
        delta=float(np.max(np.abs(left-right))) if left.size else 0.
        differences['max_symbol_error']=max(differences['max_symbol_error'],delta)
        np.testing.assert_allclose(left,right,rtol=0,atol=1e-6)
        differences['all_exact'] &= bool(np.array_equal(left,right))
    elif isinstance(left, (float,np.floating)):
        delta=abs(float(left)-float(right))
        differences['max_scalar_error']=max(differences['max_scalar_error'],delta)
        np.testing.assert_allclose(left,right,rtol=0,atol=1e-10)
        differences['all_exact'] &= bool(left==right)
    else:
        assert left==right

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    root=Path(parser.parse_args().root).resolve()
    manifest=json.loads((root/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        path=(root/name).resolve()
        assert root in path.parents and sha(path)==digest,name
    # Load preserved original source as a distinct package; no monkey-patching.
    spec=importlib.util.spec_from_file_location('frozen_amc',root/'frozen/__init__.py',
                                              submodule_search_locations=[str(root/'frozen')])
    package=importlib.util.module_from_spec(spec)
    sys.modules['frozen_amc']=package; spec.loader.exec_module(package)
    Frozen=importlib.import_module('frozen_amc.infer_np').Predictor
    old_gardner=importlib.import_module('frozen_amc.fine').gardner
    sys.path.insert(0,str(root/'ps'))
    from sentinel.amc.infer_np import Predictor
    from sentinel.amc.infer_native import NativePredictor,NativeGardner
    lib=root/'libsentinel_gardner.so'
    reference=Frozen(root/'model.npz')
    portable=Predictor(root/'model.npz')
    native=NativePredictor(root/'model.npz',lib)
    recovery=NativeGardner(lib)
    rng=np.random.default_rng(20261103)
    kernel_max_error=0.
    for sps in (4.,4.25,5.5,7.999,8.,8.125,11.5,15.75,16.):
        for kind in range(4):
            x=(rng.standard_normal(4096)+1j*rng.standard_normal(4096))
            if kind==1: x[:]=1+0j
            if kind==2: x[:]=0
            if kind==3: x*=100
            left,right=old_gardner(x,sps),recovery(x,sps)
            assert left.shape==right.shape
            error=float(np.max(np.abs(left-right)))
            kernel_max_error=max(kernel_max_error,error)
            np.testing.assert_allclose(left,right,rtol=0,atol=1e-10)
    for bad in (np.zeros(20),np.full(4096,np.nan),np.zeros((2,4096))):
        try: recovery(bad,8)
        except ValueError: pass
        else: raise AssertionError('Invalid samples accepted')
    for bad in (0,3.99,16.01,float('nan')):
        try: recovery(np.ones(4096),bad)
        except ValueError: pass
        else: raise AssertionError('Invalid sps accepted')
    pointer=ctypes.POINTER(ctypes.c_double)
    invalid=recovery._run(pointer(),4096,8.,0.,pointer(),4096)
    assert invalid<0
    small=np.empty(1,dtype=np.complex128); source=np.ones(4096,dtype=np.complex128)
    assert recovery._run(source.ctypes.data_as(pointer),4096,8.,0.,small.ctypes.data_as(pointer),1)==-3
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    difference=dict(all_exact=True,max_symbol_error=0.,max_scalar_error=0.)
    with np.load(root/'captures.npz',allow_pickle=False) as data:
        iq,labels,ids,snr=data['iq'],data['label'],data['sample_id'],data['snr']
        bench=data['benchmark_indices']
    assert iq.shape==(260,2,4096) and iq.dtype==np.int16
    assert len(set(ids.tolist()))==260 and len(bench)==50
    assert np.all(snr[bench]==10)
    validation=[]
    for index,capture in enumerate(iq):
        baseline=reference.predict(capture)
        compare(baseline,portable.predict(capture),difference)
        accelerated=native.predict(capture)
        compare(baseline,accelerated,difference)
        validation.append(dict(sample_id=int(ids[index]),snr_db=int(snr[index]),
                               label=int(labels[index]),predicted=baseline[0]['class_index'],
                               native_predicted=accelerated[0]['class_index']))
    engines=(reference,native); names=('frozen_reference','native_gardner')
    for engine in engines:
        for index in bench[:3]: engine.predict(iq[index])
    rows=[]
    for repeat in range(3):
        for position,index in enumerate(bench):
            outputs={}
            for which in ((position+repeat)%2,1-(position+repeat)%2):
                start=time.perf_counter()
                outputs[which]=engines[which].predict(iq[index])
                ms=(time.perf_counter()-start)*1000
                rows.append(dict(repeat=repeat,sample_id=int(ids[index]),label=int(labels[index]),
                                 engine=names[which],elapsed_ms=ms,predicted=outputs[which][0]['label']))
            compare(outputs[0],outputs[1],difference)
    assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    stats={}
    for name in names:
        values=np.array([row['elapsed_ms'] for row in rows if row['engine']==name])
        stats[name]=dict(count=len(values),median_ms=float(np.median(values)),
                         p95_ms=float(np.percentile(values,95)),max_ms=float(values.max()),
                         over_100ms=int(np.sum(values>100)))
    result=dict(status='PASS_RUNTIME_EQUIVALENCE',formal_x4_status='FAIL',boot_id=boot,
                no_rf_access=True,deployment_default_changed=False,model_sha256=sha(root/'model.npz'),
                library_sha256=sha(lib),manifest_sha256=sha(root/'manifest.json'),
                tolerances=dict(symbol_abs=1e-6,scalar_abs=1e-10,rtol=0),
                difference=difference,kernel_cases=36,kernel_max_error=kernel_max_error,
                invalid_input_checks=9,validation=validation,rows=rows,timing=stats,
                platform=platform.platform(),numpy=np.__version__,python=sys.version,
                limitations=['260 synthetic equivalence captures across 13 SNRs; not full accuracy reacceptance',
                             'Timing uses 50 SNR10 captures repeated three times',
                             'No RF, new bitstream, DMA, UI or training changes'])
    out=root/'result.json'
    with out.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    Path(str(out)+'.sha256').write_text(sha(out)+'  result.json\n')
    print(json.dumps(dict(status=result['status'],difference=difference,timing=stats)),flush=True)

if __name__=='__main__': main()
