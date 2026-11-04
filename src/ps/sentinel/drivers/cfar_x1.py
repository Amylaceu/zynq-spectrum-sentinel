"""X1-only MMIO driver: rejects the accepted v1 image before any writes.

Not wired into the live application until the matching RTL/bitstream passes.
Snapshot consistency relies on atomic hardware publication of the X1 contract.
"""
from dataclasses import dataclass
import struct

from .cfar import Target
from .regs import cfar_x1 as R


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid ' + name)
    return value


@dataclass(frozen=True)
class CfarSnapshot:
    sequence: int
    status_latch: int
    hit_count: int
    raw_count: int
    filtered_count: int
    candidate_count: int
    targets: tuple

    @property
    def list_overflow(self):
        return bool(self.status_latch & 0x10)


class CfarX1:
    def __init__(self, mmio):
        self.mmio = mmio
        if mmio.read(R.VERSION) != R.VERSION_VALUE:
            raise ValueError('X1 CFAR IP version mismatch; do not use with sentinel_v1')

    def configure(self, mode='CA', n=16, guard=2, alpha=1974, dc_mask=3,
                  min_width_bins=2, merge_gap_bins=6, mask_table=(), enable=True):
        modes = {'CA': 0, 'GO': 1, 'SO': 2}
        if mode not in modes:
            raise ValueError('Invalid mode')
        n = _integer(n, 'n', 1, 64)
        if n & (n - 1):
            raise ValueError('n must be a power of two')
        guard = _integer(guard, 'guard', 0, 31)
        alpha = _integer(alpha, 'alpha', 0, 65535)
        dc_mask = _integer(dc_mask, 'dc_mask', -1, 254)
        width = _integer(min_width_bins, 'min_width_bins', 0, 2048)
        gap = _integer(merge_gap_bins, 'merge_gap_bins', 0, 255)
        table = tuple(mask_table)
        if len(table) > 16:
            raise ValueError('At most 16 mask intervals')
        words = []
        for pair in table:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError('Each mask needs start and stop')
            start = _integer(pair[0], 'mask start', 0, 2047)
            stop = _integer(pair[1], 'mask stop', start, 2047)
            words.append(start | (stop << 16))
        if self.mmio.read(R.STATUS) & 3:
            raise RuntimeError('Stop and drain upstream and occupancy clearing before configuring')
        self.mmio.write(R.CTRL, 0)
        for offset, value in ((R.N_SHIFT, n.bit_length() - 1), (R.GUARD, guard),
                              (R.ALPHA, alpha), (R.DC_MASK, dc_mask & 255),
                              (R.MIN_WIDTH, width), (R.MERGE_GAP, gap)):
            self.mmio.write(offset, value)
        # Erase unused slots while disabled, then publish count before enabling.
        for index in range(16):
            self.mmio.write(R.MASK + index * 4, words[index] if index < len(words) else 0)
        self.mmio.write(R.MASK_COUNT, len(words))
        self.mmio.write(R.CTRL, (modes[mode] << 1) | int(bool(enable)))

    def snapshot(self, retries=3):
        _integer(retries, 'retries', 1, 100)
        for _ in range(retries):
            before = self.mmio.read(R.FRAME_COUNT)
            count = self.mmio.read(R.TARGET_COUNT)
            status = self.mmio.read(R.STATUS_LATCH)
            hits = self.mmio.read(R.HIT_COUNT)
            raw_count = self.mmio.read(R.RAW_COUNT)
            filtered = self.mmio.read(R.FILTERED_COUNT)
            candidates = self.mmio.read(R.CANDIDATE_COUNT)
            if not 0 <= count <= 32:
                if before != self.mmio.read(R.FRAME_COUNT):
                    continue
                raise ValueError('Corrupt X1 target count')
            if hasattr(self.mmio, 'array'):
                import numpy as np
                first, last = R.TARGETS // 4, R.TARGETS // 4 + count * 4
                if len(self.mmio.array) < last:
                    raise ValueError('Target window mapping too short')
                data = np.asarray(self.mmio.array[first:last], dtype='<u4').copy().tobytes()
            else:
                data = b''.join(struct.pack('<I', self.mmio.read(R.TARGETS + index * 4))
                                for index in range(count * 4))
            if before != self.mmio.read(R.FRAME_COUNT):
                continue
            targets = tuple(Target(*struct.unpack_from('<HHHHII', data, index * 16))
                            for index in range(count))
            overflow = bool(status & 0x10)
            if (not 0 <= hits <= 2048 or not 0 <= candidates <= raw_count <= 2048
                    or filtered != raw_count - candidates or count != min(candidates, 32)
                    or overflow != (candidates > 32) or status & ~0x1c):
                raise ValueError('Inconsistent X1 snapshot counters/status')
            if any(not 0 <= t.start <= t.peak_bin <= t.stop < 2048
                   or t.flags != int(overflow) or t.sum_power < t.peak_power for t in targets):
                raise ValueError('Corrupt X1 target record')
            order = [(-t.peak_power, t.start) for t in targets]
            if order != sorted(order):
                raise ValueError('X1 targets not sorted by power/start bin')
            return CfarSnapshot(before, status, hits, raw_count, filtered, candidates, targets)
        raise RuntimeError('X1 snapshot changed during read; retry later')

    def targets(self, retries=3):
        """Compatibility for finite replay tests; telemetry uses full snapshot."""
        value = self.snapshot(retries)
        return value.sequence, list(value.targets)
