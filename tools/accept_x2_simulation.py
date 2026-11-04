"""Freeze actual PASS logs and hardware/test inputs before the X2 full build."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT/'sim/results/x2_simulation_acceptance.json'
    if output.exists():
        raise FileExistsError(output)
    if (ROOT/'logs/X2_chain_r3_exit.txt').read_text().strip() != '0':
        raise RuntimeError('Full chain must finish successfully')
    names = ('sim/results/tb_x2_streams.log', 'logs/X2_chain_r3_adc.log',
             'logs/X2_chain_r3_chain.log', 'sim/results/tb_stream_stats_x2.log')
    logs = {name: (ROOT/name).read_text() for name in names}
    if any('TB_RESULT: PASS' not in log or re.search(r'^(Fatal|Error):', log, re.M) for log in logs.values()):
        raise ValueError('Simulation failure or missing PASS marker')
    matches = re.findall(r'X2_CHAIN sample_rate=(\d+) adc_inputs=(\d+) power_words=(\d+) sample_drop=(\d+) frames_in=(\d+) frames_out=(\d+) frame_drop=(\d+) threshold_pixels=(\d+)', logs[names[2]])
    if len(matches) != 1:
        raise ValueError('Ambiguous full chain metrics')
    rate, count, power, sample_drop, frames_in, frames_out, frame_drop, pixels = map(int, matches[0])
    if (rate, count, power, sample_drop, frames_in) != (30720000, 131072, 131072, 0, 64):
        raise ValueError('Full chain input/loss metrics fail')
    if frames_out + frame_drop != frames_in or pixels != frames_out*560:
        raise ValueError('Frame/display conservation fails')
    inputs = set(ROOT.glob('src/rtl/**/*.v')) | set(ROOT.glob('sim/tb/*x2.sv'))
    inputs |= set(ROOT.glob('data/reference/spectrum/*.hex'))
    inputs |= {ROOT/'tools/test_x2.ps1', ROOT/'sim/scripts/run_xsim.ps1', Path(__file__)}
    result = dict(status='PASS', scope='PC simulation only; no board bandwidth claim',
                  nominal_sample_rate_hz=rate, adc_inputs=count, power_words=power,
                  sample_drop=sample_drop, frames_in=frames_in, frames_out=frames_out,
                  frame_drop=frame_drop, threshold_pixels=pixels,
                  log_sha256={name: digest(ROOT/name) for name in names},
                  source_sha256={p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(inputs)},
                  chain_attempt=3, attempts_1_2='Runner path/declaration errors retained; no accepted chain metrics',
                  tests=['bit-exact signed Welch, shifts0/3/5/31, random backpressure',
                         'whole-frame queue drops under long stalls',
                         'ADC async FIFO conservation including intentional overflow and mismatch',
                         'non-backpressurable ADC 64-frame FFT/Welch/CFAR/paired LCD chain',
                         'atomic statistics token/ack, stalled AXI reads and token wrap'])
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    Path(str(output)+'.sha256').write_text(digest(output)+'  '+output.name+'\n', encoding='ascii')
    print(json.dumps({k: v for k, v in result.items() if not k.endswith('sha256')}, indent=2))


if __name__ == '__main__':
    main()
