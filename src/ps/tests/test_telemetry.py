import pytest
from types import SimpleNamespace
from src.ps.sentinel import telemetry
from src.ps.sentinel.telemetry import read_temperature_c


def test_xadc_name_and_iio_units(tmp_path,monkeypatch):
    # Windows cannot create the colon in Linux IIO names; fake only discovery.
    other = tmp_path/'other'
    other.mkdir()
    (other/'name').write_text('ad9361')
    device = tmp_path/'xadc'
    device.mkdir()
    for name, value in {'name':'xadc', 'in_temp0_raw':'2603',
                        'in_temp0_offset':'-2219',
                        'in_temp0_scale':'123.040771484'}.items():
        (device/name).write_text(value)
    def discover(pattern):
        assert pattern == 'iio:device*'
        return (other,device)
    monkeypatch.setattr(telemetry,'Path',lambda root:SimpleNamespace(glob=discover))
    assert read_temperature_c(tmp_path) == pytest.approx(47.247656249856)
    (device/'in_temp0_raw').write_text('nan')
    assert read_temperature_c(tmp_path) is None
    (device/'in_temp0_raw').write_text('100000')
    assert read_temperature_c(tmp_path) is None


def test_missing_temperature_is_unknown(tmp_path):
    assert read_temperature_c(tmp_path) is None
