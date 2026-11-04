"""Y3-only extension of the accepted v1d PS contract.

This module never loads hardware on import. The v1d image and Y2 evidence are
not mutated; it requires a distinct Y3 acceptance receipt and exact map.
"""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .v1 import V1, Source, CONTRACTS
from .v1d import V1d
from .v1b import V1b
from .overlay import SentinelOverlay
from .drivers.cfar_x1 import CfarX1
from .drivers.perf import Performance
from .drivers.regs import cfar_x1 as C
from .drivers.regs import lcd_ctrl as L
from .lcd_x5 import X5LCD, VERSION as LCD_VERSION
from .mmio import make_mmio
from .capture_x5 import ChannelCapture
from .audio_y3 import AudioControl
from .params import clock_hz_for_image


ADDRESSES = {'y3_audio_ctrl': 0x41260000, 'y3_audio_state': 0x41270000,
             'y3_audio_counts': 0x41280000, 'axi_iic_audio': 0x41630000}
MEMORIES = {'axi_lcd_ui': (0x42100000, 131072),
            'axi_power_capture': (0x42010000, 8192)}


def checked_clock_contract(root, image):
    """Reject a legacy or unknown clock before loading PL or accessing MMIO."""
    expected_hz = clock_hz_for_image(image)
    module = root.find(".//MODULE[@INSTANCE='dsp_clock']")
    if module is None:
        raise ValueError('Missing DSP clock metadata')
    parameters = {p.get('NAME'): p.get('VALUE')
                  for p in module.findall('./PARAMETERS/PARAMETER')}
    try:
        actual_hz = float(parameters['C_CLKOUT0_ACTUAL_FREQ']) * 1e6
        input_hz = float(parameters['C_PRIM_IN_FREQ']) * 1e6
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError('Invalid DSP clock metadata') from error
    if actual_hz != expected_hz or input_hz != 50_000_000:
        raise ValueError('DSP clock metadata differs from ' + image)
    return expected_hz


def checked_y3_bundle(bit, image='sentinel_y3'):
    bit = Path(bit)
    receipt = bit.parent/'acceptance.json'
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(receipt) != Path(str(receipt)+'.sha256').read_text().split()[0]:
        raise ValueError('Y3 acceptance receipt SHA256 mismatch')
    data = json.loads(receipt.read_text())
    if data.get('status') != 'PASS' or data.get('image') != image:
        raise ValueError('Require separately audited '+image+' image')
    if image == 'sentinel_v2_100m':
        checked_v2_timing_policy(data, bit.parent)
    for suffix in ('bit', 'hwh'):
        path = bit.with_suffix('.'+suffix)
        if digest(path) != data['artifacts_sha256'].get(path.name):
            raise ValueError('Y3 bit/HWH integrity mismatch')
    root = ET.parse(str(bit.with_suffix('.hwh'))).getroot()
    checked_clock_contract(root, image)
    if tuple(root.find('SYSTEMINFO').get(k) for k in ('DEVICE', 'PACKAGE', 'SPEEDGRADE')) != ('7z020', 'clg484', '-2'):
        raise ValueError('Wrong FPGA device')
    ps = root.find(".//MODULE[@INSTANCE='sys_ps7']")
    windows = {m.get('INSTANCE'): (int(m.get('BASEVALUE'), 0), int(m.get('HIGHVALUE'), 0))
               for m in ps.findall('./MEMORYMAP/MEMRANGE')}
    for name, base in {**{k: v[0] for k, v in MEMORIES.items()}, **ADDRESSES}.items():
        if name not in windows or windows[name][0] != base:
            raise ValueError('Unexpected/missing Y3 address '+name)
    for name, (base, size) in MEMORIES.items():
        if windows[name][1]-base+1 != size:
            raise ValueError('Unexpected memory span '+name)
    spans = sorted((start, end, name) for name, (start, end) in windows.items())
    for left, right in zip(spans, spans[1:]):
        if left[1] >= right[0]:
            raise ValueError('Overlapping address spans '+left[2]+'/'+right[2])
    ports = {p.get('NAME'): p for p in root.findall('./EXTERNALPORTS/PORT')}
    # These are BD output directions. Top-level BCLK/LRCK have OBUFT enables;
    # MCLK/DACDAT remain driven. HWH alone cannot prove top-level tristates.
    audio_outputs = ('aud_mclk', 'aud_bclk', 'aud_lrc', 'aud_dacdat')
    if any(name not in ports or ports[name].get('DIR') != 'O' for name in audio_outputs):
        raise ValueError('Y3 audio pin direction mismatch')
    return data


