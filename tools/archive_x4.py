"""Archive evaluated models and frozen sources outside ignored build/work.

An explicitly failed experimental candidate is usable for integration, but
its manifest never claims X4 acceptance or over-the-air accuracy.
"""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

from x2_transport import ROOT, sha, verified, write_evidence


def archive(attempt, select=False):
    tag = 'x4_pc_r'+str(attempt)
    work = ROOT/'build/work'/tag
    receipt_path = ROOT/'board/measurements'/(tag+'.json')
    receipt = verified(receipt_path)
    analysis_path = ROOT/'board/measurements'/('x4_analysis_r'+str(attempt)+'.json')
    analysis = verified(analysis_path)
    if receipt['smoke_only'] or analysis['board'] is None:
        raise ValueError('Production evaluation and board benchmark required')
    destination = ROOT/'src/ps/models/weights/amc_v2'/('round_'+str(attempt))
    destination.mkdir(parents=True, exist_ok=False)
    for rel, digest in receipt['source_sha256'].items():
        if sha(work/'source'/rel) != digest:
            raise ValueError('Frozen source mismatch: '+rel)
    model = work/'model/amc_l1_int8.npz'
    if sha(model) != receipt['export_sha256']:
        raise ValueError('Export mismatch')
    shutil.copyfile(model, destination/'model.npz')
    Path(str(destination/'model.npz')+'.sha256').write_text(
        sha(destination/'model.npz')+'  model.npz\n', encoding='ascii')
    provenance = ROOT/'report/results'/('x4_sources_r'+str(attempt)+'.zip')
    provenance.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(provenance, 'x', compression=zipfile.ZIP_DEFLATED) as zipped:
        for rel in sorted(receipt['source_sha256']):
            zipped.write(work/'source'/rel, rel)
        for name in ('frozen_sources.json', 'model/history.json'):
            zipped.write(work/name, name)
    Path(str(provenance)+'.sha256').write_text(sha(provenance)+'  '+provenance.name+'\n', encoding='ascii')
    metadata = dict(attempt=attempt, step='X4', status=analysis['status'],
                    usage='accepted_synthetic_candidate' if analysis['status']=='PASS' else 'experimental_failed_candidate',
                    fs=480000, capture_len=4096, precision='mixed INT8 MAC/FP32 statistics and scale',
                    model='model.npz', model_sha256=sha(model),
                    accuracy_snr10=analysis['metrics']['int8']['accuracy_vs_snr']['10'],
                    gates=analysis['gates'],
                    runtime_sha256={Path(k).name:v for k,v in receipt['source_sha256'].items()
                                    if k.startswith('src/ps/sentinel/amc/')},
                    evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in
                                     (receipt_path, analysis_path, provenance)},
                    limitation='Synthetic data only; confidence is uncalibrated; no OTA acceptance')
    write_evidence(destination/'manifest.json', metadata)
    if select:
        # Selection is explicit and immutable; a later model needs a new named
        # selection manifest, never replacement of measured evidence.
        selection = dict(attempt=attempt, status=analysis['status'],
                         manifest=(destination/'manifest.json').relative_to(ROOT).as_posix(),
                         manifest_sha256=sha(destination/'manifest.json'),
                         model=(destination/'model.npz').relative_to(ROOT).as_posix(),
                         model_sha256=sha(destination/'model.npz'),
                         limitation=metadata['limitation'])
        write_evidence(destination.parent/'selected.json', selection)
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1,2,3), required=True)
    parser.add_argument('--select', action='store_true')
    args = parser.parse_args()
    archive(args.attempt, args.select)
