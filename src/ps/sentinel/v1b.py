"""Explicit v1b binding; v1 remains available for accepted baseline tests."""
from .v1 import V1, Source, ADDRESSES, CONTRACTS, wait_until
from .overlay import SentinelOverlay
from .drivers.cfar_x1 import CfarX1
from .drivers.perf import Performance
from .drivers.regs import spec_ctrl as F, cfar_x1 as C
from .lcd_direct import DirectLCD
from .mmio import make_mmio


class V1b(V1):
    def __init__(self, bit, download=False):
        contracts = dict(CONTRACTS)
        contracts['cfar_core_0'] = {'version': C.VERSION_VALUE}
        self.checked = SentinelOverlay(bit, download=download, contracts=contracts)
        self.overlay = self.checked.overlay
        for name, base in ADDRESSES.items():
            if name not in self.checked.ip_dict or int(self.checked.ip_dict[name]['phys_addr']) != base:
                raise RuntimeError('Unexpected v1b address: '+name)
        self.src_regs = self.checked.registers('src_mux_0')
        self.spec = self.checked.registers('spec_front_0')
        self.source = Source(self.src_regs)
        self.cfar = CfarX1(self.checked.registers('cfar_core_0'))
        self.perf = Performance(self.checked.registers('perf_mon_0'))
        self.lcd = DirectLCD(self.checked.registers('lcd_engine'), make_mmio(0x42000000,32768))
        self.capture = make_mmio(0x42010000,8192)
        self.capture_ctrl = self.checked.registers('axi_capture_ctrl')

    def enable_processing(self, average_shift=3, **cfar_options):
        if type(average_shift) is not int or not 0 <= average_shift <= 15:
            raise ValueError('Invalid average shift')
        wait_until(lambda: not self.cfar.mmio.read(C.STATUS) & 3,
                   timeout=2, label='X1 occupancy initialization')
        self.spec.write(F.AVG_SHIFT, average_shift)
        self.spec.write(F.DISP_DECIM, 1)
        self.cfar.configure(**cfar_options)
        self.spec.write(F.CTRL, 1)
