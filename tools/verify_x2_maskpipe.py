"""Compare registered-mask results against preserved golden vectors."""
import argparse
from pathlib import Path
from x2_transport import ROOT,sha,verified,write_evidence
from analyze_cfar_x1_core import words

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt',required=True,type=int,choices=(1,2,3))
    attempt=p.parse_args().attempt
    folder=ROOT/'data/reference/cfar/x1_guard8'
    import json
    manifest=json.loads((folder/'manifest.json').read_text())
    for name,digest in manifest['sha256'].items():
        assert sha(folder/name)==digest,name
    comparisons={}
    for name in ('threshold','hit','db','occupancy','targets','stats'):
        expected=folder/(('targets_words' if name=='targets' else name)+'.hex')
        actual=ROOT/'sim/results'/('x2_maskpipe_'+name+'_out.hex')
        a,b=words(expected),words(actual)
        assert a==b,name
        comparisons[name]=dict(words=len(a),mismatches=0,expected_sha256=sha(expected),actual_sha256=sha(actual))
    log=ROOT/'sim/results/tb_cfar_maskpipe_x2.log'
    assert 'TB_RESULT: PASS X1_CORE 18 cases' in log.read_text()
    sources=['src/rtl/x2_opt/cfar_core_maskpipe_x2.v','src/rtl/cfar_x1/cfar_core_x1.v',
             'src/rtl/cfar_x1/cfar_detect_x1.v','src/rtl/cfar_x1/cfar_cluster_x1.v',
             'src/rtl/cfar_x1/cfar_x1_regs.v','src/rtl/cfar/cfar_occupancy.v',
             'src/rtl/common/axis_broadcast2.v','sim/tb/tb_cfar_maskpipe_x2.sv',
             'tools/prepare_x2_maskpipe.py','tools/test_x2_maskpipe.ps1',
             'tools/verify_x2_maskpipe.py']
    result=dict(status='PASS_SIMULATION_ONLY',cases=18,comparisons=comparisons,
                source_sha256={name:sha(ROOT/name) for name in sources},log_sha256=sha(log),
                manifest_sha256=sha(folder/'manifest.json'),formal_x2_status='FAIL',
                notes=['One-cycle payload register after mask computation',
                       'Same numeric target/mask/MMIO contract, changed cycle latency',
                       'No whole-system synthesis, timing claim, bitstream or RF access'])
    write_evidence(ROOT/'sim/results'/('x2_maskpipe_r%d.json'%attempt),result)
    print('X2_MASKPIPE_VERIFIED',comparisons)

if __name__=='__main__':main()
