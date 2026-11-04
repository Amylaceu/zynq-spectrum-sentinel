"""Archive a Z10 development checkpoint; never issue a deployment acceptance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--adc-log', default='sim/results/tb_adc_tap_v2.log')
    parser.add_argument('--adc-words', type=int, choices=(4096, 8192), default=4096)
    parser.add_argument('--software-log', default='logs/Z10_clock_r2_console.log')
    parser.add_argument('--software-tests', type=int, default=23)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_]+', args.tag):
        parser.error('Use a portable checkpoint tag')
    result = ROOT / ('board/measurements/z10_checkpoint_' + args.tag + '.json')
    archive = ROOT / ('report/results/z10_checkpoint_' + args.tag + '.zip')
    for path in (result, archive, Path(str(result)+'.sha256'), Path(str(archive)+'.sha256')):
        if path.exists():
            raise FileExistsError('Preserve previous checkpoint: ' + str(path))

    clock_log = ROOT / 'logs/Z10_clock_r2_console.log'
    adc_log = ROOT / args.adc_log
    software_log = ROOT / args.software_log
    for path in (clock_log, adc_log):
        raw = path.read_text(encoding='utf-8', errors='replace')
        if 'PASS' not in raw or re.search(r'^Error:|^ERROR:|^Fatal:', raw, re.M):
            raise ValueError('Invalid regression log: ' + str(path))
    if (str(args.software_tests)+' passed') not in software_log.read_text(encoding='utf-8-sig'):
        raise ValueError('Missing clock-sensitive software result')
    if (str(args.adc_words)+' checked words') not in adc_log.read_text():
        raise ValueError('ADC word count does not match the actual simulation')
    comparison_path = ROOT / 'sim/results/z10_clock_r2/source_compare.json'
    comparison = json.loads(comparison_path.read_text())
    if comparison['status'] != 'passed' or comparison['compared_words'] != 16384:
        raise ValueError('Incomplete source comparison')
    cfar_path = ROOT / 'sim/results/v2_cfar_r1.json'
    if sha(cfar_path.read_bytes()) != Path(str(cfar_path)+'.sha256').read_text().split()[0]:
        raise ValueError('CFAR receipt hash mismatch')
    cfar = json.loads(cfar_path.read_text())
    for name, digest in cfar['source_sha256'].items():
        if sha((ROOT/name).read_bytes()) != digest:
            raise ValueError('CFAR source changed: '+name)
    if cfar['status'] != 'PASS' or cfar['cases'] != 18:
        raise ValueError('Incomplete CFAR comparison')

    members = set()
    for folder in ('src/hw/sentinel_v2_100m', 'src/rtl/adc_tap_v2',
                   'src/rtl/cfar_v2', 'src/rtl/audio_y3', 'sim/results/z10_clock_r2'):
        members.update(path for path in (ROOT/folder).rglob('*') if path.is_file())
    for pattern in ('build/scripts/*v2*.tcl', 'tools/*v2*.ps1',
                    'build/reports/sentinel_v2_100m/**/*.rpt',
                    'build/reports/sentinel_v2_100m/**/endpoint_audit.txt',
                    'build/reports/sentinel_v2_100m/power_inspection_r1/*_cells.txt'):
        members.update(ROOT.glob(pattern))
    for pattern in ('tools/*v2*.py', 'tools/*z10*.py',
                    'board/measurements/z10_*.json*',
                    'board/measurements/t5_*.json*',
                    'build/reports/sentinel_v2_100m/inputs_*.json*'):
        members.update(ROOT.glob(pattern))
    for name in ('src/ps/sentinel/params.py', 'src/ps/sentinel/v2.py',
                 'src/ps/sentinel/v_y3.py', 'src/ps/sentinel/v1.py',
                 'src/ps/sentinel/audio_y3.py', 'src/ps/tests/test_v2_clock.py',
                 'src/ps/tests/test_audio_y3.py', 'tools/tests/test_z10_audit.py',
                 'tools/tests/test_z10_impl_policy.py',
                 'tools/tests/test_freeze_v2_options.py',
                 'tools/tests/test_run_y3_board.py',
                 'src/ps/sentinel/app/selftest_x1.py',
                 'board/scripts/run_y3_tone.py', 'board/scripts/run_y3_audio.py',
                 'board/scripts/y3_postflight.py', 'tools/run_y3_tone.py',
                 'tools/run_y3_board.py',
                 'sim/tb/tb_adc_tap_v2.sv', 'sim/tb/tb_cfar_v2.sv',
                 'sim/tb/tb_src_mux.sv', 'sim/tb/tb_perf_mon.sv',
                 'sim/scripts/run_xsim.ps1', 'tools/export_src_vectors.py',
                 'tools/record_z10_checkpoint.py', 'tools/verify_cfar_v2.py',
                 'tools/inspect_z10_power.ps1',
                 'build/scripts/inspect_z10_power.tcl',
                 'build/scripts/z10_impl_policy.tcl',
                 'docs/timing_closure_workflow.md', 'docs/timing_closure_strategy.md',
                 'docs/z10_progress.md', 'docs/z10_t5_next.md',
                 'docs/y3_audio_progress.md', 'runbook/STATUS.md', 'runbook/CONTEXT.md',
                 'report/llm_logs/Z10_clock_hold_review.md'):
        members.add(ROOT/name)
    members.update((cfar_path, Path(str(cfar_path)+'.sha256'), comparison_path, adc_log, software_log))
    members.update(ROOT.glob('logs/Z10*.*'))
    members.update(ROOT.glob('logs/T5*.*'))
    digests = {}
    archive.parent.mkdir(parents=True, exist_ok=True)
    result.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(members):
            if not path.is_file():
                continue
            name = path.relative_to(ROOT).as_posix()
            # Hash exactly the bytes written into the archive. A running
            # Vivado log can continue growing after this snapshot.
            raw = path.read_bytes()
            bundle.writestr(name, raw)
            digests[name] = sha(raw)
    data = dict(
        schema='z10-development-checkpoint-v1', status='PARTIAL',
        recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        scope='PC regression and candidate sources only; no board/deployment acceptance',
        clock_hz=100_000_000, sample_rate_hz=3_840_000,
        checks=dict(source_words=16384, source_mismatches=0, cfar_cases=18,
                    adc_words=args.adc_words, adc_reset_assertions=0, ps_tests=args.software_tests),
        pending=['Complete routed WNS >= +1ns and WHS >= 0ns, CDC/DRC/IO review',
                 'Board single tone, three tones, replay, zero sample drops and >=30fps'],
        archive=archive.relative_to(ROOT).as_posix(),
        archive_sha256=sha(archive.read_bytes()),
        archive_member_sha256=digests,
        note='Member hashes describe archived bytes; live logs may subsequently grow.')
    result.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for path in (result, archive):
        Path(str(path)+'.sha256').write_text(
            sha(path.read_bytes())+'  '+path.name+'\n', encoding='ascii')
    print('Z10_CHECKPOINT_RECORDED', result.relative_to(ROOT).as_posix(), 'PARTIAL')


if __name__ == '__main__':
    main()
