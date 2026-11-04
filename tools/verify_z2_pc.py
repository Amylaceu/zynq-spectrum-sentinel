"""Record Z2 software/RTL/packaging checks without claiming routed timing."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from x2_transport import ROOT, sha, write_evidence


def main():
    output = ROOT/'sim/results/z2_pc_r1.json'
    log = ROOT/'logs/Y2_z2_pc_regression_r1.log'
    archive_path = ROOT/'report/results/z2_pc_r1.zip'
    if any(p.exists() for p in (output, log, archive_path)):
        raise FileExistsError('Preserve Z2 attempt evidence')
    with log.open('x', encoding='utf-8') as stream:
        code = subprocess.call([sys.executable, '-m', 'pytest', 'src/ps/tests', 'tools/tests', '-q'],
                               stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
    logs = [log, ROOT/'sim/results/tb_lcd_render_scheduler_z2.log',
            ROOT/'logs/Y2_z2_package_r1_controller.log']
    for path, marker in ((logs[1], 'TB_RESULT: PASS Z2'),
                         (logs[2], 'IP_PACKAGE_PASS lcd8080_engine_z2')):
        if marker not in path.read_text(errors='replace'):
            raise ValueError('Missing PASS marker: '+str(path))
    sources = set((ROOT/'src/rtl/lcd_z2').glob('*.v'))
    sources.update(ROOT/name for name in (
        'src/ps/sentinel/lcd_z2.py', 'src/ps/sentinel/lcd_x5.py',
        'src/ps/sentinel/ui_events.py', 'src/ps/sentinel/v_z2.py',
        'src/ps/sentinel/app/monitor_z2.py', 'board/scripts/run_z2_monitor.py',
        'src/ps/tests/test_lcd_z2.py', 'sim/tb/tb_lcd_render_scheduler_z2.sv',
        'src/rtl/lcd/lcd_trace_pixel.v', 'src/rtl/lcd/lcd8080_region.v',
        'src/rtl/lcd/lcd_snapshot.v', 'src/rtl/lcd/lcd8080_bus.v',
        'src/rtl/spectrum/spec_display_reduce.v', 'src/rtl/common/lcd_init_rom.vh',
        'tools/test_z2_lcd.ps1', 'tools/package_z2_lcd.ps1',
        'build/scripts/package_z2_lcd.tcl', 'tools/verify_z2_pc.py',
        'report/figures/z2_ui_preview.png'))
    for p in sources:
        if p.suffix == '.py':
            ast.parse(p.read_text(encoding='utf-8'), feature_version=(3, 8))
    files = sorted(sources.union(logs))
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in manifest:
            archive.write(ROOT/name, name)
        archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2)+'\n')
    value = dict(status='PASS' if code == 0 else 'FAIL',
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='PC tests,8-color scroll simulation,IP packaging only; no routed timing/board acceptance',
                 pytest_exit_code=code, ui_version='0x4c430006', bank_used_bytes=64000,
                 bank_capacity_bytes=65536, banks=2,
                 source_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)},
                 log_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in logs},
                 archive=archive_path.relative_to(ROOT).as_posix(), archive_sha256=sha(archive_path))
    write_evidence(output, value)
    Path(str(archive_path)+'.sha256').write_text(sha(archive_path)+'  '+archive_path.name+'\n')
    print('Z2_PC_'+value['status'])
    raise SystemExit(code)


if __name__ == '__main__':
    main()
