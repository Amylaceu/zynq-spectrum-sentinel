"""Run PC regression and board-Python syntax gates, preserving hashed evidence."""
import ast
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--validation-attempt', type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    suffix = '' if args.attempt == 1 else '_r%d' % args.attempt
    path = ROOT/('sim/results/x5_integration_acceptance'+suffix+'.json')
    if path.exists():
        raise FileExistsError('Preserve previous evidence')
    tests = ROOT/('logs/X5_ps_regression'+suffix+'.log')
    validation_log = 'logs/X5_v1d_validate_r%d_console.log' % args.validation_attempt
    with tests.open('w', encoding='utf-8') as stream:
        code = subprocess.call([sys.executable, '-m', 'pytest', 'src/ps/tests', 'tools/tests', '-q'],
                               cwd=str(ROOT), stdout=stream, stderr=subprocess.STDOUT)
    sources = set((ROOT/'src/ps/sentinel').rglob('*.py'))
    for source in sources:
        ast.parse(source.read_text(encoding='utf-8-sig'), filename=str(source), feature_version=(3, 8))
    for relative, marker in (
            (validation_log, 'SENTINEL_BD_VALIDATION_PASS'),
            ('logs/X5_lcd_package_r2_console.log', 'IP_PACKAGE_PASS lcd8080_engine_x5'),
            ('sim/results/tb_lcd_render_scheduler_x5.log', 'TB_RESULT: PASS'),
            ('sim/results/tb_x5_fork.log', 'TB_RESULT: PASS')):
        source = ROOT/relative
        if marker not in source.read_text(errors='replace'):
            raise ValueError('Missing success marker '+relative)
    for folder in ('src/rtl/x5', 'src/rtl/lcd_x5', 'src/hw/sentinel_v1d', 'src/rtl/cfar_x5'):
        sources.update(p for p in (ROOT/folder).rglob('*') if p.is_file())
    sources.update(ROOT/p for p in (
        'sim/tb/tb_lcd_render_scheduler_x5.sv', 'sim/tb/tb_x5_fork.sv',
        'src/ps/tests/test_x5.py', 'tools/verify_x5_pc.py',
        'build/scripts/package_x5_lcd.tcl', 'tools/package_x5_lcd.ps1',
        'tools/test_x5_fork.ps1', 'tools/test_x5_lcd.ps1',
        'src/rtl/lcd/lcd_trace_pixel.v', 'src/rtl/lcd/lcd8080_region.v'))
    logs = [tests]+[ROOT/p for p in (
        validation_log, 'logs/X5_lcd_package_r2_console.log',
        'sim/results/tb_lcd_render_scheduler_x5.log', 'sim/results/tb_x5_fork.log')]
    value = dict(status='PASS' if code == 0 else 'FAIL',
                 scope='PC regression, Python3.8 syntax, lossless fork, LCD simulation and BD; no RF claim',
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 pytest_exit_code=code, python38_ast_files=len(list((ROOT/'src/ps/sentinel').rglob('*.py'))),
                 source_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)},
                 log_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in logs})
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print('X5_PC_'+value['status'])
    if code:
        raise SystemExit(code)


if __name__ == '__main__':
    main()
