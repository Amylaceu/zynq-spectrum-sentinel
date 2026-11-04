"""Preserve one FM component simulation attempt, including failure inputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from x2_transport import ROOT, sha, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--note', required=True)
    args = parser.parse_args()
    tag = 'y3_fm_r%d' % args.attempt
    result = ROOT/('sim/results/'+tag+'.json')
    archive = ROOT/('report/results/'+tag+'.zip')
    if result.exists() or archive.exists():
        raise FileExistsError('Preserve previous attempt')
    code = (ROOT/('logs/Y3_fm_r%d_exit.txt' % args.attempt)).read_text(encoding='utf-8-sig').strip()
    if code not in ('0', '1'):
        raise ValueError('Attempt not completed')
    log = ROOT/'sim/results/tb_fm_y3.log'
    passed = code == '0' and 'TB_RESULT: PASS Y3 FM' in log.read_text(errors='replace')
    names = ['src/rtl/audio_y3/fm_phase_y3.v', 'src/rtl/audio_y3/fm_audio_filter_y3.v',
             'sim/tb/tb_fm_y3.sv', 'tools/gen_y3_fm_vectors.py', 'tools/test_y3_fm.ps1',
             'tools/archive_y3_fm.py', 'sim/scripts/run_xsim.ps1',
             'logs/Y3_fm_r%d_controller.log' % args.attempt,
             'logs/Y3_fm_r%d_exit.txt' % args.attempt, 'sim/results/tb_fm_y3.log']
    vectors = ROOT/('build/work/y3_fm_vectors_r%d' % args.attempt)
    names += [p.relative_to(ROOT).as_posix() for p in sorted(vectors.glob('*')) if p.is_file()]
    manifest = {n: sha(ROOT/n) for n in names}
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(ROOT/name, name)
        z.writestr('MANIFEST.json', json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:
        for name, digest in manifest.items():
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                raise ValueError('Archive readback failed')
    archive.with_name(archive.name+'.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
    write_evidence(result, dict(status='PASS' if passed else 'FAIL', attempt=args.attempt,
        recorded_at_pc=datetime.now(timezone.utc).isoformat(), note=args.note,
        scope='Isolated fixed-point FM component, not PFB integration/routed timing/audio playback',
        archive=archive.relative_to(ROOT).as_posix(), archive_sha256=sha(archive),
        sources_sha256=manifest))
    print('Y3_FM_ARCHIVE_VERIFIED '+('PASS' if passed else 'FAIL'))


if __name__ == '__main__':
    main()
