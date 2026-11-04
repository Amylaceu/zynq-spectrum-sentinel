"""Freeze a completed audio sink integration simulation, including failures."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import zipfile
from x2_transport import ROOT, sha, write_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--note', required=True)
    args = parser.parse_args()
    tag = 'y3_sink_r%d' % args.attempt
    result, archive = ROOT / ('sim/results/' + tag + '.json'), ROOT / ('report/results/' + tag + '.zip')
    if result.exists() or archive.exists():
        raise FileExistsError('Preserve previous evidence')
    exitfile = ROOT / ('logs/Y3_sink_r%d_exit.txt' % args.attempt)
    code = exitfile.read_text(encoding='utf-8-sig').strip()
    if code not in ('0', '1'):
        raise ValueError('Simulation not finished')
    log = ROOT / 'build/work/xsim_tb_audio_sink_y3/xsim_console.log'
    passed = code == '0' and log.exists() and 'TB_RESULT: PASS Y3 audio sink' in log.read_text(errors='replace')
    files = set((ROOT / 'src/rtl/audio_y3').glob('*.v'))
    files.update(ROOT / n for n in ('sim/tb/tb_audio_sink_y3.sv', 'tools/test_y3_sink.ps1',
        'tools/archive_y3_sink.py', 'sim/scripts/run_xsim.ps1',
        'logs/Y3_sink_r%d_controller.log' % args.attempt))
    files.add(exitfile)
    files.update((ROOT / 'build/work/xsim_tb_audio_sink_y3').glob('*_console.log'))
    vectors = 'build/work/y3_sink_vectors_r3' if args.attempt == 3 else 'build/work/y3_fm_vectors_r3'
    files.update(p for p in (ROOT / vectors).glob('*') if p.is_file())
    if args.attempt == 3:
        files.add(ROOT / 'tools/gen_y3_sink_vectors.py')
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for name in hashes:
            z.write(ROOT / name, name)
        z.writestr('MANIFEST.json', json.dumps(hashes, indent=2) + '\n')
    with zipfile.ZipFile(archive) as z:
        for name, digest in hashes.items():
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                raise ValueError('Archive mismatch: ' + name)
    archive.with_name(archive.name + '.sha256').write_text(sha(archive) + '  ' + archive.name + '\n')
    write_evidence(result, dict(status='PASS' if passed else 'FAIL', attempt=args.attempt,
        note=args.note, recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        scope='Selected-channel FM/FIFO/I2S simulation; not full PFB/route/board/5min acceptance',
        sources_sha256=hashes, archive=archive.relative_to(ROOT).as_posix(), archive_sha256=sha(archive)))
    print('Y3_SINK_ARCHIVED ' + ('PASS' if passed else 'FAIL'))


if __name__ == '__main__':
    main()
