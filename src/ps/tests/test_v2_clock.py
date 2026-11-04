"""Clock-sensitive PS control must follow the selected image, never a global guess."""
import pytest
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from src.ps.sentinel.params import clock_hz_for_image
from src.ps.sentinel.v1 import Source
from src.ps.sentinel.drivers.regs import src_ctrl as S
from src.ps.sentinel.v_y3 import checked_clock_contract, checked_y3_bundle
from src.ps.sentinel import v_y3
from src.ps.sentinel.drivers.regs import cfar_x1 as C
from src.ps.sentinel.app import monitor_x5


class Registers:
    def __init__(self):
        self.values = {S.VERSION: 0x53520001}

    def read(self, offset):
        return self.values.get(offset, 0)

    def write(self, offset, value):
        self.values[offset] = value


@pytest.mark.parametrize('image,hz', [
    ('sentinel_v1d', 150_000_000),
    ('sentinel_y3', 150_000_000),
    ('sentinel_v2_100m', 100_000_000),
])
def test_source_divider_tracks_image_clock(image, hz):
    registers = Registers()
    source = Source(registers, dsp_clk_hz=clock_hz_for_image(image))
    actual = source.configure('test', rate=3_840_000, bins=(64,), amplitudes=(4096,))
    divider = round(hz * 65536 / 3_840_000)
    assert registers.read(S.RATE_DIV) == divider
    assert actual == hz * 65536 / divider


def test_unknown_image_cannot_silently_use_legacy_clock():
    with pytest.raises(ValueError, match='Unknown bitstream clock'):
        clock_hz_for_image('sentinel_unverified')


def clock_xml(mhz):
    return ET.fromstring('''<ROOT><MODULE INSTANCE="dsp_clock"><PARAMETERS>
        <PARAMETER NAME="C_CLKOUT0_ACTUAL_FREQ" VALUE="%s"/>
        <PARAMETER NAME="C_PRIM_IN_FREQ" VALUE="50"/>
        </PARAMETERS></MODULE></ROOT>''' % mhz)


@pytest.mark.parametrize('mhz', [150, 50, 'nan', 'inf'])
def test_v2_rejects_mismatched_hwh_clock(mhz):
    with pytest.raises(ValueError, match='clock metadata'):
        checked_clock_contract(clock_xml(mhz), 'sentinel_v2_100m')


def test_accepted_legacy_clock_stays_150mhz():
    root = Path(__file__).resolve().parents[3]
    hwh = root/'board/overlay/sentinel_v1d/sentinel_v1d.hwh'
    assert checked_clock_contract(ET.parse(hwh).getroot(), 'sentinel_v1d') == 150_000_000
    assert checked_clock_contract(clock_xml(100), 'sentinel_v2_100m') == 100_000_000
    with pytest.raises(ValueError):
        checked_clock_contract(ET.Element('ROOT'), 'sentinel_v2_100m')


@pytest.mark.parametrize('timing', [
    {}, {'WNS_ns': 0.99, 'WHS_ns': .1}, {'WNS_ns': 1.1, 'WHS_ns': -.01},
    {'WNS_ns': float('nan'), 'WHS_ns': .1}, {'WNS_ns': True, 'WHS_ns': 0},
])
def test_generic_pass_cannot_bypass_v2_timing_gate(tmp_path, timing):
    receipt = tmp_path/'acceptance.json'
    receipt.write_text(json.dumps(dict(status='PASS', image='sentinel_v2_100m',
                                      final_timing=timing)))
    Path(str(receipt)+'.sha256').write_text(hashlib.sha256(receipt.read_bytes()).hexdigest())
    # No bitstream or PYNQ is available: rejection must precede hardware access.
    with pytest.raises(ValueError, match='Z10 timing gate'):
        checked_y3_bundle(tmp_path/'sentinel_v2_100m.bit', image='sentinel_v2_100m')


@pytest.mark.parametrize('image', ['sentinel_y3', 'sentinel_v2_100m'])
def test_y3_overlay_contract_uses_exact_cfar_driver_version(monkeypatch, image):
    class ContractCaptured(Exception):
        pass

    def capture_overlay(bit, download, contracts):
        assert contracts['cfar_core_0']['version'] == C.VERSION_VALUE
        raise ContractCaptured

    monkeypatch.setattr(v_y3, 'checked_y3_bundle', lambda bit, image: None)
    monkeypatch.setattr(v_y3, 'SentinelOverlay', capture_overlay)
    with pytest.raises(ContractCaptured):
        v_y3.VY3('unloaded.bit', image=image)


