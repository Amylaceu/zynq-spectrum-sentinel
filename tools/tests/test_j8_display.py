"""J8 page ownership, measured ranking and LCD metadata regressions (no RF)."""
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from product import app_instance
from sentinel_host.application_v61 import Window
from sentinel.app.features_apps import strongest_points
from sentinel.app.feature_display import display_options


@pytest.fixture
def window():
    app = app_instance()
    w = Window(ROOT)
    yield w
    w.worker = None; w.active = None; w.pending = None; w.app_busy = False
    w.wifi_worker = None; w.close(); app.processEvents()


def test_cached_wifi_does_not_stop_audio_or_steal_page_on_completion(window):
    w = window
    commands = []
    w.worker = SimpleNamespace(command=lambda *a, **k: commands.append(k))
    w.last_packet = time.monotonic()
    w.active = w.app_identity = 'F8'
    w.panel_for('F8')
    w.wifi_result = dict(status='DECODED_BEACONS', networks=[])
    w.start_feature('F14')
    assert not commands and w.active == 'F8' and w.selected == 'F14'
    w.refresh()
    assert w.selected == 'F14'
    rows = w.table.rowCount()
    w.packet(dict(type='telemetry', scene='F8', display_fps=49,
                  audio=dict(pcm_samples=99999, output_unmuted=True), pilot={}),
             b'', time.monotonic())
    assert w.table.rowCount() == rows
    assert '播放样本' not in [w.table.item(i, 0).text() for i in range(rows)]
    w.panel_for('F1'); w.tabs.setCurrentIndex(0)
    w.wifi_complete(dict(result=dict(status='DECODED_BEACONS', networks=[])))
    assert w.selected == 'F1' and w.tabs.currentIndex() == 0
    assert w.cards['F14'][1].toolTip() == '结果就绪'


def test_switch_clears_metrics_and_twin_returns_to_application(window):
    w = window
    w.worker = SimpleNamespace(command=lambda *a, **k: 1)
    w.last_packet = time.monotonic()
    w.display_metrics({'播放样本': dict(before=0, after=12345, unit='样本')})
    w.start_feature('F11')
    assert w.table.rowCount() == 0 and w.last_result is None
    assert w.plot.isHidden()
    w.toggle_twin(); assert w.tabs.currentIndex() == 1
    w.toggle_twin(); assert w.tabs.currentIndex() == w.app_tab


def test_1080p_all_thirteen_cards_fit_without_navigation_scroll(window):
    w = window
    w.cards['F12'][0].show()
    w.resize(1920, 1080); w.show(); app_instance().processEvents()
    assert w.nav_scroll.verticalScrollBar().maximum() == 0
    assert len([v for v in w.cards.values() if not v[0].isHidden()]) == 13
    w.panel_for('F0'); assert w.plot.isHidden() and w.app_plot.isHidden()
    w.panel_for('F8'); assert w.plot.isHidden() and w.app_plot.isHidden()


def test_rank_fm_separately_and_never_rank_gaps():
    frequency = np.array([90000000, 95000000, 100000000, 310000000, 400000000])
    power = np.array([1., 2., 3., 100., 1000.])
    count = np.array([1, 1, 1, 1, 0])
    assert strongest_points(frequency, power, count)[0]['frequency_hz'] == 310000000
    fm = strongest_points(frequency, power, count, (88000000, 108000000))
    assert [v['frequency_hz'] for v in fm] == [100000000, 95000000, 90000000]


def test_lcd_labels_carry_card_and_actual_number():
    value = display_options('F10', dict(metrics={'CPU/PL比值': dict(after=23.125)}))
    assert value['demo_title'] == 'F10 CPU / PL'
    assert '23.1 X' in value['model_status']
    assert '45%' in display_options('F14', progress='CAP 45%')['model_status']


def test_megahertz_comparison_keeps_station_precision(window):
    window.display_metrics({'电台': dict(before='—', after=100.9, unit='MHz')})
    assert window.table.item(0, 2).text() == '100.900 MHz'


def test_search_cannot_interrupt_playing_broadcast(window):
    commands = []
    window.worker = SimpleNamespace(command=lambda *a, **k: commands.append(k))
    window.last_packet = time.monotonic()
    window.active = 'F8'
    window.start_feature('F8', action='search')
    assert not commands
    assert window.active == 'F8'
    assert '先点击停止' in window.state.text()


def test_search_preserves_chosen_frequency_without_sending_tuning(window):
    commands = []
    window.worker = SimpleNamespace(command=lambda *a, **k: commands.append(k))
    window.last_packet = time.monotonic()
    window.station.addItem('100.900 MHz', 100900000)
    window.station.setCurrentIndex(window.station.findData(100900000))
    window.application_data(dict(stage='found_stations', stations=[
        dict(frequency_hz=97000000, lo_hz=97050000)]))
    assert window.station.currentData() == 100900000
    assert window.station.findData(97000000) >= 0
    assert not commands


def test_default_fm_station_is_explicit_not_search_ranking(window):
    assert window.station.currentData() == 95800000


def test_first_f12_searches_current_rf_instead_of_falling_back_to_old_station(tmp_path):
    from sentinel.app.features_apps import ApplicationBackend
    b = ApplicationBackend.__new__(ApplicationBackend)
    calls = []
    def search(_):
        calls.append('search'); b.found_stations = []
    b.run_f8_search = search
    b._prepare_capture_dma = lambda: calls.append('prepare')
    b._start_receive = lambda: calls.append('receive')
    b.radio = SimpleNamespace(configure=lambda *a: None)
    b.config = dict(lo_hz=96050000, rf_bandwidth_hz=1500000, station_hz=95800000,
                    stations=[dict(frequency_hz=95800000)])
    b.job_output = tmp_path
    b.emit = lambda *a, **k: None
    result = b.run_f12(dict(station_hz=0))
    assert calls[0] == 'search' and result['status'] == 'NOT_QUALIFIED'
    assert result['qualification'] == []
    calls.clear()
    b.run_f12(dict(station_hz=0))
    assert 'search' not in calls
