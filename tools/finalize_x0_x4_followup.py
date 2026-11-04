"""Independently verify the native CPU and registered-mask experiments."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from x2_transport import ROOT,sha,verified,write_evidence

def utilization_resources(report):
    """Read exact resource rows; ignore report headings and blank lines."""
    resources = {}
    for label in ('Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'):
        matches = []
        for line in report.splitlines():
            cells = line.split('|')
            if len(cells) >= 4 and cells[1].strip() == label:
                matches.append(float(cells[2].strip()))
        # Vivado repeats registers in both logic and distribution sections.
        # Repeated rows must agree; a missing or conflicting count is an error.
        if not matches or len(set(matches)) != 1:
            raise ValueError('Missing or inconsistent utilization rows for '+label)
        resources[label] = matches[0]
    return resources

def main():
    out=ROOT/'board/measurements/x0_x4_followup_r1.json'
    archive=ROOT/'report/results/x0_x4_followup_r1.zip'
    if out.exists() or archive.exists():raise FileExistsError('Preserve prior evidence')
    native=verified(ROOT/'board/measurements/x4_native_board_r1.json')
    builder=verified(ROOT/'board/measurements/x4_native_buildcheck_r1.json')
    mask=verified(ROOT/'sim/results/x2_maskpipe_r2.json')
    cfg=verified(ROOT/'sim/results/x2_cfgpipe_r3.json')
    for record in (native,builder,mask,cfg):
        for name,digest in record['source_sha256'].items():
            assert sha(ROOT/name)==digest,name
    assert native['difference']['all_exact'] and native['kernel_max_error']==0
    assert native['library_sha256']==builder['library_sha256']
    assert native['boot_id']==builder['boot_id']
    rows=native['rows']; validation=native['validation']
    assert len(rows)==300 and len(validation)==260
    assert len(set(row['sample_id'] for row in validation))==260
    assert set(row['snr_db'] for row in validation)==set(range(-4,21,2))
    assert all(row['predicted']==row['native_predicted'] for row in validation)
    ids={row['sample_id'] for row in rows}
    expected={(repeat,sample,engine) for repeat in range(3) for sample in ids for engine in native['timing']}
    assert len(ids)==50 and {(x['repeat'],x['sample_id'],x['engine']) for x in rows}==expected
    for repeat in range(3):
        for sample in ids:
            pair=[x for x in rows if x['repeat']==repeat and x['sample_id']==sample]
            assert len({(x['predicted'],x['label']) for x in pair})==1
    for engine,stats in native['timing'].items():
        a=np.array([row['elapsed_ms'] for row in rows if row['engine']==engine])
        assert len(a)==150 and np.all(np.isfinite(a)) and np.all(a>0)
        for key,value in [('median_ms',np.median(a)),('p95_ms',np.percentile(a,95)),('max_ms',a.max())]:
            np.testing.assert_allclose(value,stats[key],rtol=0,atol=1e-9)
        assert int(np.sum(a>100))==stats['over_100ms']
    timing_log=ROOT/'logs/X2_maskpipe_timing_r2.log'
    text=timing_log.read_text(errors='replace')
    assert (ROOT/'logs/X2_maskpipe_timing_r2_exit.txt').read_text(encoding='utf-8-sig').strip()=='0'
    assert 'X2_MASKPIPE_AUDIT_COMPLETE' in text
    reports=ROOT/'build/reports/x2_maskpipe_r2'
    timing={}
    for top in ('cfar_reference_regwrap','cfar_maskpipe_regwrap'):
        line=next(line for line in text.splitlines() if line.startswith('X2_MASKPIPE_RESULT '+top+' '))
        fields=dict(item.split('=') for item in line.split()[2:])
        wns,whs=float(fields['REG_WNS']),float(fields['REG_WHS'])
        setup=(reports/(top+'_reg_setup.rpt')).read_text()
        hold=(reports/(top+'_reg_hold.rpt')).read_text()
        def slack(report):
            line=next(line for line in report.splitlines() if line.startswith('Slack ('))
            return float(line.split(':',1)[1].strip().split('ns',1)[0])
        assert slack(setup)==wns and slack(hold)==whs
        util=(reports/(top+'_utilization.rpt')).read_text()
        resources=utilization_resources(util)
        timing[top]=dict(reg_wns_ns=wns,reg_whs_ns=whs,resources=resources,
                         register_timing_met=wns>=0 and whs>=0,period_ns=6.667)
    cfg_text=(ROOT/'logs/X2_maskpipe_timing_r3.log').read_text(errors='replace')
    assert (ROOT/'logs/X2_maskpipe_timing_r3_exit.txt').read_text(encoding='utf-8-sig').strip()=='0'
    assert 'X2_MASKPIPE_AUDIT_COMPLETE' in cfg_text
    cfg_top='cfar_cfgpipe_regwrap'
    cfg_line=next(line for line in cfg_text.splitlines() if line.startswith('X2_MASKPIPE_RESULT '+cfg_top+' '))
    fields=dict(item.split('=') for item in cfg_line.split()[2:])
    cfg_wns,cfg_whs=float(fields['REG_WNS']),float(fields['REG_WHS'])
    cfg_reports=ROOT/'build/reports/x2_maskpipe_r3'
    setup=(cfg_reports/(cfg_top+'_reg_setup.rpt')).read_text()
    hold=(cfg_reports/(cfg_top+'_reg_hold.rpt')).read_text()
    def slack(report):
        line=next(line for line in report.splitlines() if line.startswith('Slack ('))
        return float(line.split(':',1)[1].strip().split('ns',1)[0])
    assert slack(setup)==cfg_wns and slack(hold)==cfg_whs
    util=(cfg_reports/(cfg_top+'_utilization.rpt')).read_text()
    resources=utilization_resources(util)
    timing[cfg_top]=dict(reg_wns_ns=cfg_wns,reg_whs_ns=cfg_whs,resources=resources,
                         register_timing_met=cfg_wns>=0 and cfg_whs>=0,period_ns=6.667)
    chain_log=ROOT/'sim/results/tb_sentinel_maskpipe_x2.log'
    chain_text=chain_log.read_text()
    assert (ROOT/'logs/X2_maskpipe_chain_r1_exit.txt').read_text(encoding='utf-8-sig').strip()=='0'
    assert 'TB_RESULT: PASS ADC async FIFO' in chain_text
    chain_line=next(line for line in chain_text.splitlines() if line.startswith('X2_CHAIN '))
    chain={k:int(v) for k,v in (part.split('=') for part in chain_line.split()[1:])}
    assert chain['sample_rate']==30720000 and chain['sample_drop']==0
    assert chain['adc_inputs']==chain['power_words']==131072
    assert chain['frames_in']==64 and chain['frames_out']+chain['frame_drop']==64
    test_log=ROOT/'logs/X0_X4_native_full_tests_r1.log'
    assert '280 passed' in test_log.read_text()
    sources=set(native['source_sha256'])|set(builder['source_sha256'])|set(mask['source_sha256'])|set(cfg['source_sha256'])
    sources.update(['tools/finalize_x0_x4_followup.py','src/ps/tests/test_amc_native.py',
        'tools/prepare_x2_maskpipe_timing.py','tools/audit_x2_maskpipe.ps1',
        'build/scripts/audit_x2_maskpipe.tcl','tools/test_x2_maskpipe_chain.ps1',
        'sim/tb/cfar_reference_regwrap.v','sim/tb/cfar_maskpipe_regwrap.v',
        'sim/tb/cfar_cfgpipe_regwrap.v','tools/test_x2_maskpipe_chain.ps1',
        'build/scripts/audit_x2_maskpipe.tcl'])
    files=set(sources)
    files.update(path.relative_to(ROOT).as_posix() for path in reports.glob('*.rpt'))
    files.update(path.relative_to(ROOT).as_posix() for path in cfg_reports.glob('*.rpt'))
    files.update(['board/measurements/x4_native_board_r1.json',
        'board/measurements/x4_native_buildcheck_r1.json','sim/results/x2_maskpipe_r2.json',
        'sim/results/x2_cfgpipe_r3.json',
        'logs/X4_runtime_profile_r1.log','logs/X4_native_profile_r1.log',
        'logs/X4_native_board_r1.log','logs/X0_X4_native_full_tests_r1.log',
        'logs/X2_maskpipe_r1_console.log','logs/X2_maskpipe_timing_r1_console.log',
        'logs/X2_maskpipe_timing_r2.log','logs/X2_maskpipe_timing_r3.log',
        'sim/results/tb_cfar_maskpipe_x2.log','sim/results/tb_cfar_cfgpipe_x2.log',
        'sim/results/tb_sentinel_maskpipe_x2.log',
        'build/work/x4_native_board_r1/bundle.tar.gz',
        'build/work/x4_native_board_r1/libsentinel_gardner.so',
        'build/work/x2_maskpipe_chain_r1/cfar_core_x2.v',
        'build/work/x2_maskpipe_chain_r1/tb_sentinel_maskpipe_x2.sv'])
    files.update(path.relative_to(ROOT).as_posix() for path in (ROOT/'sim/results').glob('x2_maskpipe_*_out.hex'))
    files.update(path.relative_to(ROOT).as_posix() for path in (ROOT/'sim/results').glob('x2_cfgpipe_*_out.hex'))
    hashes={name:sha(ROOT/name) for name in sorted(files)}
    assert sha(ROOT/'build/work/x4_native_board_r1/bundle.tar.gz')==native['archive_sha256']
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):z.write(ROOT/name,name)
        z.writestr('manifest.json',json.dumps(hashes,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:
        for name,digest in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
    Path(str(archive)+'.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
    write_evidence(out,dict(status='VERIFIED_RUNTIME_AND_RTL_CANDIDATES',
        recorded_at_pc_utc=datetime.now(timezone.utc).isoformat(),
        formal_status={'X0':'DONE','X1':'FAIL','X2':'FAIL','X3':'FAIL','X4':'FAIL'},
        x4_timing=native['timing'],x4_equivalence_captures=260,x4_kernels=36,
        x4_difference=native['difference'],x4_model_sha256=native['model_sha256'],
        x4_library_sha256=native['library_sha256'],board_boot_id=native['boot_id'],
        x2_maskpipe_simulation=mask['comparisons'],x2_cfgpipe_simulation=cfg['comparisons'],
        x2_chain=chain,x2_core_timing=timing,
        regression=dict(scope='src/ps/tests + tools/tests',passed=280),
        archive=archive.relative_to(ROOT).as_posix(),archive_sha256=sha(archive),
        source_and_evidence_sha256=hashes,no_rf_access=True,bitstream_loaded=False,
        limitations=['Native latency still has >100ms outliers; original accuracy failure retained',
                     'Core-level register timing is not whole-system or IO timing acceptance',
                     '30.72MSPS is simulation only; board qualified rate remains 3.84MSPS',
                     'Default Predictor numerical path unchanged; optional native backend requires explicit selection']))
    print('X0_X4_FOLLOWUP_VERIFIED',len(files),'files')
    print(json.dumps(dict(timing=timing,chain=chain),indent=2))

if __name__=='__main__':main()
