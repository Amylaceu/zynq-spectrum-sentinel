"""Capture immutable inputs BEFORE a v2 run; a manifest is not acceptance."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    'src/hw/sentinel_v2_100m', 'src/rtl',
    'build/work/v2_clock_packaged_ip', 'build/work/v2_cfar_packaged_ip',
    'build/work/x5_packaged_ip', 'build/work/x5_cfar_packaged_ip',
    'build/work/packaged_ip_round2', 'build/work/n3_packaged_ip_round2',
    'build/work/n4_packaged_ip_round2',
    'build/work/adi_hdl/library', 'build/work/adi_hdl/projects/scripts',
)
FILES = (
    'tools/build_sentinel_v2.ps1', 'tools/freeze_v2_inputs.py',
    'build/scripts/run_sentinel_v2.tcl', 'build/scripts/resume_sentinel_v2.tcl',
    'build/scripts/post_route_v2.tcl',
    'build/scripts/z10_impl_policy.tcl',
    'build/work/x5_fft/x5_fft.srcs/sources_1/ip/pfb_fft16/pfb_fft16.xci',
)
SUFFIXES = {'.v', '.sv', '.vhd', '.hex', '.mem', '.xci', '.xdc', '.tcl', '.xml'}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--power-optimization', choices=('On', 'Off'), default='On')
    args = parser.parse_args()
    if re.fullmatch(r'[A-Za-z0-9_]+', args.tag) is None:
        parser.error('Invalid tag')
    path = ROOT/'build/reports/sentinel_v2_100m'/('inputs_'+args.tag+'.json')
    sidecar = path.with_name(path.name+'.sha256')
    if args.verify:
        if sha(path) != sidecar.read_text().split()[0]:
            raise ValueError('Input manifest digest mismatch')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['status'] != 'INPUTS_FROZEN_NOT_ACCEPTED' or data['tag'] != args.tag:
            raise ValueError('Wrong input manifest')
        if data.get('implementation_options', {}).get('power_optimization', args.power_optimization) != args.power_optimization:
            raise ValueError('Power optimization option changed')
        for name, digest in data['build_input_sha256'].items():
            if sha(ROOT/name) != digest:
                raise ValueError('Build input changed: '+name)
        print('Z10_BUILD_INPUTS_VERIFIED')
        return
    if path.exists() or sidecar.exists():
        raise FileExistsError('Preserve prior input manifest')
    inputs = {ROOT/name for name in FILES}
    for name in DIRECTORIES:
        directory = ROOT/name
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        inputs.update(p for p in directory.rglob('*') if p.is_file()
                      and p.suffix.lower() in SUFFIXES)
    data = dict(status='INPUTS_FROZEN_NOT_ACCEPTED', tag=args.tag,
                implementation_options={'power_optimization': args.power_optimization},
                recorded_utc=datetime.now(timezone.utc).isoformat(),
                scope='Conservative source superset before build; not implementation or board acceptance',
                build_input_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(inputs)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2)+'\n').encode('utf-8'))
    sidecar.write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print('Z10_BUILD_INPUTS_FROZEN count='+str(len(inputs)))


if __name__ == '__main__':
    main()
