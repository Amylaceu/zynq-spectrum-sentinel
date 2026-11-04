"""Exclusive v1 image ownership and muted RF cleanup."""
import os,time
from pathlib import Path
from ..v1 import V1
from ..rf import AD9361

class Session:
    def __init__(self,bit,source='test',load=False,lo=98000000,rate=3840000,hw_factory=None):
        self.bit,self.source,self.load,self.lo,self.rate=bit,source,load,lo,rate
        self.hw_factory=V1 if hw_factory is None else hw_factory
        self.lock=None;self.radio=None;self.hw=None;self.rf_gpio=None
        self._owns_hardware=False
    def _hold_rf_in_reset(self):
        if self.rf_gpio is None:return
        # Channel 1 is synthesized C_ALL_OUTPUTS=1. GPIO_DATA reads the
        # output latch; GPIO_TRI reads constant ones and is not a direction
        # readback in this configuration (Vivado AXI GPIO v2.0).
        self.rf_gpio.write(0,0)
        if self.rf_gpio.read(0)!=0:
            raise RuntimeError('AD9361 GPIO reset readback mismatch')
    def __enter__(self):
        import fcntl
        os.environ['XILINX_XRT']='/usr'
        self.lock=open('/run/lock/zss_ad9361.lock','a')
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._owns_hardware=True
            self.hw=self.hw_factory(self.bit,download=self.load)
            if not self.hw.overlay.is_loaded():raise RuntimeError('Requested v1 overlay is not loaded')
            self.rf_gpio=self.hw.checked.registers('axi_ad9361_gpio')
            self._hold_rf_in_reset()
            if self.source=='rf':
                # The C driver takes its own flock. Do not access PL during
                # this handoff, or reset RF after that driver releases its lock.
                self._owns_hardware=False
                self.rf_gpio=None
                fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None
                self.radio=AD9361().open(rate=int(self.rate),rx_lo=int(self.lo),bandwidth=min(1500000,int(self.rate)))
                self._owns_hardware=True
                if self.radio.tx_atten!=(89.75,89.75):raise RuntimeError('TX must remain muted')
                adc=self.hw.checked.registers('axi_ad9361')
                for i in range(4):
                    adc.write(0x400+64*i,0x51);adc.write(0x418+64*i,0)
                if any(adc.read(0x400+64*i)!=0x51 for i in range(4)):raise RuntimeError('ADC format readback mismatch')
                prepare_receive = getattr(self.hw, 'prepare_receive', None)
                if prepare_receive is not None:
                    self.receive_startup = prepare_receive()
            return self
        except BaseException:
            self.close();raise
    def close(self):
        try:
            if self._owns_hardware and self.hw is not None:self.hw.source.stop()
        finally:
            try:
                if self.radio is not None:self.radio.close();self.radio=None
            finally:
                try:
                    if self._owns_hardware:self._hold_rf_in_reset()
                finally:
                    self._owns_hardware=False
                    if self.lock is not None:
                        import fcntl
                        fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None
    def __exit__(self,*args):self.close()
