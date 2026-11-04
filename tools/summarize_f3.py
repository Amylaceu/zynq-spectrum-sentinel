"""Audit existing F3 evidence and write a new summary; never access hardware."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/ps'))
from sentinel.release_support import sha, write_result
from sentinel.v_y3 import checked_y3_bundle


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Refusing to replace existing evidence')
    measurements = ROOT / 'board/measurements'
    files = [p for p in measurements.rglob('*') if p.is_file()
             and p.relative_to(measurements).parts[0].startswith('f3_')]
    sidecars = [p for p in files if p.name.endswith('.sha256')]
    for sidecar in sidecars:
        target = Path(str(sidecar)[:-7])
        require(target.is_file() and sha(target) == sidecar.read_text().split()[0],
                'Missing or altered evidence: ' + str(target))

    def load(name):
        return json.loads((measurements / name).read_text(encoding='utf-8'))

    demo = load('f3_demo_r2/verification.json')
    manifest = load('f3_demo_r2/download_manifest.json')
    raw = measurements / 'f3_demo_r2/raw'
    actual = {p.relative_to(raw).as_posix(): sha(p)
              for p in raw.rglob('*') if p.is_file()}
    require(actual == manifest['files'], 'Demo files differ from board manifest')
    require(sha(measurements / 'f3_demo_r2/execution.json') == manifest['execution_sha256'],
            'Supervisor execution digest differs')
    require(sha(ROOT / 'logs/F3_f3_demo_r2_board.log') == manifest['log_sha256'],
            'Board log differs')
    stopped = load('f3_final_stopped_readback.json')
    require(demo['status'] == 'PASS_FUNCTIONAL' and stopped['status'] == 'PASS',
            'Functional demo or final stop did not pass')
    evaluation = load('f3_evaluation_r1/result.json')
    require(sha(measurements / 'f3_capture_r1/result.json') == evaluation['capture_result_sha256'],
            'Evaluation capture result differs')
    require(sha(measurements / 'f3_evaluation_r1/predictions.npz') == evaluation['predictions_sha256'],
            'Evaluation predictions differ')
    for index, check in enumerate(evaluation['capture_checks']):
        require(sha(measurements / ('f3_capture_r1/class_%02d.npz' % index)) == check['sha256'],
                'Evaluation capture IQ differs')
    at10 = next(p for p in evaluation['curves']['ota'] if p['injected_reference_db'] == 10)
    for classes in (10, 8):
        matrix = at10['confusion_' + str(classes)]
        total = sum(sum(row) for row in matrix)
        accuracy = sum(row[i] for i, row in enumerate(matrix)) / total
        require(total == 500 and abs(accuracy-at10['accuracy_' + str(classes)]) < 1e-12,
                'Confusion matrix and reported accuracy disagree')

    library = load('f3_library_r1.json')
    require(sha(ROOT / 'build/f3_library/libad9361_f3.so') == library['library_sha256'],
            'Independent F3 library differs')
    bundle = ROOT / 'board/overlay/sentinel_v2_100m'
    accepted = checked_y3_bundle(bundle / 'sentinel_v2_100m.bit', image='sentinel_v2_100m')
    log = ROOT / 'logs/F3_final_regression_env.log'
    test_match = re.search(r'(\d+) passed, (\d+) skipped', log.read_text(encoding='utf-8'))
    require(test_match is not None, 'Missing passing regression summary')
    sources = list((ROOT / 'src/ps/sentinel').rglob('*.py'))
    sources += list((ROOT / 'tools').glob('*f3*.py'))
    sources += list((ROOT / 'board/scripts').glob('*f3*.py'))
    sources += [ROOT / p for p in ('board/scripts/demo_b.py', 'board/scripts/release_entry.py',
        'board/scripts/y3_postflight.py', 'tools/release_board.py',
        'src/ps/libad9361_pynq/Makefile.f3', 'src/ps/libad9361_pynq/app/f3_api_c.c',
        'src/ps/libad9361_pynq/app/f3_exports.map')]
    source_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(sources))}
    log_names = ('F3_final_regression.log', 'F3_final_regression_env.log',
                 'F3_demo_fix_regression.log', 'F3_demo_collect_r2.log', 'F3_f3_demo_r2_board.log')
    result = dict(status='FAIL_SPEC_WITH_FUNCTIONAL_PASS', functional_status='PASS_FUNCTIONAL',
        host_utc=datetime.now(timezone.utc).isoformat(), rf_access=False,
        baseline='sentinel_v2_100m; 100MHz; 3.84MSPS', frozen_image_checked=True,
        artifacts_sha256=accepted['artifacts_sha256'],
        independent_tx_library_sha256=library['library_sha256'],
        accepted_rx_library_sha256=library['baseline_after'],
        demo={k: v for k, v in demo.items() if k not in ('segments', 'host_utc')},
        accuracy_10class=at10['accuracy_10'], accuracy_8family=at10['accuracy_8'],
        confusion_matrices_recomputed=True, capture_windows=500,
        accuracy_scope=evaluation['scope'],
        broadband_25db_pass=load('f3_calibrate_r3/result.json')['broadband_25db_pass'],
        pd_10db_certified=load('f3_pd_r1/result.json')['pd_10db_certified'],
        calibrated_pfa_certified=load('f3_pfa_r1/result.json')['calibrated_pfa_certified'],
        human_reply='画面没问题',
        human_scope='Observed screen only; no claim of full three-cycle manual review or accuracy',
        software=dict(passed=int(test_match[1]), skipped=int(test_match[2]),
            initial_attempt='1 failed, 603 passed, 18 skipped, 1 error; Windows Tcl environment/capture',
            correction='Set installed TCL_LIBRARY/TK_LIBRARY; pytest -s; no functional change'),
        sidecars_verified=len(sidecars), downloaded_files_verified=len(actual),
        evidence_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)},
        source_sha256=source_hashes,
        log_sha256={name: sha(ROOT / 'logs' / name) for name in log_names},
        unmet=['8-family accuracy below 90%', 'Broadband CW calibration below 25dB',
               'Pd@10dB and operating Pfa not calibrated', 'Demo cycle exceeds approximately 2 minutes'],
        history_preserved=True,
        next_step='F4 waits for SD backup and configuration A confirmation; no new RF operation')
    write_result(args.output, result)
    print(json.dumps({k: result[k] for k in ('status', 'sidecars_verified',
        'downloaded_files_verified', 'accuracy_10class', 'accuracy_8family', 'software')}))


if __name__ == '__main__':
    main()
