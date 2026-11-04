"""Record X1 integration simulation with unchanged input/source hashes."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    prefix = ROOT / ('logs/X1_chain_r%d' % args.attempt)
    inputs = json.loads(Path(str(prefix)+'_inputs.json').read_text(encoding='utf-8-sig'))
    for name, expected in inputs.items():
        if digest(ROOT/name) != expected:
            raise ValueError('Input changed during simulation: '+name)
    log = Path(str(prefix)+'_xsim.log')
    text = log.read_text(encoding='utf-8-sig')
    marker = 'TB_RESULT: PASS integrated FFT/Welch->CFAR-X1->LCD pairing'
    if marker not in text or re.search(r'^(?:Fatal|ERROR):', text, re.M):
        raise ValueError('Simulation did not pass')
    match = re.search(r'CHAIN_STEADY input_cycles=([0-9]+) output_cycles=([0-9]+) frames=7 dsp_hz=150000000', text)
    if match is None or min(map(int, match.groups())) <= 0:
        raise ValueError('Missing steady-state cycle measurement')
    result = {
        'status': 'PASS',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': 'PC-only integration simulation, no ADC realtime or board timing acceptance',
        'input_frames': 16, 'input_samples': 32768,
        'exact_power_comparisons': 8192, 'threshold_pixels_observed': 8960,
        'coherent_snapshot_columns_compared': 560,
        'steady_state': {'input_cycles': int(match[1]), 'output_cycles': int(match[2]),
                         'frames': 7, 'dsp_clock_hz': 150000000},
        'source_and_vector_sha256': inputs, 'log_sha256': digest(log),
        'hardware_accessed': False,
    }
    path = ROOT/('sim/results/x1_chain_r%d_acceptance.json' % args.attempt)
    sidecar = Path(str(path)+'.sha256')
    if path.exists() or sidecar.exists():
        raise FileExistsError('Preserve prior acceptance')
    path.write_text(json.dumps(result, indent=2)+chr(10), encoding='utf-8')
    sidecar.write_text(digest(path)+'  '+path.name+chr(10), encoding='ascii')
    print(json.dumps(result['steady_state']))
    print('X1_CHAIN_ACCEPTANCE_PASS')


if __name__ == '__main__':
    main()
