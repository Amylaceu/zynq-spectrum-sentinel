"""Seal Y2 failed/successful deployment evidence without changing measurements."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from x2_transport import ROOT, sha, verified, write_evidence


def main():
    output = ROOT/'report/results/y2_board_checkpoint_1.zip'
    summary = ROOT/'board/measurements/y2_board_checkpoint_1.json'
    if output.exists() or summary.exists():
        raise FileExistsError('Checkpoint already sealed')
    analysis = verified(ROOT/'board/measurements/x5_station_r3_analysis.json')
    receipt = verified(ROOT/'board/measurements/x5_station_r3_execution.json')
    reports = verified(ROOT/'board/overlay/sentinel_v1d/acceptance.json')
    for name, digest in reports['report_sha256'].items():
        if sha(ROOT/'build/reports/sentinel_v1d'/name) != digest:
            raise ValueError('Audited report changed: '+name)
    for attempt in (2, 3):
        probe = ROOT/('board/measurements/x5_station_r%d_result_probe.json' % attempt)
        result = ROOT/('board/measurements/x5_station_r%d/result.json' % attempt)
        if probe.read_bytes() != result.read_bytes():
            raise ValueError('Probe does not match retrieved result')
        sidecar = Path(str(probe)+'.sha256')
        if not sidecar.exists():
            sidecar.write_text(sha(probe)+'  '+probe.name+'\n', encoding='ascii')
    files = set((ROOT/'logs').glob('X5_station*'))
    files.update((ROOT/'build').glob('x5_station*_runtime.tar.gz'))
    files.update(ROOT/name for name in (
        'logs/Y2_pc_regression.log', 'logs/Y2_archive_r2.log',
        'docs/x5_v1d_prebuild_r3.json', 'docs/x5_v1d_prebuild_r3.json.sha256'))
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files) if p.is_file()}
    payload = ROOT/'build/x5_station_r3_runtime.tar.gz'
    if sha(payload) != receipt['archive_sha256']:
        raise ValueError('Original station-r3 payload does not match receipt')
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in manifest:
            archive.write(ROOT/name, name)
        archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        for name, digest in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Archive member mismatch: '+name)
    paths = ('board/measurements/x5_station_r2_execution.json',
             'board/measurements/x5_station_r3_execution.json',
             'board/measurements/x5_station_r3_analysis.json',
             'board/measurements/x5_implementation_r2.json',
             'docs/x5_runtime_patch_2.json', 'docs/x5_v1d_prebuild_r2.json',
             'src/rtl/perf/perf_mon.v', 'tools/analyze_x5_board.py',
             'tools/tests/test_x5_board_analysis.py', 'tools/tests/test_x5_runtime_patch.py',
             'src/ps/tests/test_v1d_memory.py', 'src/ps/sentinel/v1d.py',
             'tools/archive_y2_board_checkpoint.py', 'docs/y2_board_checkpoint.md')
    value = dict(schema='y2-board-checkpoint-v1', recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 status=analysis['status'], human_visual='PENDING', z2_ui='INCOMPLETE',
                 hardware_implementation_attempt=2, station_deployment_attempts_used=3,
                 configuration='A', splitter_required=False, RF_TX_requested=False,
                 original_r3_prebuild='Historical software label only; not hardware/simulation evidence',
                 results=analysis['metrics'], pc_tests=dict(passed=229, log='logs/Y2_pc_regression.log'),
                 archive=output.relative_to(ROOT).as_posix(), archive_sha256=sha(output),
                 source_sha256={name: sha(ROOT/name) for name in paths},
                 archived_files_sha256=manifest, postflight=receipt['postflight'])
    write_evidence(summary, value)
    Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
    print('Y2_CHECKPOINT_SEALED files=%d status=%s' % (len(manifest), value['status']))


if __name__ == '__main__':
    main()
