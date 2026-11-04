"""X5 binding: accepted v1b processing plus PL capture and LCD version 5.

This module performs no hardware operations until VZ2 is constructed explicitly.
Use only the routed and audited sentinel_z2 bit/HWH pair, never v1c.
"""
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from .v1 import V1, Source, ADDRESSES, CONTRACTS
from .v1b import V1b
from .overlay import SentinelOverlay
from .drivers.cfar_x1 import CfarX1
from .drivers.perf import Performance
from .drivers.regs import cfar_x1 as C, lcd_ctrl as L, src_ctrl as S
from .lcd_z2 import Z2LCD, VERSION
from .capture_x5 import ChannelCapture
from .mmio import make_mmio


MEMORY_WINDOWS = (('axi_lcd_ui', 0x42100000, 131072),
                  ('axi_power_capture', 0x42010000, 8192))


def checked_memory_windows(bit):
    """Verify accepted bit/HWH bytes and MEMORY ranges before mapping BRAM.

    PYNQ 2.7 omits BRAM from ip_dict. Absence there must not bypass HWH checks.
    Hashes provide artifact integrity, not an author identity/signature.
    """
    bit = Path(bit)
    manifest = bit.parent/'acceptance.json'
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(manifest) != Path(str(manifest)+'.sha256').read_text().split()[0]:
        raise ValueError('Implementation acceptance digest mismatch')
    accepted = json.loads(manifest.read_text())
    if accepted.get('status') != 'PASS' or accepted.get('image') != 'sentinel_z2':
        raise ValueError('Require accepted sentinel_z2 memory map')
    for path in (bit, bit.with_suffix('.hwh')):
        if digest(path) != accepted['artifacts_sha256'].get(path.name):
            raise ValueError('Accepted artifact mismatch: '+path.name)
    tree = ET.parse(str(bit.with_suffix('.hwh')))
    for name, base, size in MEMORY_WINDOWS:
        ranges = {(int(node.attrib['BASEVALUE'], 0), int(node.attrib['HIGHVALUE'], 0))
                  for node in tree.iter('MEMRANGE')
                  if node.get('INSTANCE') == name and node.get('MEMTYPE') == 'MEMORY'}
        if ranges != {(base, base+size-1)}:
            raise RuntimeError('Unexpected Z2 HWH memory window: '+name)


class VZ2(V1):
    enable_processing = V1b.enable_processing

    def __init__(self, bit, download=False):
        checked_memory_windows(bit)
        contracts = dict(CONTRACTS)
        contracts.update(cfar_core_0={'version': C.VERSION_VALUE},
                         lcd_engine={'version': VERSION})
        self.checked = SentinelOverlay(bit, download=download, contracts=contracts)
        self.overlay = self.checked.overlay
        addresses = dict(ADDRESSES, x5_ctrl=0x41230000, x5_meta=0x41240000,
                         x5_status=0x41250000)
        for name, base in addresses.items():
            if name not in self.checked.ip_dict or int(self.checked.ip_dict[name]['phys_addr']) != base:
                raise RuntimeError('Unexpected Z2 address: '+name)
        for name, base, size in MEMORY_WINDOWS:
            # Cross-check optional PYNQ metadata against the verified HWH.
            info = self.checked.ip_dict.get(name)
            if info is not None and (int(info.get('phys_addr', -1)) != base
                                     or int(info.get('addr_range', 0)) != size):
                raise RuntimeError('Unexpected Z2 memory window: '+name)
        self.src_regs = self.checked.registers('src_mux_0')
        self.spec = self.checked.registers('spec_front_0')
        self.source = Source(self.src_regs)
        self.cfar = CfarX1(self.checked.registers('cfar_core_0'))
        self.perf = Performance(self.checked.registers('perf_mon_0'))
        self.lcd = Z2LCD(self.checked.registers('lcd_engine'), make_mmio(0x42100000, 131072))
        self.capture = make_mmio(0x42010000, 8192)
        self.capture_ctrl = self.checked.registers('axi_capture_ctrl')
        self.x5_ctrl = self.checked.registers('x5_ctrl')
        self.x5_status = self.checked.registers('x5_status')
        self.channel_capture = ChannelCapture(self.x5_ctrl, self.checked.registers('x5_meta'),
                                              self.x5_status, self.overlay.axi_dma_replay,
                                              health=self.channel_health)

    def reset_channelizer(self):
        if self.src_regs.read(S.CTRL) & 1:
            raise RuntimeError('Stop source before clearing PFB history')
        if self.channel_capture.failed:
            raise RuntimeError('DMA failure requires full PL reset; local PFB reset is insufficient')
        self.x5_ctrl.write(0, 4)
        time.sleep(.001)  # >16 DSP clocks, including official XFFT reset.
        self.x5_ctrl.write(8, 0)
        self.x5_ctrl.write(0, 0)
        time.sleep(.001)
        if self.x5_status.read(0):
            raise RuntimeError('PFB/capture reset readback failed')

    def channel_health(self):
        status = self.perf.snapshot().status & 3
        # PERF bit1 aggregates src/spec/ADC sticky errors through event_bridge;
        # those baseline IPs do not expose a separate STATUS register.
        status |= (self.cfar.mmio.read(C.STATUS) & 0xc) << 12
        status |= (self.lcd.registers.read(L.STATUS) & 0x1c) << 16
        return status
