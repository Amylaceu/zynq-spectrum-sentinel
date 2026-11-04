"""X2 session with explicit RF bandwidth and the accepted ownership protocol."""
import os

from .runtime_v1 import Session
from ..rf.ad9361_x2 import AD9361X2
from ..v1c import V1c

RATES = {7680000: 6000000, 15360000: 12000000,
         24576000: 20000000, 30720000: 25000000}


class SessionX2(Session):
    def __init__(self, bit, source='rf', load=True, lo=98000000, rate=7680000):
        if rate not in RATES:
            raise ValueError('Unsupported X2 measurement rate')
        super().__init__(bit, source, load, lo, rate, hw_factory=V1c)
        self.bandwidth = RATES[rate]

    def __enter__(self):
        import fcntl
        os.environ['XILINX_XRT'] = '/usr'
        self.lock = open('/run/lock/zss_ad9361.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._owns_hardware = True
            self.hw = self.hw_factory(self.bit, download=self.load)
            self.rf_gpio = self.hw.checked.registers('axi_ad9361_gpio')
            self._hold_rf_in_reset()
            self.hw.source.stop()
            if self.source == 'rf':
                # The C library owns the same flock throughout RF operation.
                self._owns_hardware = False
                self.rf_gpio = None
                fcntl.flock(self.lock, fcntl.LOCK_UN)
                self.lock.close()
                self.lock = None
                self.radio = AD9361X2().open(rate=self.rate, rx_lo=self.lo,
                                             bandwidth=self.bandwidth)
                self._owns_hardware = True
                if (self.radio.rate != self.rate or abs(self.radio.rx_lo-self.lo) > 5
                        or self.radio.bandwidth != self.bandwidth
                        or self.radio.tx_atten != (89.75, 89.75)):
                    raise RuntimeError('X2 muted RF configuration readback mismatch')
                adc = self.hw.checked.registers('axi_ad9361')
                for i in range(4):
                    adc.write(0x400 + 64*i, 0x51)
                    adc.write(0x418 + 64*i, 0)
                if any(adc.read(0x400 + 64*i) != 0x51 for i in range(4)):
                    raise RuntimeError('ADC format readback mismatch')
            return self
        except BaseException:
            self.close()
            raise
