"""Verify all three immutable X4 rounds and the selected integration model.

Run after archive_x4.py; does not train, change selection, or access hardware.
Writes a separate evidence index with hashes, never overwriting measurements.
"""
from pathlib import Path
import zipfile

from x2_transport import ROOT, sha, verified, write_evidence


def verify():
    models = ROOT/'src/ps/models/weights/amc_v2'
    selected = verified(models/'selected.json')
    index, rounds = {}, []
    for attempt in (1, 2, 3):
        execution = verified(ROOT/'board/measurements'/('x4_pc_r%d.json' % attempt))
        analysis_path = ROOT/'board/measurements'/('x4_analysis_r%d.json' % attempt)
        analysis = verified(analysis_path)
        manifest_path = models/('round_%d' % attempt)/'manifest.json'
        manifest = verified(manifest_path)
        model = manifest_path.parent/'model.npz'
        if sha(model) != manifest['model_sha256'] or sha(model) != execution['export_sha256']:
            raise ValueError('Archived export mismatch')
        for rel, digest in manifest['evidence_sha256'].items():
            if sha(ROOT/rel) != digest:
                raise ValueError('Archive provenance mismatch: '+rel)
        archive = ROOT/'report/results'/('x4_sources_r%d.zip' % attempt)
        with zipfile.ZipFile(archive) as zipped:
            import hashlib
            for rel, digest in execution['source_sha256'].items():
                if hashlib.sha256(zipped.read(rel)).hexdigest() != digest:
                    raise ValueError('Archived source mismatch: '+rel)
        if manifest['status'] != analysis['status']:
            raise ValueError('Manifest acceptance differs from independent analysis')
        rounds.append(dict(attempt=attempt, status=analysis['status'],
                           int8_snr10=analysis['metrics']['int8']['accuracy_vs_snr']['10'],
                           gates=analysis['gates'], board_median_ms=analysis['board']['median_ms'],
                           board_max_ms=analysis['board']['max_ms']))
    if sha(ROOT/selected['model']) != selected['model_sha256']:
        raise ValueError('Selected model digest mismatch')
    if sha(ROOT/selected['manifest']) != selected['manifest_sha256']:
        raise ValueError('Selected manifest digest mismatch')
    chosen = verified(ROOT/selected['manifest'])
    for name, digest in chosen['runtime_sha256'].items():
        if sha(ROOT/'src/ps/sentinel/amc'/name) != digest:
            raise ValueError('Current runtime differs from selected evaluated source: '+name)
    for path in sorted((ROOT/'board/measurements').glob('x4_*')):
        if path.suffix in ('.json', '.npz'):
            if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
                raise ValueError('Measurement digest mismatch: '+path.name)
            index[path.relative_to(ROOT).as_posix()] = sha(path)
    regression = ROOT/'logs/X4_full_regression.log'
    text = regression.read_text(encoding='utf-8')
    if 'passed' not in text or 'failed' in text or 'ERROR' in text:
        raise ValueError('Full regression did not pass')
    result = dict(step='X4', mode='archive_integrity_not_acceptance_override',
                  status='PASS', rounds=rounds, selected=selected,
                  measurements_sha256=index, verifier_sha256=sha(Path(__file__)),
                  regression_summary=text.strip().splitlines()[-1],
                  regression_log_sha256=sha(regression))
    write_evidence(ROOT/'board/measurements/x4_archive_integrity.json', result)
    print('X4_ARCHIVE_VERIFIED', len(index), 'measurements')


if __name__ == '__main__':
    verify()
