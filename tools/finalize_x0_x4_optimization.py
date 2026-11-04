"""Verify and archive the isolated X2/X4 experiments without board access.

Run only after the r3 OOC audit finishes. This never changes acceptance status,
deployed sources, FPGA state or RF settings. Existing evidence is immutable.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'board/measurements/x0_x4_optimization_r1.json'
ARCHIVE = ROOT / 'report/results/x0_x4_optimization_r1.zip'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified(relative):
    path = ROOT / relative
    if sha(path) != Path(str(path) + '.sha256').read_text().split()[0]:
        raise ValueError('Evidence digest mismatch: ' + relative)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    Path(str(path) + '.sha256').write_text(sha(path) + '  ' + path.name + '\n', encoding='ascii')


def main():
    if OUT.exists() or ARCHIVE.exists():
        raise FileExistsError('Preserve prior optimization evidence')
    original = {
        'x0_acceptance_r2': 'PASS', 'x1_final_checkpoint': 'FAIL',
        'x2_deferred_summary': 'FAIL_TIMING_DEFERRED', 'x3_analysis': 'FAIL_ORIGINAL_X3_TARGETS',
        'x4_archive_integrity': 'PASS', 'x4_analysis_r3': 'FAIL'}
    for name, status in original.items():
        if verified('board/measurements/' + name + '.json')['status'] != status:
            raise ValueError('Original acceptance status changed: ' + name)
    pc_name = 'sim/results/x4_cached_pc_r1.json'
    board_name = 'board/measurements/x4_cached_board_r3.json'
    pc, board = verified(pc_name), verified(board_name)
    for record, key in ((pc, 'source_sha256'), (board, 'sources_sha256')):
        for relative, digest in record[key].items():
            if sha(ROOT / relative) != digest:
                raise ValueError('Frozen source changed: ' + relative)
    if board['pc_equivalence_sha256'] != sha(ROOT / pc_name):
        raise ValueError('PC/board provenance mismatch')
    model = ROOT / 'src/ps/models/weights/amc_v2/round_3/model.npz'
    if sha(model) != board['model_sha256'] or pc['model_sha256'] != board['model_sha256']:
        raise ValueError('Model identity mismatch')
    for relative, digest in pc['subset_metadata_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise ValueError('Test metadata changed: ' + relative)
    raw = ROOT / 'sim/results/x4_cached_pc_r1.npz'
    if sha(raw) != pc['raw_sha256'] or sha(raw) != Path(str(raw) + '.sha256').read_text().split()[0]:
        raise ValueError('PC raw measurements changed')
    with np.load(raw, allow_pickle=False) as arrays:
        for engine, stats in pc['timing'].items():
            values = arrays[engine]
            assert len(values) == stats['count'] == 150
            for key, value in (('median_ms', np.median(values)),
                               ('p95_ms', np.percentile(values, 95)), ('max_ms', np.max(values))):
                np.testing.assert_allclose(value, stats[key], rtol=0, atol=1e-9)

    rows = board['rows']
    assert len(rows) == 450 and len(set(board['sample_ids'])) == 50
    expected = {(repeat, sample, engine) for repeat in range(3)
                for sample in board['sample_ids'] for engine in board['timing']}
    observed = {(row['repeat'], row['sample_id'], row['engine']) for row in rows}
    assert expected == observed and len(observed) == 450
    for repeat in range(3):
        for sample in board['sample_ids']:
            paired = [row for row in rows if row['repeat'] == repeat and row['sample_id'] == sample]
            assert len({(row['predicted'], row['confidence'], row['label']) for row in paired}) == 1
    for engine, stats in board['timing'].items():
        values = np.array([row['elapsed_ms'] for row in rows if row['engine'] == engine])
        assert len(values) == stats['count'] == 150 and np.all(np.isfinite(values)) and np.all(values > 0)
        assert bool(np.all(values <= 100)) == stats['all_under_100ms']
        for key, value in (('median_ms', np.median(values)),
                           ('p95_ms', np.percentile(values, 95)), ('max_ms', np.max(values))):
            np.testing.assert_allclose(value, stats[key], rtol=0, atol=1e-9)
    for engine, value in board['median_speedup'].items():
        np.testing.assert_allclose(value, board['timing']['reference_int32']['median_ms'] /
                                   board['timing'][engine]['median_ms'], rtol=0, atol=1e-12)
    work = ROOT / 'build/work/x4_cached_board_r3'
    if sha(work / 'bundle.tar.gz') != board['pc_bundle_archive_sha256']:
        raise ValueError('Board bundle archive changed')
    if sha(work / 'bundle/manifest.json') != board['bundle_sha256']:
        raise ValueError('Board bundle manifest changed')
    if verified('build/work/x4_cached_board_r3/result.json')['rows'] != rows:
        raise ValueError('Raw board measurements differ')
    if sha(ROOT / 'logs/X4_cached_board_r3.log') != board['log_sha256']:
        raise ValueError('Board result log changed')

    prefix = ROOT / 'logs/X2_timing_ooc_r3'
    if Path(str(prefix) + '_exit.txt').read_text(encoding='utf-8-sig').strip() != '0':
        raise ValueError('OOC audit incomplete or failed')
    log = Path(str(prefix) + '.log').read_text(encoding='utf-8', errors='replace')
    if 'X2_TIMING_CANDIDATES_AUDIT_COMPLETE' not in log:
        raise ValueError('OOC completion marker absent')
    report_dir = ROOT / 'build/reports/x2_timing_candidates_r3'
    tops = ('drop_counter_reference', 'drop_counter_segmented', 'cfar_cluster_x1', 'cfar_cluster_timing_x2')
    timing = {}
    for top in tops:
        report = (report_dir / (top + '_timing.rpt')).read_text()
        summary = re.search(r'^\s*WNS\(ns\).*\n[^\n]*\n([^\n]+)', report, re.MULTILINE)
        if summary is None:
            raise ValueError('Timing summary missing: ' + top)
        values = summary.group(1).split()
        wns, whs = float(values[0]), float(values[4])
        match = re.search(r'X2_CANDIDATE_RESULT ' + top + r' WNS=([-\d.]+) WHS=([-\d.]+)', log)
        assert match and abs(float(match[1]) - wns) < .0001 and abs(float(match[2]) - whs) < .0001
        util = (report_dir / (top + '_utilization.rpt')).read_text()
        resources = {}
        for label in ('Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'):
            match = re.search(r'\|\s*' + label + r'\s*\|\s*([\d.]+)', util)
            if match:
                resources[label] = float(match[1])
        timing[top] = dict(wns_ns=wns, whs_ns=whs, resources=resources,
                           setup_and_hold_met=wns >= 0 and whs >= 0,
                           period_ns=4.069 if top.startswith('drop_') else 6.667)
    sim_logs = ['sim/results/tb_x2_drop_counter.log', 'sim/results/tb_x2_timing_candidates.log']
    for relative in sim_logs:
        text = (ROOT / relative).read_text()
        assert 'TB_RESULT: PASS' in text and 'Fatal:' not in text
    tests = ROOT / 'logs/X0_X4_optimization_tests_r1.log'
    assert '172 passed' in tests.read_text()
    files = [Path(__file__).relative_to(ROOT).as_posix(), pc_name, board_name,
             'sim/results/x4_cached_pc_r1.npz',
             'board/scripts/bench_x4_cached.py', 'tools/bench_x4_cached_board.py',
             'tools/benchmark_x4_cached.py', 'src/ps/sentinel/amc/infer_cached.py',
             'src/ps/tests/test_amc_cached.py', 'tools/test_x2_timing_candidates.ps1',
             'tools/audit_x2_timing_candidates.ps1', 'build/scripts/audit_x2_timing_candidates.tcl',
             'src/rtl/x2_opt/drop_counter_segmented.v', 'src/rtl/x2_opt/cfar_cluster_timing_x2.v',
             'src/rtl/cfar_x1/cfar_cluster_x1.v', 'sim/tb/drop_counter_reference.v',
             'sim/tb/tb_x2_drop_counter.sv', 'sim/tb/tb_x2_timing_candidates.sv',
             'logs/X2_timing_ooc_r3.log', 'logs/X4_cached_board_r3.log',
             'logs/X2_timing_ooc_r1_console.log', 'logs/X2_timing_ooc_r2_console.log',
             'logs/X4_cached_board_r1_stderr.log', 'logs/X4_cached_board_r2_stderr.log',
             'build/work/x4_cached_board_r3/bundle/manifest.json',
             'logs/X0_X4_optimization_tests_r1.log'] + sim_logs
    files += [path.relative_to(ROOT).as_posix() for path in sorted(report_dir.glob('*.rpt'))]
    files += sorted(board['sources_sha256'])
    files += ['board/measurements/' + name + '.json' for name in original]
    files = sorted(set(files))
    hashes = {relative: sha(ROOT / relative) for relative in files}
    # Keep diagnostic logs inside the evidence ZIP; never stage logs/ directly.
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            archive.write(ROOT / relative, relative)
        archive.writestr('manifest.json', json.dumps(hashes, indent=2) + '\n')
    with zipfile.ZipFile(ARCHIVE) as archive:
        for relative, digest in hashes.items():
            assert hashlib.sha256(archive.read(relative)).hexdigest() == digest
    Path(str(ARCHIVE) + '.sha256').write_text(sha(ARCHIVE) + '  ' + ARCHIVE.name + '\n', encoding='ascii')
    write_json(OUT, dict(
        status='VERIFIED_ISOLATED_EXPERIMENTS', recorded_at_pc_utc=datetime.now(timezone.utc).isoformat(),
        formal_status={'X0': 'DONE', 'X1': 'FAIL', 'X2': 'FAIL', 'X3': 'FAIL', 'X4': 'FAIL'},
        no_rf_access=True, deployment_changed=False, new_full_system_implementation=False,
        x2_ooc=timing, x2_simulation='PASS cycle equivalence, stalls, carry boundaries, saturation and reset',
        x4_board_timing=board['timing'], x4_board_median_speedup=board['median_speedup'],
        x4_pc_exact_logits=pc['logit_exact_captures'], x4_board_exact_captures=50,
        x4_board_measurements=450, x4_model_sha256=board['model_sha256'],
        board_boot_id=board['boot_id'], python_tests={'scope': 'src/ps/tests', 'passed': 172},
        original_evidence_status=original,
        x3_latency_planning=dict(
            measured_total_median_us=629.9, frame_iq_samples=2048, sample_intervals=2047,
            frame_interval_convention='First to last accepted IQ spans N-1 sample intervals',
            measured_fs_hz=3840000, estimated_remaining_us=629.9 - 2047 / 3.84,
            collection_only_min_fs_hz_exclusive=2047 / 200e-6,
            constant_remaining_estimates_us={str(fs): 2047 / fs * 1e6 + 629.9 - 2047 / 3.84
                                            for fs in (7680000, 15360000, 24576000, 30720000)},
            qualification='Arithmetic planning only; no new latency measurement, no acceptance change'),
        source_and_report_sha256=hashes, archive=ARCHIVE.relative_to(ROOT).as_posix(),
        archive_sha256=sha(ARCHIVE),
        limitations=['OOC virtual zero-delay ports do not represent board or whole-system timing',
                     'No new whole-system implementation, RF test, UI or bandwidth acceptance',
                     'X4 timings are synthetic 50-capture paired tests, not original acceptance set',
                     'Exact FP32 dot products use floating-point arithmetic; no INT32 MAC speed claim',
                     'PC and board wall clocks differ; PC UTC and board boot_id identify this record'],
        decisions=['Keep deployed RTL and Predictor unchanged',
                   'Preserve X1-X4 failures and original thresholds',
                   'Do not repeat exhausted experiment rounds automatically']))
    print('X0_X4_OPTIMIZATION_VERIFIED', OUT.relative_to(ROOT).as_posix())
    print(json.dumps(timing, indent=2))


if __name__ == '__main__':
    main()
