"""Audit the X1 routed design and artifacts without touching the v1 bundle."""
import argparse
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from accept_sentinel_v1 import timing_summary, utilization, hwh_contract

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bus_skew_summary(text):
    """Fail closed when skew constraints are missing, violated or unparseable."""
    lines = re.findall(r'^\s*Slack\s*\([^\n]*$', text, re.MULTILINE)
    matches = [re.match(r'\s*Slack \((MET|VIOLATED)\)\s*:\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))ns\b', line)
               for line in lines]
    if not matches or any(match is None for match in matches):
        raise ValueError('Final bus skew coverage/constraints fail')
    values = [(match.group(1), float(match.group(2))) for match in matches]
    if any(status != 'MET' or value < 0 for status, value in values):
        raise ValueError('Final bus skew coverage/constraints fail')
    return {'reported_paths':len(values), 'minimum_slack_ns':min(value for _, value in values)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1,2,3), required=True)
    args = parser.parse_args()
    reports = ROOT/'build/reports/sentinel_v1b'
    bundle = ROOT/'board/overlay/sentinel_v1b'
    for directory in (reports,bundle):
        if (directory/'acceptance.json').exists():
            raise FileExistsError('Preserve accepted bundle')
    prepath = ROOT/('docs/x1_v1b_prebuild_r%d.json' % args.attempt)
    if sha(prepath) != Path(str(prepath)+'.sha256').read_text().split()[0]:
        raise ValueError('Prebuild manifest hash mismatch')
    pre = json.loads(prepath.read_text())
    for name, digest in pre['sources_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Prebuild input changed: '+name)
    timing = timing_summary((reports/'final_timing.rpt').read_text(encoding='utf-8',errors='replace'))
    resources = utilization((reports/'final_utilization.rpt').read_text(encoding='utf-8',errors='replace'))
    bus_skew = bus_skew_summary((reports/'final_bus_skew.rpt').read_text(encoding='utf-8',errors='replace'))
    manifest = {line.split()[1]:line.split()[0].lower() for line in
                (bundle/'sha256.txt').read_text(encoding='utf-8-sig').splitlines() if line.strip()}
    for suffix in ('bit','hwh','xsa'):
        path = bundle/('sentinel_v1b.'+suffix)
        if sha(path) != manifest.get(path.name):
            raise ValueError('Artifact digest mismatch: '+path.name)
    hwh = bundle/'sentinel_v1b.hwh'
    addresses = hwh_contract(hwh)
    module = ET.parse(hwh).getroot().find(".//MODULE[@INSTANCE='cfar_core_0']")
    if module is None or module.get('MODTYPE') != 'cfar_core_x1':
        raise ValueError('v1b must contain the X1 CFAR implementation')
    result = {
        'status':'PASS', 'recorded_at_pc':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope':'PC implementation acceptance only; no X1 RF metrics or visual acceptance',
        'cfar_version':0x43460002, 'final_timing':timing, 'resources':resources,
        'bus_skew':bus_skew,
        'addresses':addresses, 'artifacts_sha256':manifest,
        'prebuild_manifest_sha256':sha(prepath),
        'report_sha256':{p.name:sha(p) for p in reports.glob('final_*.rpt')},
        'cdc_review':'Inherited ADI warnings retained in final_cdc.rpt; no blanket risk waiver',
        'timing_source':'Fresh open_run impl_1 after post-route ADI timing fix',
        'standalone_cluster_r1_hold_result':'FAIL retained; routed full-system report assessed separately',
    }
    raw = (json.dumps(result,indent=2)+chr(10)).encode()
    for directory in (reports,bundle):
        path = directory/'acceptance.json'
        path.write_bytes(raw)
        Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+chr(10),encoding='ascii')
    print('SENTINEL_V1B_IMPLEMENTATION_ACCEPTANCE_PASS')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
