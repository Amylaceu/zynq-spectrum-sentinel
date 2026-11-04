"""Validate N3 evidence, including exact complete outputs and implemented resources."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--synth-round',type=int,required=True)
    p.add_argument('--package-round',type=int,required=True)
    p.add_argument('--occupancy-round',type=int,required=True)
    args=p.parse_args()
    hashes={}
    def read(name):
        raw=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8-sig')
    for name in ('sim_round3_final',f'synth_round{args.synth_round}',f'package_round{args.package_round}',
                 f'occupancy_round{args.occupancy_round}'):
        assert read(f'logs/N3_{name}_exit.txt').strip()=='0',name
    manifest=json.loads(read('data/reference/cfar/n3/manifest.json'))
    assert len(manifest['cases'])==13
    for name,digest in manifest['sha256'].items():
        read('data/reference/cfar/n3/'+name)
        assert hashes['data/reference/cfar/n3/'+name]==digest
    checks={}
    for name in ('threshold','hit','db','occupancy','targets'):
        result=json.loads(read(f'sim/results/cfar_{name}_compare.json'))
        assert result['status']=='passed' and result['mode']=='exact'
        assert result['compared_words']==(1664 if name=='targets' else 26624)
        assert result['mismatch_words']==result['discarded_expected_words']==result['discarded_actual_words']==0
        checks[name]=result
    synthesis=read(f'logs/N3_synth_round{args.synth_round}.log')
    assert 'MODULE_SYNTHESIS_PASS cfar_core' in synthesis
    wns=float(re.search(r'MODULE_WNS cfar_core ([\d.-]+)',synthesis)[1])
    hold=float(re.search(r'MODULE_INTERNAL_HOLD cfar_core ([\d.-]+)',synthesis)[1])
    assert wns>=0 and hold>=0
    occ_bram=int(re.search(r'CFAR_OCCUPANCY_BRAMS (\d+)',synthesis)[1])
    assert occ_bram>=2
    util=read('build/reports/modules/cfar_core_util.rpt')
    resources={}
    for label,key in [('Slice LUTs','lut'),('Slice Registers','ff'),('Block RAM Tile','bram36_equivalent'),('DSPs','dsp')]:
        resources[key]=float(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*([\d.]+)',util)[1])
    read('build/reports/modules/cfar_core_timing.rpt');read('build/reports/modules/cfar_core_internal_hold.rpt')
    assert '4 passed' in read('logs/N3_driver_tests.log')
    assert 'Integrity check passed' in read(f'logs/N3_package_round{args.package_round}.log')
    component=ET.fromstring(read(f'build/work/n3_packaged_ip_round{args.package_round}/cfar_core/component.xml'))
    ns={'s':'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    interfaces={b.findtext('s:name',namespaces=ns):b for b in component.findall('s:busInterfaces/s:busInterface',ns)}
    expected={'s_axis_pwr','m_axis_thr','m_axis_hit','m_axis_tgt','s_axi','aclk','aresetn'}
    assert set(interfaces)==expected,set(interfaces)
    params={v.findtext('s:name',namespaces=ns):v.findtext('s:value',namespaces=ns)
            for v in interfaces['aclk'].findall('s:parameters/s:parameter',ns)}
    assert params['FREQ_HZ']=='150000000' and params['ASSOCIATED_RESET']=='aresetn'
    assert set(params['ASSOCIATED_BUSIF'].split(':'))==expected-{'aclk','aresetn'}
    for path in sorted((ROOT/'src/rtl/cfar').glob('*.v')):
        read(path.relative_to(ROOT).as_posix())
    for name in ('src/rtl/common/axis_broadcast2.v','src/rtl/regs/cfar_ctrl_regs.v','src/regs/cfar_ctrl.yaml','sim/tb/tb_cfar_core.sv','sim/tb/tb_cfar_occupancy.sv'):
        read(name)
    result=dict(status='passed',step='N3',date='2026-11-02',cases=manifest['cases'],comparisons=checks,
                frequency_mhz=150,setup_wns_ns=wns,internal_register_hold_ns=hold,resources=resources,
                occupancy_bram_primitives=occ_bram,ip_integrity='passed',python_driver_tests=4,
                scope='OOC core: bit-exact simulation, AXI/list/occupancy tests, 150MHz implementation; no board download',
                limitations=['Single wrap numeric policy; boundary test groups cover interior and both edge targets.',
                             'Framed capture/process architecture; one bin per enabled processing clock, not overlapping capture.',
                             'OOC virtual I/O hold is not full-system hold closure; integrate and measure in N4.'],
                provenance_sha256=hashes)
    (ROOT/'sim/results/n3_acceptance.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print('N3_ACCEPTANCE_PASS',wns,hold,resources)


if __name__=='__main__':main()
