"""Preserve one completed failed X2 implementation without replacing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from x2_transport import ROOT, sha, verified, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    tag = 'r%d' % args.attempt
    if (ROOT/('logs/X2_v1c_implementation_%s_exit.txt' % tag)).read_text().strip() != '1':
        raise RuntimeError('Only archive a completed failed implementation')
    frozen_path = ROOT/('docs/x2_v1c_prebuild_%s.json' % tag)
    frozen = verified(frozen_path)
    for name, digest in frozen['sources_sha256'].items():
        if sha(ROOT/name) != digest:
            raise RuntimeError('Frozen input changed before archival: '+name)
    evidence_path = ROOT/('docs/x2_implementation_%s_failure.json' % tag)
    if evidence_path.exists() or Path(str(evidence_path)+'.sha256').exists():
        raise FileExistsError('Preserve previous failure evidence: '+str(evidence_path))
    archive = ROOT/('build/reports/sentinel_v1c_%s_failed' % tag)
    archive.mkdir(exist_ok=False)
    project = ROOT/'build/work/adi_hdl/projects/fmcomms2/sentinel_v1c'
    files = {ROOT/name for name in frozen['sources_sha256']}
    files |= {frozen_path, Path(str(frozen_path)+'.sha256')}
    files |= {p for p in (project/'sentinel_v1c.runs/impl_1').rglob('*') if p.is_file()}
    files |= {p for p in (project/'sentinel_v1c.sdk').rglob('*') if p.is_file()}
    files |= set(project.glob('timing_*.log'))
    files |= set((ROOT/'logs').glob('X2_v1c_*'+tag+'*'))
    files |= set((ROOT/'logs').glob('X2_retry_runner_'+tag+'*'))
    files |= set((ROOT/'logs').glob('X2_final_audit_'+tag+'*'))
    retry_report = ROOT/('build/reports/sentinel_v1c/retry_%s_timing.rpt' % tag)
    if retry_report.is_file():
        files.add(retry_report)
    bundle = archive/'failed_build.zip'
    hashes = {}
    with zipfile.ZipFile(bundle, 'x', compression=zipfile.ZIP_STORED) as output:
        for path in sorted(files):
            name = path.relative_to(ROOT).as_posix()
            hashes[name] = sha(path)
            output.write(path, name)
    # Verify archived bytes, rather than trusting a successful copy operation.
    with zipfile.ZipFile(bundle) as saved:
        for name, digest in hashes.items():
            if hashlib.sha256(saved.read(name)).hexdigest() != digest:
                raise RuntimeError('Archive verification failed: '+name)
    result = dict(status='FAIL_TIMING', attempt=args.attempt, board_loaded=False,
        reason='Implementation rejected routed setup/hold timing; no deployment or board test',
        archive=bundle.relative_to(ROOT).as_posix(), archive_sha256=sha(bundle),
        files_sha256=hashes)
    write_evidence(evidence_path, result)
    print('X2_FAILED_BUILD_ARCHIVED files='+str(len(hashes)), flush=True)


if __name__ == '__main__':
    main()
