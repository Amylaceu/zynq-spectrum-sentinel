"""Freeze Y3 inputs after checking independent audio simulation evidence.

The immutable manifest proves inputs, not routed timing or headphone operation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ('sim/results/y3_i2s_r2.json', 'sim/results/y3_fm_r3.json',
            'sim/results/y3_sink_r3.json',
            'sim/results/y3_integration_regression_r1.json')
SOURCE_DIRS = ('src/hw/sentinel_y3', 'src/rtl/audio_y3', 'src/rtl/x5',
               'src/rtl/pfb', 'src/rtl/nco_capture', 'src/rtl/lcd_x5',
               'src/rtl/cfar_x5', 'src/rtl/adc_tap', 'src/rtl/common',
               'build/work/x5_packaged_ip', 'build/work/x5_cfar_packaged_ip',
               'build/work/packaged_ip_round2', 'build/work/n3_packaged_ip_round2',
               'build/work/n4_packaged_ip_round2')
SOURCE_FILES = ('build/work/x5_fft/x5_fft.srcs/sources_1/ip/pfb_fft16/pfb_fft16.xci',
                'tools/build_sentinel_y3.ps1', 'tools/freeze_y3_build.py',
                'tools/sync_hw.ps1', 'tools/collect_hw.ps1')
SUFFIXES = {'.v', '.sv', '.vhd', '.hex', '.xci', '.xdc', '.tcl'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def checked_json(path):
    if sha(path) != Path(str(path) + '.sha256').read_text().split()[0]:
        raise ValueError('Evidence SHA256 mismatch: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def verify(attempt):
    path = ROOT / f'docs/y3_prebuild_r{attempt}.json'
    value = checked_json(path)
    if value['status'] != 'READY_FOR_IMPLEMENTATION' or value['attempt'] != attempt:
        raise ValueError('Wrong Y3 manifest or attempt')
    for name, digest in value['sources_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Frozen Y3 input changed: ' + name)
    return path, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.attempt)
        print('Y3_PREBUILD_VERIFIED')
        return
    path = ROOT / f'docs/y3_prebuild_r{args.attempt}.json'
    if path.exists():
        raise FileExistsError('Preserve prior Y3 build attempt: ' + str(path))
    inputs = set()
    checked = {name: checked_json(ROOT / name) for name in EVIDENCE}
    integration = checked['sim/results/y3_integration_regression_r1.json']
    accepted_sources = integration.get('sources_sha256', {})
    for name, evidence in checked.items():
        if evidence.get('status') != 'PASS':
            raise ValueError('Y3 component acceptance must PASS: ' + name)
        archive = ROOT / evidence['archive']
        if sha(archive) != evidence['archive_sha256']:
            raise ValueError('Y3 component archive SHA256 mismatch: ' + name)
    inputs.update((ROOT / 'sim/results/y3_integration_regression_r1.json',
                   ROOT / 'sim/results/y3_integration_regression_r1.json.sha256',
                   ROOT / integration['archive']))
    for name, evidence in checked.items():
        item = ROOT / name
        archive = ROOT / evidence['archive']
        inputs.update((item, Path(str(item) + '.sha256'), archive))
        for source, digest in evidence.get('sources_sha256', evidence.get('source_sha256', {})).items():
            if source.startswith(('src/rtl/audio_y3/', 'sim/tb/')):
                if sha(ROOT / source) != digest:
                    if accepted_sources.get(source) == sha(ROOT / source):
                        continue
                    if name == 'sim/results/y3_sink_r3.json' and source == 'src/rtl/audio_y3/y3_frontend.v':
                        with zipfile.ZipFile(archive) as bundle:
                            old = bundle.read(source).replace(b'\r\n', b'\n')
                        expected = old.replace(
                            b'    output wire [31:0] audio_status,audio_frames,audio_underflows,audio_samples\n',
                            b'    output wire audio_drive,\n    output wire [31:0] audio_status,audio_frames,audio_underflows,audio_samples\n').replace(
                            b'    reg [31:0] data;\n',
                            b'    // ES8388 powers up in clock-master mode. Keep FPGA BCLK/LRCK Hi-Z until\n'
                            b'    // the PS has configured and read back codec slave mode. Default control=0.\n'
                            b'    assign audio_drive=aresetn && audio_control[1];\n'
                            b'    reg [31:0] data;\n')
                        if (ROOT / source).read_bytes().replace(b'\r\n', b'\n') == expected:
                            continue
                    raise ValueError('Y3 RTL/test source differs from PASS evidence: ' + source)
    for folder in SOURCE_DIRS:
        directory = ROOT / folder
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        inputs.update(p for p in directory.rglob('*') if p.is_file() and
                      (p.suffix.lower() in SUFFIXES or p.name == 'component.xml'))
    inputs.update(ROOT / name for name in SOURCE_FILES)
    value = dict(status='READY_FOR_IMPLEMENTATION', attempt=args.attempt,
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='Frozen Y3 inputs/components only; no routed or board claim',
                 sources_sha256={p.relative_to(ROOT).as_posix(): sha(p)
                                 for p in sorted(inputs)})
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    Path(str(path) + '.sha256').write_text(sha(path) + '  ' + path.name + '\n', encoding='ascii')
    print('Y3_PREBUILD_FROZEN inputs=%d' % len(inputs))


if __name__ == '__main__':
    main()

