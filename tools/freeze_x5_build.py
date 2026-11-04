"""Freeze X5 source/IP/ROM inputs only after matching simulation evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path):
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Evidence digest mismatch '+str(path))
    return json.loads(path.read_text())


def verify(attempt):
    path = ROOT/('docs/x5_v1d_prebuild_r%d.json' % attempt)
    value = verified(path)
    for name, digest in value['sources_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Frozen input changed '+name)
    return path, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.attempt)
        print('X5_PREBUILD_VERIFIED')
        return
    path = ROOT/('docs/x5_v1d_prebuild_r%d.json' % args.attempt)
    if path.exists():
        raise FileExistsError(path)
    inputs = set()
    integration = 'sim/results/x5_integration_acceptance%s.json' % (
        '' if args.attempt == 1 else '_r%d' % args.attempt)
    evidence_names = ['sim/results/x5_core_acceptance.json', integration]
    if args.attempt >= 2:
        evidence_names.append('sim/results/x5_cfar_r%d.json' % args.attempt)
    for name in evidence_names:
        evidence = verified(ROOT/name)
        if evidence['status'] != 'PASS':
            raise ValueError('Simulation evidence must pass '+name)
        inputs.add(ROOT/name)
        for field in ('source_sha256', 'log_sha256'):
            for source, digest in evidence[field].items():
                if sha(ROOT/source) != digest:
                    raise ValueError('Simulation source/log changed '+source)
                inputs.add(ROOT/source)
    for folder in ('src/hw/sentinel_v1d', 'src/rtl/x5', 'src/rtl/pfb',
                   'src/rtl/nco_capture', 'src/rtl/lcd_x5', 'src/rtl/cfar_x5', 'src/constraints',
                   'build/work/x5_packaged_ip', 'build/work/x5_cfar_packaged_ip',
                   'build/work/packaged_ip_round2', 'build/work/n3_packaged_ip_round2',
                   'build/work/n4_packaged_ip_round2'):
        directory = ROOT/folder
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        inputs.update(p for p in directory.rglob('*') if p.is_file() and
                      (p.suffix.lower() in ('.v', '.sv', '.vhd', '.hex', '.xci', '.xdc', '.tcl')
                       or p.name == 'component.xml'))
    inputs.update(ROOT/name for name in (
        'tools/build_sentinel_v1d.ps1', 'tools/freeze_x5_build.py',
        'tools/accept_sentinel_v1d.py', 'tools/audit_sentinel_v1d.ps1',
        'tools/sync_hw.ps1', 'tools/collect_hw.ps1',
        'build/scripts/audit_sentinel_v1d.tcl', 'build/scripts/package_x5_lcd.tcl',
        'build/scripts/package_cfar_x5.tcl', 'tools/package_cfar_x5.ps1',
        'src/rtl/adc_tap/adc_tap.v', 'src/rtl/common/sentinel_capture.v',
        'src/rtl/common/sentinel_events.v',
        'build/work/x5_fft/x5_fft.srcs/sources_1/ip/pfb_fft16/pfb_fft16.xci'))
    value = dict(status='READY_FOR_IMPLEMENTATION', attempt=args.attempt,
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='Frozen inputs only; does not establish routed timing or board acceptance',
                 sources_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(inputs)})
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print('X5_PREBUILD_FROZEN inputs=%d' % len(inputs))


if __name__ == '__main__':
    main()
