"""CFAR MMIO contract; no RF or FPGA programming side effects."""
from dataclasses import dataclass
import struct
from .regs import cfar_ctrl as R


@dataclass(frozen=True)
class Target:
    start: int
    stop: int
    peak_bin: int
    flags: int
    peak_power: int
    sum_power: int


class Cfar:
    def __init__(self, mmio):
        self.mmio = mmio
        if mmio.read(R.VERSION) != 0x43460001:
            raise ValueError('CFAR IP version mismatch')

    def configure(self, mode='CA', n=16, guard=2, alpha=1974, dc_mask=3, gap=2, enable=True):
        modes = {'CA': 0, 'GO': 1, 'SO': 2}
        if (mode not in modes or not isinstance(n, int) or n < 1 or n > 64 or n & (n-1)
                or not isinstance(guard, int) or not 0 <= guard <= 31
                or not isinstance(alpha, int) or not 0 <= alpha <= 65535
                or not isinstance(dc_mask, int) or not -1 <= dc_mask <= 254
                or not isinstance(gap, int) or not 0 <= gap <= 255):
            raise ValueError('Unsupported CFAR configuration')
        # Stop upstream spec_front and drain first: changing configuration is not an atomic multi-register operation.
        if self.mmio.read(R.STATUS) & 1:
            raise RuntimeError('Stop and drain upstream spectrum frames before configuring CFAR')
        self.mmio.write(R.CTRL, 0)
        for register, value in ((R.N_SHIFT, n.bit_length()-1), (R.GUARD, guard),
                                (R.ALPHA, alpha), (R.DC_MASK, dc_mask & 255), (R.GAP, gap)):
            self.mmio.write(register, value)
        self.mmio.write(R.CTRL, (modes[mode] << 1) | int(bool(enable)))

    def targets(self, retries=3):
        if not isinstance(retries, int) or retries < 1:
            raise ValueError('retries must be positive')
        for _ in range(retries):
            before = self.mmio.read(R.FRAME_COUNT)
            count = self.mmio.read(R.TARGET_COUNT)
            if not 0 <= count <= 32:
                raise ValueError('Corrupt target count')
            if hasattr(self.mmio,'array'):
                # Copy the entire window before a second sequence read; Python per-word calls
                # can span several lists at continuous FFT rates.
                import numpy as np
                first=R.TARGETS//4;last=first+4*count
                if len(self.mmio.array)<last:raise ValueError('Target window mapping is too short')
                raw=np.asarray(self.mmio.array[first:last],dtype='<u4').copy().tobytes()
            else:
                raw = b''.join(struct.pack('<I', self.mmio.read(R.TARGETS+16*i+4*j))
                               for i in range(count) for j in range(4))
            if before != self.mmio.read(R.FRAME_COUNT):
                continue
            result = [Target(*struct.unpack_from('<HHHHII', raw, 16*i)) for i in range(count)]
            if any(not 0 <= t.start <= t.peak_bin <= t.stop < 2048 for t in result):
                raise ValueError('Corrupt target interval')
            return before, result
        raise RuntimeError('CFAR list changed during read; stop upstream or retry later')

    def occupancy(self):
        if self.mmio.read(R.CTRL) & 1 or self.mmio.read(R.STATUS) & 3:
            raise RuntimeError('Disable and drain CFAR before reading coherent occupancy')
        frames = self.mmio.read(R.OCC_FRAMES)
        counters = [self.mmio.read(R.OCCUPANCY+4*i) & 65535 for i in range(2048)]
        return frames, counters
