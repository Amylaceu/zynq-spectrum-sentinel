"""Summarize the two user-confirmed antenna captures without claiming audio SNR."""
import json
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[1]
folder = root / 'board/measurements'
records = []
for attempt, antenna in ((2, '2.4GHz panel'), (3, '20-512MHz magnetic')):
    capture = json.loads((folder / f'fm_audio_95800000_round{attempt}.json').read_text())
    demod = json.loads((folder / f'fm_95800000_round{attempt}_demod.json').read_text())
    voice = json.loads((folder / f'fm_95800000_round{attempt}_voice.json').read_text())
    assert capture['status'] == 'passed'
    assert capture['gpio_after_close'] == 0 and not capture['buffers_quarantined']
    assert capture['tx_attenuation_mdb'] == [89750, 89750]
    assert all(c['guards_ok'] and c['passed'] for c in capture['captures'])
    def span(values):
        a = np.asarray(values)
        return dict(minimum=float(a.min()), median=float(np.median(a)), maximum=float(a.max()))
    records.append(dict(
        attempt=attempt, antenna=antenna,
        sample_rate_hz=capture['sample_rate_hz'], rx_lo_hz=capture['rx_lo_hz'],
        bit_sha256=capture['bit_sha256'],
        capture_count=len(capture['captures']), iq_samples=capture['iq_samples'],
        rx1_gain_db=span([c['rx_gain_db'][0] for c in capture['captures']]),
        chip_rx1_rssi_mdb_uncalibrated=span([c['chip_rssi_mdb'][0] for c in capture['captures']]),
        raw_word_clipped_fraction=span([c['clipped_fraction'] for c in capture['captures']]),
        pilot_prominence_db=span([c['pilot_prominence_db'] for c in demod['chunks']]),
        stereo_pilot_in_all_chunks=demod['stereo_pilot_in_all_chunks'],
        discriminator_rms_hz=span([c['demod_frequency_rms_hz'] for c in demod['chunks']]),
        voice_short_slip_corrected_fraction=span([
            c['short_phase_slip_corrected_fraction'] for c in voice['chunks']]),
    ))
for key in ('sample_rate_hz', 'rx_lo_hz', 'bit_sha256', 'capture_count', 'iq_samples'):
    assert records[0][key] == records[1][key], key
result = dict(date='2026-11-02', station_candidate_hz=95800000,
              records=records, matching_settings_verified=True,
              clean_reference_snr_measured=False,
              subjective_quality_after_replacement='pending_user_listening',
              limitations='Snapshots have gaps; broadcast program/time and antenna placement were not controlled. RSSI is an uncalibrated chip readback, not antenna power.')
target = folder / 'fm_antenna_comparison.json'
target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps(result, indent=2))
