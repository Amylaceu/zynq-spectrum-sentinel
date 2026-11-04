"""Reject plausible-looking stale/corrupt data before diagnosing RF decisions."""
import copy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_x1_diagnostic import CONFIGURATION, decision_trace, reconstruct, verify_receipt
from sim.golden.cfar_x1 import cluster_x1, detect_x1, mask_bins


def fixture():
    power = np.ones((4, 2048), dtype=np.uint32)
    power[:, 703:706] = 100000
    data = {'status': 'completed', 'source': 'rf', 'RF_TX_requested': False,
            'configuration': copy.deepcopy(CONFIGURATION), 'lo_hz': 96400000,
            'rate_hz': 3840000, 'rf_bandwidth_hz': 1500000, 'warmup_frames': 64,
            'requested_frames': 4, 'warmup_association': {'cfar_before': 0,
                'source_frames': 64, 'source_samples': 131072, 'spec_sequence': 64,
                'perf_delta': [131072, 64, 64], 'perf_status': 0}, 'samples': []}
    for index, p in enumerate(power):
        _, _, c = detect_x1(p)
        safety = {'temperature_c': 50, 'rx_rssi_dbm': -70, 'tx_atten_mdb': [89750, 89750],
                  'actual_lo_hz': 96399998, 'actual_rate_hz': 3840000}
        data['samples'].append(dict(safety, safety_before=safety.copy(), index=index,
            elapsed_s=index+1., cfar_sequence=65+index, association={
                'cfar_before': 64+index, 'source_frames': 1, 'source_samples': 2048,
                'spec_sequence': 65+index, 'perf_delta': [2048, 1, 1], 'perf_status': 0,
                'capture_token': index % 2}, hit_count=c.hit_count, raw_count=c.raw_count,
            filtered_count=c.filtered_count, candidate_count=c.candidate_count,
            status_latch=c.status_latch, list_overflow=c.overflow, targets=[
                dict(start=int(t['start']), stop=int(t['stop']), peak_bin=int(t['peak_bin']),
                     flags=int(t['flags']), peak_power=int(t['peak_pwr']), sum_power=int(t['sum_pwr']))
                for t in c.targets]))
    return data, power


def test_exact_association_and_decisions():
    data, power = fixture()
    threshold, hit, mask, traces = reconstruct(data, power)
    assert threshold.shape == hit.shape == (4, 2048)
    assert mask.sum() == 7
    assert all(t['station_peak_detected'] for t in traces)


@pytest.mark.parametrize('field,value', [('cfar_sequence',64), ('hit_count',0),
    ('candidate_count',32), ('elapsed_s',float('nan')), ('list_overflow',True)])
def test_rejects_stale_or_corrupt_records(field, value):
    data, power = fixture()
    data['samples'][0][field] = value
    with pytest.raises(ValueError):
        reconstruct(data, power)


def test_rejects_valid_hash_but_wrong_raw_power():
    data, power = fixture()
    power[0, 704] += 1
    with pytest.raises(ValueError, match='target mismatch'):
        reconstruct(data, power)


def test_rejects_repeated_capture_token():
    data, power = fixture()
    data['samples'][1]['association']['capture_token'] = 0
    with pytest.raises(ValueError, match='unpaired'):
        reconstruct(data, power)


def test_peak_offset_label_does_not_redefine_acceptance():
    power, hit = np.ones(2048, dtype=np.uint32), np.zeros(2048, dtype=np.uint8)
    hit[[704, 710, 716, 722]] = 1
    power[722] = 100000
    c = cluster_x1(hit, power)
    t = decision_trace(hit, power, c, mask_bins(2048, (), 3))
    assert not t['station_peak_detected']
    assert t['published_interval_overlaps_tolerance']
    assert 'overlapping_segment_peak_outside_tolerance' in t['labels']


@pytest.mark.parametrize('field', ['archive_sha256', 'result_sha256', 'boot_id_before'])
def test_receipt_mismatch_rejected_even_if_other_hashes_equal(field):
    data = {'source': 'rf', 'boot_id': 'BOOT', 'raw_archive_sha256': 'ARCHIVE'}
    state = {'boot_id': 'BOOT', 'status': 'PASS', 'gpio_data': 0, 'source_ctrl': 0}
    execution = {'status': 'PASS_EXECUTION', 'ssh_exit_code': 0, 'mode': 'rf',
        'result_sha256': 'JSON', 'archive_sha256': 'ARCHIVE', 'boot_id_before': 'BOOT',
        'preflight': state.copy(), 'postflight': state.copy(), 'user_confirmed_rx1a_tx_empty': True}
    verify_receipt(data, execution, 'JSON', 'ARCHIVE')
    execution[field] = 'WRONG'
    with pytest.raises(ValueError, match='association mismatch'):
        verify_receipt(data, execution, 'JSON', 'ARCHIVE')
