"""Prepare/audit an isolated guard=8 variant of the frozen 18-case RTL test."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

import export_cfar_x1_core_vectors as vectors
from analyze_cfar_x1_core import words
from run_x1_board import ROOT, sha, write_evidence

DIRECTORY = ROOT/'data/reference/cfar/x1_guard8'
TESTBENCH = ROOT/'sim/tb/tb_cfar_guard8.sv'
SOURCES = ['src/rtl/cfar_x1/cfar_core_x1.v', 'src/rtl/cfar_x1/cfar_x1_regs.v',
           'src/rtl/cfar_x1/cfar_cluster_x1.v', 'src/rtl/cfar_x1/cfar_detect_x1.v',
           'src/rtl/cfar/cfar_occupancy.v', 'src/rtl/common/axis_broadcast2.v',
           'sim/tb/tb_cfar_core_x1.sv', 'sim/golden/cfar_x1.py', 'sim/golden/cfar.py',
           'tools/export_cfar_x1_core_vectors.py', 'tools/verify_x1_guard8_sim.py']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        if DIRECTORY.exists() or TESTBENCH.exists():
            parser.error('Preserve previous simulation')
        cases = vectors.make_cases()
        for case in cases:
            case['g'] = 8
            case['name'] = 'guard8_'+case['name']
        # Reuse the frozen vector serialization without editing the old exporter.
        with patch.object(vectors, 'make_cases', return_value=cases), patch.object(
                sys, 'argv', ['export', '--out', str(DIRECTORY)]):
            vectors.main()
        template = (ROOT/'sim/tb/tb_cfar_core_x1.sv').read_text()
        TESTBENCH.write_text(template.replace('tb_cfar_core_x1', 'tb_cfar_guard8').replace(
            'x1_core_', 'x1_guard8_'), encoding='utf-8')
        write_evidence(DIRECTORY/'provenance.json', {
            'scope': '18 synthetic cases with guard=8; no RF acceptance',
            'source_sha256': {name: sha(ROOT/name) for name in SOURCES},
            'generated_testbench_sha256': sha(TESTBENCH)})
        return
    provenance = json.loads((DIRECTORY/'provenance.json').read_text())
    for name, digest in provenance['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Simulation source changed: '+name)
    if sha(TESTBENCH) != provenance['generated_testbench_sha256']:
        raise ValueError('Generated testbench changed')
    manifest = json.loads((DIRECTORY/'manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if sha(DIRECTORY/name) != digest:
            raise ValueError('Vector changed: '+name)
    comparisons = {}
    for name in ('threshold', 'hit', 'db', 'occupancy', 'targets', 'stats'):
        expected = DIRECTORY/(('targets_words' if name == 'targets' else name)+'.hex')
        actual = ROOT/'sim/results'/('x1_guard8_'+name+'_out.hex')
        if words(expected) != words(actual):
            raise ValueError('RTL/model mismatch: '+name)
        comparisons[name] = dict(words=len(words(expected)), mismatches=0,
                                 expected_sha256=sha(expected), actual_sha256=sha(actual))
    log = ROOT/'sim/results/tb_cfar_guard8.log'
    text = log.read_text(encoding='utf-8-sig')
    if 'TB_RESULT: PASS X1_CORE 18 cases' not in text or 'X1_ADD_SUB40_PASS 10096' not in text:
        raise ValueError('Simulation incomplete')
    result = dict(status='PASS', scope='guard=8 RTL/model simulation only', cases=18,
                  comparisons=comparisons, source_sha256=provenance['source_sha256'],
                  manifest_sha256=sha(DIRECTORY/'manifest.json'), log_sha256=sha(log))
    write_evidence(ROOT/'sim/results/x1_guard8_acceptance.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
