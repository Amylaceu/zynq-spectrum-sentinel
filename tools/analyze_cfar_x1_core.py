"""Verify all integrated X1 outputs independently of testbench PASS messages."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(path):
    return [int(x, 16) for x in path.read_text(encoding='ascii').split()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = p.parse_args()
    tag = 'r%d' % args.attempt
    vectors = ROOT/'data/reference/cfar'/('x1_core_'+tag)
    manifest_path = vectors/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest_path.with_name('manifest.json.sha256').read_text().split()[0] != sha(manifest_path):
        raise ValueError('Bad manifest hash')
    for name, value in manifest['sha256'].items():
        if Path(name).name != name or sha(vectors/name) != value:
            raise ValueError('Bad vector hash: '+name)
    comparisons = {}
    for name in ('threshold', 'hit', 'db', 'occupancy', 'targets', 'stats'):
        expected = vectors/(('targets_words' if name == 'targets' else name)+'.hex')
        actual = ROOT/'logs'/('X1_core_'+name+'_'+tag+'.hex')
        a, b = words(expected), words(actual)
        if a != b:
            raise ValueError('Output differs in count/value/order: '+name)
        comparisons[name] = {'words':len(a), 'mismatches':0, 'actual_sha256':sha(actual), 'expected_sha256':sha(expected)}
    log = ROOT/'logs'/('X1_core_xsim_'+tag+'.log')
    text = log.read_text(encoding='utf-8-sig')
    case_ids = [int(x) for x in re.findall(r'^X1_CORE_CASE_PASS (\d+) ', text, re.M)]
    if case_ids != list(range(len(manifest['cases']))) or 'TB_RESULT: PASS X1_CORE 18 cases' not in text:
        raise ValueError('Incomplete testbench case completion')
    sources = ['src/rtl/cfar_x1/cfar_core_x1.v','src/rtl/cfar_x1/cfar_x1_regs.v',
        'src/rtl/cfar_x1/cfar_cluster_x1.v','src/rtl/cfar_x1/cfar_detect_x1.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/common/axis_broadcast2.v','sim/tb/tb_cfar_core_x1.sv',
        'sim/golden/cfar_x1.py','sim/golden/cfar.py','tools/export_cfar_x1_core_vectors.py']
    if 'X1_ADD_SUB40_PASS 10096' not in text:
        raise ValueError('Missing carry-save arithmetic boundary/random checks')
    result = {'status':'PASS','recorded_at_pc':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope':'Integrated X1 CFAR simulation only; no full-system timing or hardware/RF acceptance',
        'cases':len(case_ids),'input_bins':2048*len(case_ids),'comparisons':comparisons,
        'carry_save_arithmetic_checks':10096,
        'log_sha256':sha(log),'manifest_sha256':sha(manifest_path),
        'source_sha256':{name:sha(ROOT/name) for name in sources},
        'extra_checks':['AXI AW/W independent arrivals, WSTRB, stable stalled responses',
            'Invalid mask count/order/range and width refuse new input',
            'Mask/DC/gap/width changes during input apply only to next frame',
            'IRQ publication exposes matching sequence/counts/alarm/status/list',
            'Threshold/hit/target AXIS backpressure stability',
            'Occupancy accumulation and explicit clear',
            'Framing error visible live and in snapshot, reset clears metadata'],
        'hardware_accessed':False}
    path = ROOT/'sim/results'/('x1_core_'+tag+'_acceptance.json')
    if path.exists() or path.with_name(path.name+'.sha256').exists():
        raise FileExistsError('Preserve previous acceptance')
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    path.with_name(path.name+'.sha256').write_text(sha(path)+'  '+path.name+'\n',encoding='ascii')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
