"""100 MHz candidate overlay binding; requires a separate v2 acceptance receipt.

No hardware is opened on import. VY3 retains the legacy 150 MHz default.
"""
import time

from .v_y3 import VY3


class V2(VY3):
    def __init__(self, bit, download=False):
        super().__init__(bit, download=download, image='sentinel_v2_100m')

    def prepare_receive(self):
        """Clear initialization-only ADC FIFO faults before starting a session.

        AD9361 calibration can clock RX faster than the 100 MHz consumer.
        PERF.clear alone cannot clear the ADC-domain sticky latch. Pulse only
        AXI ADC core reset (RSTN bit 0), keeping MMCM reset released (bit 1).
        Never call during acquisition: in-session faults must still abort.
        """
        if self.src_regs.read(0) & 1:
            raise RuntimeError('Stop source before resetting the RX startup epoch')
        adc = self.checked.registers('axi_ad9361')
        saved = adc.read(0x40)
        if saved != 3:
            raise RuntimeError('Unexpected AXI ADC reset state before RX startup')
        before = self.perf.snapshot().__dict__
        try:
            adc.write(0x40, 2)
            if adc.read(0x40) != 2:
                raise RuntimeError('AXI ADC core reset assertion failed')
            time.sleep(.01)
        finally:
            adc.write(0x40, saved)
        time.sleep(.01)
        if adc.read(0x40) != saved or not adc.read(0x5c) & 1:
            raise RuntimeError('AXI ADC failed to resume after startup reset')
        self.perf.clear()
        time.sleep(.01)
        after = self.perf.snapshot().__dict__
        if after['status'] & 3:
            raise RuntimeError('RX fault persists after startup reset: ' + str(after))
        return dict(scope='Before acquisition only; no in-session fault masking',
                    reset_register_before=saved, reset_register_after=adc.read(0x40),
                    perf_before=before, perf_after=after)
