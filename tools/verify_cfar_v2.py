"""Compare V2 CFAR against immutable 18-case golden vectors."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(path):
    return [int(word, 16) for word in path.read_text().split()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    output = ROOT/('sim/results/v2_cfar_r%d.json' % args.attempt)
    if output.exists():
        raise FileExistsError('Preserve previous evidence')
    folder = ROOT/'data/reference/cfar/x1_guard8'
    manifest = json.loads((folder/'manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if sha(folder/name) != digest:
            raise ValueError('Golden manifest mismatch '+name)
    sources = [ROOT/p for p in (
        'src/rtl/cfar_v2/cfar_core_v2.v', 'src/rtl/cfar_v2/cfar_cluster_v2.v',
        'src/rtl/cfar_x1/cfar_detect_x1.v', 'src/rtl/cfar_x1/cfar_x1_regs.v',
        'src/rtl/cfar/cfar_occupancy.v', 'src/rtl/common/axis_broadcast2.v',
        'sim/tb/tb_cfar_v2.sv', 'tools/verify_cfar_v2.py', 'tools/test_cfar_v2.ps1')]
    logs = [ROOT/'sim/results/tb_cfar_v2.log', folder/'manifest.json']
    if 'TB_RESULT: PASS X1_CORE 18 cases' not in logs[0].read_text():
        raise ValueError('Missing complete CFAR PASS marker')
    comparisons = {}
    for name in ('threshold', 'hit', 'db', 'occupancy', 'targets', 'stats'):
        expected = folder/(('targets_words' if name == 'targets' else name)+'.hex')
        actual = ROOT/('sim/results/v2_cfar_'+name+'_out.hex')
        if words(expected) != words(actual):
            raise ValueError('Golden mismatch '+name)
        comparisons[name] = dict(words=len(words(expected)), mismatches=0,
                                 expected_sha256=sha(expected), actual_sha256=sha(actual))
        logs.extend((expected, actual))
    value = dict(status='PASS', attempt=args.attempt, cases=18,
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='CFAR numeric/MMIO equivalence, stalls, config, reset and saturation; no timing claim',
                 comparisons=comparisons,
                 source_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sources},
                 log_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in logs})
    output.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
    print('V2_CFAR_GOLDEN_PASS cases=18')


if __name__ == '__main__':
    main()
