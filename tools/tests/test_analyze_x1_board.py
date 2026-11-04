import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('x1_board_metrics',Path(__file__).resolve().parents[1]/'analyze_x1_board.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def data():
    target = {'start':703,'stop':705,'peak_bin':704,'flags':0,'peak_power':100,'sum_power':300}
    row = {'snapshot_available':True,'overflow':False,'tx_atten_mdb':[89750,89750],
           'rx_rssi_dbm':-70,'temperature_c':50,'status_latch':0,'list_overflow':False,
           'candidate_count':1,'raw_count':2,'filtered_count':1,'targets':[target],'display_fps':49}
    rows = [dict(copy.deepcopy(row), elapsed_s=i+1., display_frames=i*49,
                 input_samples=i*3840000, fft_frames=i*400, cfar_sequence=i*400)
            for i in range(100)]
    return {'status':'completed','stopped_by_signal':False,'RF_TX_requested':False,
            'actual_lo_hz':96400000,'actual_rate_hz':3840000,'rf_bandwidth_hz':1500000,
            'bus_phase':3,'elapsed_total_s':120.2,'telemetry_attempts':100,'snapshot_misses':0,
            'configuration':{'average_shift':3},'samples':rows}


def test_station_detection_uses_peak_and_actual_frequency():
    item = data()
    assert module.detection(item['samples'][0],96400000,3840000)
    assert not module.detection(item['samples'][0],98000000,3840000)
    stats = module.summarize(item,96400000)
    assert stats['station_detection_rate_all_attempts'] == 1


def test_missing_snapshots_count_as_unknown_alarm_and_missed_detection():
    item = data()
    item['samples'][0]['snapshot_available'] = False
    item['snapshot_misses'] = 1
    stats = module.summarize(item,96400000)
    assert stats['capacity_alarm_rate_upper_bound_all_attempts'] == .01
    assert stats['station_detection_rate_all_attempts'] == .99
    item['snapshot_misses'] = 0
    with pytest.raises(ValueError,match='accounted'):
        module.summarize(item,96400000)


@pytest.mark.parametrize('change',[
    {'status':'failed'},{'stopped_by_signal':True},{'RF_TX_requested':True},
    {'elapsed_total_s':100},{'actual_rate_hz':30720000},{'rf_bandwidth_hz':6000000},
])
def test_incomplete_or_different_test_is_rejected(change):
    item=data();item.update(change)
    with pytest.raises(ValueError):
        module.summarize(item,96400000)


@pytest.mark.parametrize('change',[
    {'overflow':True},{'tx_atten_mdb':[30000,30000]},{'rx_rssi_dbm':-20},
    {'temperature_c':90},{'candidate_count':34},{'status_latch':16},
])
def test_unsafe_or_inconsistent_record_is_not_hidden(change):
    item=data();item['samples'][0].update(change)
    with pytest.raises(ValueError):
        module.summarize(item,96400000)


@pytest.mark.parametrize('key', ['elapsed_s','display_frames','input_samples','fft_frames','cfar_sequence'])
def test_stale_live_telemetry_is_rejected(key):
    item = data()
    item['samples'][1][key] = item['samples'][0][key]
    with pytest.raises(ValueError, match='Non-advancing'):
        module.summarize(item,96400000)


def test_hardware_counters_may_wrap_without_becoming_stale():
    item = data()
    for row in item['samples']:
        for key in ('display_frames','fft_frames','cfar_sequence'):
            row[key] = (row[key]+0xfffffff0)&0xffffffff
    assert module.summarize(item,96400000)['station_detection_rate_all_attempts'] == 1


@pytest.mark.parametrize('value', [float('nan'),float('inf'),float('-inf'),None])
def test_invalid_numeric_telemetry_is_rejected(value):
    item = data()
    item['samples'][0]['rx_rssi_dbm'] = value
    with pytest.raises(ValueError,match='Non-finite'):
        module.summarize(item,96400000)
