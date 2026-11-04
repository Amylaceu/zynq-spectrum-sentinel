"""Accept final (post-ADI timing fix) implementation and matched v1 artifacts."""
import argparse,hashlib,json,math,re,xml.etree.ElementTree as E
from pathlib import Path

BASES={'src_mux_0':0x43c00000,'spec_front_0':0x43c10000,'cfar_core_0':0x43c20000,
'lcd_engine':0x43c60000,'perf_mon_0':0x43c70000,'axi_lcd_ui':0x42000000,
'axi_power_capture':0x42010000,'axi_capture_ctrl':0x41220000,'axi_dma_replay':0x40400000,
'axi_sentinel_intc':0x41800000,'axi_ad9361':0x79020000,'axi_ad9361_adc_dma':0x7c400000,'axi_ad9361_dac_dma':0x7c420000}

def timing_summary(text):
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if 'WNS(ns)' in line and 'WHS(ns)' in line:
            fields=lines[i+2].split()
            if len(fields)!=12:raise ValueError('Malformed final timing summary')
            values=[float(v) for v in fields]
            if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite timing')
            out={'WNS_ns':values[0],'TNS_ns':values[1],'setup_failing_endpoints':int(values[2]),
                'WHS_ns':values[4],'THS_ns':values[5],'hold_failing_endpoints':int(values[6]),
                'WPWS_ns':values[8],'pulse_failing_endpoints':int(values[10])}
            if min(values[0],values[4],values[8])<0 or any(values[j]!=0 for j in (2,6,10)):
                raise ValueError('Final routed timing fails: '+str(out))
            if min(values[3],values[7])<=0:raise ValueError('No constrained endpoints')
            for kind in ('no_clock','unconstrained_internal_endpoints'):
                match=re.search(r'checking '+kind+r' \((\d+)\)',text)
                if not match or int(match[1]):raise ValueError('Timing coverage missing: '+kind)
            return out
    raise ValueError('Missing final timing summary')

def utilization(text):
    def value(name):
        m=re.search(r'\|\s*'+re.escape(name)+r'\s*\|\s*([0-9.]+)',text)
        if not m:raise ValueError('Missing utilization '+name)
        return float(m[1])
    out={name:value(name) for name in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs')}
    if out['Slice LUTs']>39900 or out['Block RAM Tile']>110:raise ValueError('N4 resource limits exceeded: '+str(out))
    return out

def hwh_contract(path):
    root=E.parse(path).getroot();sys=root.find('SYSTEMINFO')
    if sys is None or (sys.get('DEVICE'),sys.get('PACKAGE'),sys.get('SPEEDGRADE'))!=('7z020','clg484','-2'):
        raise ValueError('Wrong device')
    ps=root.find(".//MODULE[@INSTANCE='sys_ps7']")
    actual={e.get('INSTANCE'):(int(e.get('BASEVALUE'),0),int(e.get('HIGHVALUE'),0)) for e in ps.findall('./MEMORYMAP/MEMRANGE')}
    for name,base in BASES.items():
        if name not in actual or actual[name][0]!=base:raise ValueError('Wrong/missing address '+name)
    for name,size in [('axi_lcd_ui',32768),('axi_power_capture',8192),('cfar_core_0',16384)]:
        if actual[name][1]-actual[name][0]+1!=size:raise ValueError('Wrong window size '+name)
    clock=root.find(".//MODULE[@INSTANCE='dsp_clock']")
    params={e.get('NAME'):e.get('VALUE') for e in clock.findall('./PARAMETERS/PARAMETER')}
    if float(params['C_CLKOUT0_ACTUAL_FREQ'])!=150 or float(params['C_PRIM_IN_FREQ'])!=50:raise ValueError('Wrong DSP clock')
    return {name:hex(value[0]) for name,value in actual.items()}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path('.'));a=p.parse_args();root=a.repo.resolve()
    reports=root/'build/reports/sentinel_v1';bundle=root/'board/overlay/sentinel_v1'
    timing=timing_summary((reports/'final_timing.rpt').read_text(encoding='utf-8',errors='replace'))
    resources=utilization((reports/'final_utilization.rpt').read_text(encoding='utf-8',errors='replace'))
    expected={line.split()[1]:line.split()[0].lower() for line in (bundle/'sha256.txt').read_text(encoding='utf-8-sig').splitlines() if line.strip()}
    for ext in ('bit','hwh','xsa'):
        file=bundle/('sentinel_v1.'+ext)
        if not file.is_file() or expected.get(file.name)!=sha(file):raise ValueError('Artifact hash mismatch '+file.name)
    addresses=hwh_contract(bundle/'sentinel_v1.hwh')
    pre=json.loads((root/'sim/results/n4_integration_prebuild.json').read_text(encoding='utf-8'))
    expected_sources=pre['overlay_sources_sha256'].copy()
    timing_patch=pre.get('timing_patch_after_prebuild')
    if timing_patch:
        expected_sources['system_project.tcl']=timing_patch['system_project_tcl_sha256']
        expected_sources['adc_tap_cdc.xdc']=timing_patch['adc_tap_cdc_xdc_sha256']
    for name,digest in expected_sources.items():
        if sha(root/'src/hw/sentinel_v1'/name)!=digest:raise ValueError('Overlay changed after prebuild validation: '+name)
    r={'status':'PASS','scope':'Computer implementation/artifact acceptance only; board and visual gates still pending',
       'final_timing':timing,'resources':resources,'addresses':addresses,'artifacts_sha256':expected,
       'timing_source':'final_timing.rpt (fresh open_run after post-route ADI timing fix); pre-fix routed/placed reports are not used',
       'timing_report_sha256':sha(reports/'final_timing.rpt')}
    (reports/'acceptance.json').write_bytes((json.dumps(r,indent=2)+'\n').encode())
    summary='# sentinel_v1 computer implementation acceptance\n\nFinal timing: '+str(timing)+'\n\nResources: '+str(resources)+'\n\nBoard tests, LCD timing-phase visual checks, measured15fps and N5 remain pending. RF/TX was not exercised by this acceptance.\n'
    (reports/'SUMMARY.md').write_bytes(summary.encode());print('SENTINEL_V1_IMPLEMENTATION_ACCEPTANCE_PASS');print(json.dumps(r))

if __name__=='__main__':main()
