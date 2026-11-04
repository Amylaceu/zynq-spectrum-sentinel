"""X2 RX bandwidth readback; uses a separate library and inherited TX guard."""
import ctypes as ct
from pathlib import Path

from .ad9361 import AD9361


class AD9361X2(AD9361):
    def __init__(self, lib=None):
        if lib is None:
            lib = Path(__file__).resolve().parents[2] / 'libad9361_pynq/libad9361_x2.so'
        super().__init__(lib=lib)
        self.lib.z20_x2_get_rx_bandwidth.argtypes = [ct.POINTER(ct.c_uint32)]
        self.lib.z20_x2_get_rx_bandwidth.restype = ct.c_int

    @property
    def bandwidth(self):
        value = ct.c_uint32()
        self._check(self.lib.z20_x2_get_rx_bandwidth(ct.byref(value)), 'RX bandwidth readback')
        return value.value
