"""Verify local N2 evidence without rerunning implementation or touching hardware."""
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    provenance = {}

    def read(path):
        p = ROOT / path
        raw = p.read_bytes()
        provenance[path] = hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8-sig')

    for name in ('fft_round1', 'fft_sim_round3', 'stages_round2', 'regs_round1',
                 'front_round3', 'reduce_round1', 'front_synth_round2', 'package_round2'):
        assert read(f'logs/N2_{name}_exit.txt').strip() == '0', name
    checks = {}
    for stage, count in dict(fft=16384, power=8192, avg=8192, db=8192, display=2240).items():
        record = json.loads(read(f'sim/results/spec_front_{stage}_compare.json'))
        assert record['status'] == 'passed' and record['mode'] == 'exact'
        assert record['compared_words'] == count and record['mismatch_words'] == 0
        assert record['discarded_expected_words'] == record['discarded_actual_words'] == 0
        checks[stage] = record
    log = read('logs/N2_front_synth_round2.log')
    assert 'MODULE_SYNTHESIS_PASS spec_front' in log
    wns = float(re.search(r'MODULE_WNS spec_front ([\d.-]+)', log)[1])
    hold = float(re.search(r'MODULE_INTERNAL_HOLD spec_front ([\d.-]+)', log)[1])
    bram = int(re.search(r'FFTSHIFT_BLOCK_RAMS (\d+)', log)[1])
    assert wns >= 0 and hold >= 0 and bram == 4
    util = read('build/reports/modules/spec_front_util.rpt')
    resources = {}
    for label, key in [('Slice LUTs', 'lut'), ('Slice Registers', 'ff'),
                       ('Block RAM Tile', 'bram36_equivalent'), ('DSPs', 'dsp')]:
        resources[key] = float(re.search(r'\|\s*' + re.escape(label) + r'\s*\|\s*([\d.]+)', util)[1])
    read('build/reports/modules/spec_front_timing.rpt')
    read('build/reports/modules/spec_front_internal_hold.rpt')
    package_log = read('logs/N2_package_round2.log')
    assert 'Integrity check passed' in package_log and 'IP_PACKAGE_PASS spec_front' in package_log
    component = ET.fromstring(read('build/work/packaged_ip_round2/spec_front/component.xml'))
    ns = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    interfaces = component.findall('s:busInterfaces/s:busInterface', ns)
    names = {bus.findtext('s:name', namespaces=ns): bus for bus in interfaces}
    assert set(names) == {'aclk', 'aresetn', 's_axi', 's_axis', 'm_axis_pwr', 'm_axis_db'}
    params = {p.findtext('s:name', namespaces=ns): p.findtext('s:value', namespaces=ns)
              for p in names['aclk'].findall('s:parameters/s:parameter', ns)}
    assert params['FREQ_HZ'] == '150000000' and params['ASSOCIATED_RESET'] == 'aresetn'
    assert set(params['ASSOCIATED_BUSIF'].split(':')) == {'s_axi', 's_axis', 'm_axis_pwr', 'm_axis_db'}
    for directory, pattern in [('src/rtl/spectrum', '*.v'), ('src/rtl/common', '*.v'),
                               ('src/rtl/regs', 'spec_ctrl_regs.v'), ('data/reference/spectrum', '*.hex')]:
        for p in sorted((ROOT / directory).glob(pattern)):
            read(p.relative_to(ROOT).as_posix())
    result = dict(status='passed', date='2026-11-02', step='N2', frames=4, comparisons=checks,
                  frequency_mhz=150, setup_wns_ns=wns, internal_register_hold_ns=hold,
                  fftshift_bram36_count=bram, resources=resources, ip_integrity='passed',
                  scope='OOC core simulation, implementation and packaging; no board download',
                  limitation='OOC virtual-port hold is not board I/O closure; N4 must close full-system setup/hold and verify sustained throughput.',
                  provenance_sha256=provenance)
    (ROOT / 'sim/results/n2_acceptance.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('N2_ACCEPTANCE_PASS', resources, wns, hold)


if __name__ == '__main__':
    main()
