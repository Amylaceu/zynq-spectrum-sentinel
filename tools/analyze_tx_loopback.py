"""Verify archived native captures independently of the board's pass flag."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ps.sentinel.loopback import sequence


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', default='board/measurements/tx_loopback.json')
    args = parser.parse_args()
    result_path = ROOT / args.result
    result = json.loads(result_path.read_text(encoding='utf-8'))
    assert result['status'] == 'passed' and result['stage'] == 'completed'
    assert result['gpio_after_close'] == 0 and not result['buffers_quarantined']
    assert 'tx_stop_error' not in result and not result.get('cleanup_acceptance_failed')
    assert result['product_id'] & 0xf8 == 8
    assert result['observe_config'] == 1 and result['dac_data_select'] == [2]*4
    assert result['rx_channel_control'] == [0x51]*4
    assert result['tx_atten_mdb_samples']
    assert all(value == [89750, 89750] for value in result['tx_atten_mdb_samples'])
    assert [entry['kind'] for entry in result['sequences']] == ['ramp', 'pn']
    if result['attempt'] == 4:
        assert result['extra_attempt_user_authorized']

    fig, axes = plt.subplots(2, 2, figsize=(11, 6), constrained_layout=True)
    checks = []
    for row, entry in enumerate(result['sequences']):
        capture = (ROOT/'board'/entry['capture_file']).resolve()
        assert (ROOT/'board/measurements').resolve() in capture.parents
        assert sha256(capture) == entry['capture_sha256']
        with np.load(capture, allow_pickle=False) as archive:
            reference = archive['reference_native']
            received = archive['received_native']
        assert reference.shape == (8192, 4) and received.shape == (32768, 4)
        assert reference.dtype == np.dtype('<i2') and received.dtype == np.dtype('<i2')
        assert np.array_equal(reference, sequence(entry['kind']))
        assert hashlib.sha256(reference.tobytes()).hexdigest() == entry['reference_sha256']
        assert hashlib.sha256(received.tobytes()).hexdigest() == entry['rx_sha256']
        offset = entry['alignment_samples']
        assert isinstance(offset, int) and 0 <= offset < len(reference)
        expected = reference[(np.arange(len(received)) + offset) % len(reference)]
        errors = received.astype(np.int32) - expected.astype(np.int32)
        mismatch = np.count_nonzero(errors, axis=0)
        assert not mismatch.any() and entry['mismatch_words'] == 0 and entry['passed']
        assert entry['compared_words'] == received.size and entry['guards_ok']
        check = dict(kind=entry['kind'], compared_words=int(received.size),
                     mismatch_by_channel=mismatch.tolist(), alignment_samples=offset,
                     capture_file=str(capture.relative_to(ROOT)).replace('\\', '/'),
                     capture_bytes=capture.stat().st_size, capture_sha256=sha256(capture))
        checks.append(check)
        axes[row, 0].plot(expected[:64, 0], label='aligned reference I1', lw=2)
        axes[row, 0].plot(received[:64, 0], '.', label='captured I1', ms=3)
        axes[row, 0].set(title=entry['kind'].upper()+': first 64 samples',
                         xlabel='captured sample', ylabel='native signed 12-bit code')
        axes[row, 0].legend(fontsize=8)
        for ch, label in enumerate(('I1', 'Q1', 'I2', 'Q2')):
            axes[row, 1].plot(errors[:, ch], label=label, lw=1)
        axes[row, 1].set(title='All 131,072 words: zero error', xlabel='captured sample',
                         ylabel='received - reference', ylim=(-1, 1))
        axes[row, 1].legend(fontsize=8)
        print(json.dumps(check))
    fig.suptitle('AD9361 internal digital loopback | 30.72 MSPS | TX attenuation 89.75 dB')
    figure = ROOT/'report/figures/tx_loopback.png'
    fig.savefig(figure, dpi=150)
    plt.close(fig)
    acceptance = dict(status='passed', scope='finite internal digital loopback; no RF/BER claim',
                      attempt=result['attempt'], source_result=str(result_path.relative_to(ROOT)),
                      result_sha256=sha256(result_path), sequences=checks,
                      tx_atten_mdb_samples=result['tx_atten_mdb_samples'], gpio_after_close=0,
                      buffers_quarantined=False, figure='report/figures/tx_loopback.png')
    (ROOT/'board/measurements/tx_loopback_acceptance.json').write_bytes(
        (json.dumps(acceptance, indent=2)+'\n').encode('utf-8'))
    print('TX_LOOPBACK_ARCHIVE_ACCEPTANCE_PASS')


if __name__ == '__main__':
    main()