def test_monitor_v2_rejects_routed_candidate_below_margin_before_hardware(tmp_path,
                                                                            monkeypatch):
    bit = tmp_path/'sentinel_v2_100m.bit'
    bit.write_bytes(b'not a deployable bitstream')
    model = tmp_path/'model.npz'
    model.write_bytes(b'model test bytes')
    monkeypatch.setattr(monitor_x5, 'MODEL_SHA256', hashlib.sha256(model.read_bytes()).hexdigest())
    receipt = tmp_path/'acceptance.json'
    receipt.write_text(json.dumps(dict(status='PASS', image=bit.stem,
                                       final_timing={'WNS_ns': .210, 'WHS_ns': .030})))
    Path(str(receipt)+'.sha256').write_text(hashlib.sha256(receipt.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='Z10 timing gate'):
        monitor_x5.checked_inputs(bit, model, image='sentinel_v2_100m')


def test_monitor_v2_routes_to_separate_bundle_gate(tmp_path, monkeypatch):
    bit = tmp_path/'sentinel_v2_100m.bit'
    hwh = bit.with_suffix('.hwh')
    bit.write_bytes(b'candidate bit')
    hwh.write_bytes(b'candidate hwh')
    model = tmp_path/'model.npz'
    model.write_bytes(b'model test bytes')
    monkeypatch.setattr(monitor_x5, 'MODEL_SHA256', hashlib.sha256(model.read_bytes()).hexdigest())
    called = []
    def verified_v2(path, image):
        called.append((path, image))
        return {'status': 'PASS'}
    monkeypatch.setattr(monitor_x5, 'checked_y3_bundle', verified_v2)
    receipt = tmp_path/'acceptance.json'
    receipt.write_text(json.dumps(dict(status='PASS', image=bit.stem,
                                       artifacts_sha256={name: hashlib.sha256(path.read_bytes()).hexdigest()
                                                         for name, path in ((bit.name, bit), (hwh.name, hwh))})))
    Path(str(receipt)+'.sha256').write_text(hashlib.sha256(receipt.read_bytes()).hexdigest())
    assert monitor_x5.checked_inputs(bit, model, image='sentinel_v2_100m')['image'] == bit.stem
    assert called == [(bit, bit.stem)]
    with pytest.raises(ValueError, match='Explicit image'):
        monitor_x5.checked_inputs(bit, model, image='sentinel_v1d')


def development_receipt(tmp_path, **changes):
    """Model an independently reviewed image; no PYNQ/hardware access."""
    review = dict(status='PASS_DEVELOPMENT_REVIEW', image='sentinel_v2_100m',
                  artifacts_sha256={'candidate.bit': 'a', 'candidate.hwh': 'b'},
                  checks={key: True for key in ('basic_timing', 'cdc', 'external_io',
                          'pins_and_voltages', 'build_inputs', 'route_and_drc')})
    review.update(changes)
    path = tmp_path/'development_review.json'
    path.write_text(json.dumps(review))
    return dict(deployment_policy='development_nonnegative_v1',
                final_timing={'WNS_ns': .210, 'WHS_ns': .030},
                artifacts_sha256=review['artifacts_sha256'],
                development_review_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_explicit_reviewed_development_policy_accepts_current_slack(tmp_path):
    receipt = development_receipt(tmp_path)
    v_y3.checked_v2_timing_policy(receipt, tmp_path)
    receipt['final_timing'] = {'WNS_ns': 0, 'WHS_ns': 0}
    v_y3.checked_v2_timing_policy(receipt, tmp_path)


@pytest.mark.parametrize('key,value', [('WNS_ns', -.001), ('WHS_ns', -.001),
    ('WNS_ns', float('nan')), ('WHS_ns', float('inf')), ('WNS_ns', True)])
def test_development_policy_still_rejects_bad_timing(tmp_path, key, value):
    receipt = development_receipt(tmp_path)
    receipt['final_timing'][key] = value
    with pytest.raises(ValueError, match='timing gate'):
        v_y3.checked_v2_timing_policy(receipt, tmp_path)


@pytest.mark.parametrize('key', ['basic_timing', 'cdc', 'external_io',
    'pins_and_voltages', 'build_inputs', 'route_and_drc'])
@pytest.mark.parametrize('value', [False, None, 1, 'PASS'])
def test_every_development_review_check_is_required(tmp_path, key, value):
    receipt = development_receipt(tmp_path)
    path = tmp_path/'development_review.json'
    review = json.loads(path.read_text())
    review['checks'][key] = value
    path.write_text(json.dumps(review))
    receipt['development_review_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='Incomplete or mismatched'):
        v_y3.checked_v2_timing_policy(receipt, tmp_path)


def test_development_review_cannot_be_reused_for_different_artifacts(tmp_path):
    receipt = development_receipt(tmp_path)
    receipt['artifacts_sha256'] = {'candidate.bit': 'different'}
    with pytest.raises(ValueError, match='mismatched'):
        v_y3.checked_v2_timing_policy(receipt, tmp_path)


def test_development_review_digest_prevents_unnoticed_changes(tmp_path):
    receipt = development_receipt(tmp_path)
    (tmp_path/'development_review.json').write_text('{}')
    with pytest.raises(ValueError, match='digest mismatch'):
        v_y3.checked_v2_timing_policy(receipt, tmp_path)


def test_unknown_deployment_policy_is_rejected(tmp_path):
    receipt = development_receipt(tmp_path)
    receipt['deployment_policy'] = 'skip_checks'
    with pytest.raises(ValueError, match='Unknown'):
        v_y3.checked_v2_timing_policy(receipt, tmp_path)


def test_health_reads_lcd_status_not_ui_epoch():
    from types import SimpleNamespace
    from sentinel.drivers.regs import lcd_ctrl as L
    hw = object.__new__(v_y3.VY3)
    hw.perf = SimpleNamespace(snapshot=lambda: SimpleNamespace(status=4))
    hw.cfar = SimpleNamespace(mmio=SimpleNamespace(read=lambda offset: 0))
    # An ordinary UI epoch must never look like a display fault.
    hw.lcd = SimpleNamespace(registers=SimpleNamespace(
        read=lambda offset: 0x1c if offset == L.UI_EPOCH else 1))
    assert hw.channel_health() == 0
    hw.lcd.registers.read = lambda offset: 4 if offset == L.STATUS else 0
    assert hw.channel_health() == 4 << 16
