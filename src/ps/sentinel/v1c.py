"""Independent X2 image binding; accepted v1/v1b bindings remain available."""
from .v1 import V1, Source, ADDRESSES, CONTRACTS
from .v1b import V1b
from .overlay import SentinelOverlay
from .drivers.cfar_x1 import CfarX1
from .drivers.perf import Performance
from .drivers.regs import cfar_x1 as C
from .drivers.stream_x2 import StreamStatistics, VERSION_VALUE
from .regs import stream_x2 as R
from .lcd_direct import DirectLCD
from .mmio import make_mmio


class V1c(V1):
    enable_processing = V1b.enable_processing

    def __init__(self, bit, download=False):
        contracts = dict(CONTRACTS)
        contracts.update(cfar_core_0={'version': C.VERSION_VALUE},
                         stream_stats_0={'version': VERSION_VALUE})
        self.checked = SentinelOverlay(bit, download=download, contracts=contracts)
        self.overlay = self.checked.overlay
        addresses = dict(ADDRESSES, stream_stats_0=R.BASE)
        for name, base in addresses.items():
            if name not in self.checked.ip_dict or int(self.checked.ip_dict[name]['phys_addr']) != base:
                raise RuntimeError('Unexpected v1c address: ' + name)
        # SentinelOverlay checks family; these stricter clients require the
        # complete version word for the independently evolved X1/X2 cores.
        self.src_regs = self.checked.registers('src_mux_0')
        self.spec = self.checked.registers('spec_front_0')
        self.source = Source(self.src_regs)
        self.cfar = CfarX1(self.checked.registers('cfar_core_0'))
        self.stream = StreamStatistics(self.checked.registers('stream_stats_0'))
        self.perf = Performance(self.checked.registers('perf_mon_0'))
        self.lcd = DirectLCD(self.checked.registers('lcd_engine'), make_mmio(0x42000000, 32768))
        self.capture = make_mmio(0x42010000, 8192)
        self.capture_ctrl = self.checked.registers('axi_capture_ctrl')
