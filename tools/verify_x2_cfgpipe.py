"""Final configuration-pipeline candidate verification; retain failed rounds."""
from pathlib import Path
from x2_transport import ROOT,sha,write_evidence
from analyze_cfar_x1_core import words

def main():
    directory=ROOT/'data/reference/cfar/x1_guard8'
    comparisons={}
    for name in ('threshold','hit','db','occupancy','targets','stats'):
        expected=directory/(('targets_words' if name=='targets' else name)+'.hex')
        actual=ROOT/'sim/results'/('x2_cfgpipe_'+name+'_out.hex')
        assert words(expected)==words(actual),name
        comparisons[name]=dict(words=len(words(expected)),mismatches=0,
                               expected_sha256=sha(expected),actual_sha256=sha(actual))
    log=ROOT/'sim/results/tb_cfar_cfgpipe_x2.log'
    assert 'TB_RESULT: PASS X1_CORE 18 cases' in log.read_text()
    files=['src/rtl/x2_opt/cfar_core_cfgpipe_x2.v','sim/tb/tb_cfar_cfgpipe_x2.sv',
           'tools/prepare_x2_cfgpipe.py','tools/test_x2_cfgpipe.ps1','tools/verify_x2_cfgpipe.py']
    write_evidence(ROOT/'sim/results/x2_cfgpipe_r3.json',dict(status='PASS_SIMULATION_ONLY',
        comparisons=comparisons,source_sha256={n:sha(ROOT/n) for n in files},log_sha256=sha(log),
        formal_x2_status='FAIL',notes=['Registered config validity plus split AXI write quiet gate',
                                     'Mid-frame config changes, stalled AXI, reset and invalid masks tested']))
    print('X2_CFGPIPE_VERIFIED')

if __name__=='__main__':main()