def checked_v2_timing_policy(data, directory):
    """Preserve Z10 +1ns unless the explicit reviewed development policy applies.

    User authorized deferring the +1ns optimization target on 2026-11-03.
    A policy string alone cannot authorize an unreviewed or negative-slack image.
    """
    policy = data.get('deployment_policy')
    minimum_setup = 1.0
    if policy == 'development_nonnegative_v1':
        review_path = Path(directory)/'development_review.json'
        digest = hashlib.sha256(review_path.read_bytes()).hexdigest()
        if digest != data.get('development_review_sha256'):
            raise ValueError('Development review digest mismatch')
        review = json.loads(review_path.read_text())
        required = ('basic_timing', 'cdc', 'external_io', 'pins_and_voltages',
                    'build_inputs', 'route_and_drc')
        if (review.get('status') != 'PASS_DEVELOPMENT_REVIEW'
                or review.get('image') != 'sentinel_v2_100m'
                or any(review.get('checks', {}).get(k) is not True for k in required)
                or review.get('artifacts_sha256') != data.get('artifacts_sha256')):
            raise ValueError('Incomplete or mismatched development review')
        minimum_setup = 0.0
    elif policy not in (None, 'z10_margin_1ns'):
        raise ValueError('Unknown v2 deployment policy')
    for key, minimum in (('WNS_ns', minimum_setup), ('WHS_ns', 0.0)):
        value = data.get('final_timing', {}).get(key)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or value < minimum):
            raise ValueError('Z10 timing gate not satisfied: ' + key)


class VY3(V1):
    # Reuse the accepted processing/reset protocol, not the v1d-only image
    # constructor: Y3 has its own independently checked bit/HWH receipt.
    enable_processing = V1b.enable_processing
    reset_channelizer = V1d.reset_channelizer

    def __init__(self, bit, download=False, image='sentinel_y3'):
        checked_y3_bundle(bit, image=image)
        contracts = dict(CONTRACTS)
        contracts.update(cfar_core_0={'version': C.VERSION_VALUE},
                         lcd_engine={'version': LCD_VERSION})
        self.checked = SentinelOverlay(bit, download=download, contracts=contracts)
        self.overlay = self.checked.overlay
        for name, base in ADDRESSES.items():
            if name not in self.checked.ip_dict or int(self.checked.ip_dict[name]['phys_addr']) != base:
                raise RuntimeError('Unexpected Y3 register base: '+name)
        self.src_regs = self.checked.registers('src_mux_0')
        self.spec = self.checked.registers('spec_front_0')
        self.source = Source(self.src_regs, dsp_clk_hz=clock_hz_for_image(image))
        self.cfar = CfarX1(self.checked.registers('cfar_core_0'))
        self.perf = Performance(self.checked.registers('perf_mon_0'))
        self.lcd = X5LCD(self.checked.registers('lcd_engine'), make_mmio(0x42100000, 131072))
        self.capture = make_mmio(0x42010000, 8192)
        self.capture_ctrl = self.checked.registers('axi_capture_ctrl')
        self.x5_ctrl = self.checked.registers('x5_ctrl')
        self.x5_status = self.checked.registers('x5_status')
        self.channel_capture = ChannelCapture(self.x5_ctrl, self.checked.registers('x5_meta'),
            self.x5_status, self.overlay.axi_dma_replay, health=self.channel_health)
        self.audio = AudioControl(self.checked.registers('y3_audio_ctrl'),
            self.checked.registers('y3_audio_state'), self.checked.registers('y3_audio_counts'))
        from .audio_y3 import bind_audio_iic
        self.audio_iic = bind_audio_iic(self.overlay)

    def channel_health(self):
        status = self.perf.snapshot().status & 3
        status |= (self.cfar.mmio.read(C.STATUS) & 0xc) << 12
        status |= (self.lcd.registers.read(L.STATUS) & 0x1c) << 16
        return status
