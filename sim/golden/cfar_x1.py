"""X1 golden contract; v1 remains available for the accepted N3/N4 image.

Intervals are inclusive, masks are hard cluster boundaries, and equal-power
targets are ordered by ascending start bin. This model does not access hardware.
"""
from dataclasses import dataclass

import numpy as np

from .cfar import TARGET_DTYPE, U32_MAX, _power, cfar

VERSION = 0x43460002
MAX_MASKS = 16
MAX_TARGETS = 32


def _integer(value, name, low, high):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(name + ' must be an integer')
    value = int(value)
    if not low <= value <= high:
        raise ValueError(name + ' outside supported range')
    return value


def mask_bins(length, mask_table=(), dc_mask=-1):
    """Return union of <=16 explicit ranges and an optional automatic DC range.

    Entries may overlap or be unsorted. Neither masks nor clustering wrap from
    the last bin to bin zero; the CFAR reference windows still wrap as in v1.
    """
    length = _integer(length, 'length', 1, 2048)
    dc_mask = _integer(dc_mask, 'dc_mask', -1, 254)
    table = tuple(mask_table)
    if len(table) > MAX_MASKS:
        raise ValueError('At most 16 mask intervals are supported')
    blocked = np.zeros(length, dtype=bool)
    for interval in table:
        if not isinstance(interval, (tuple, list, np.ndarray)) or len(interval) != 2:
            raise ValueError('Each mask must contain start and stop')
        start = _integer(interval[0], 'mask start', 0, length - 1)
        stop = _integer(interval[1], 'mask stop', start, length - 1)
        blocked[start:stop + 1] = True
    if dc_mask >= 0:
        center = length // 2
        blocked[max(0, center - dc_mask):min(length, center + dc_mask + 1)] = True
    return blocked


@dataclass(frozen=True)
class ClusterResult:
    targets: np.ndarray
    raw_count: int
    filtered_count: int
    candidate_count: int
    hit_count: int
    overflow: bool

    @property
    def status_latch(self):
        """Successful golden frame: only the capacity-overflow bit may be set."""
        return int(self.overflow) << 4


def cluster_x1(hit, power, min_width_bins=2, merge_gap_bins=6,
               mask_table=(), dc_mask=-1, max_targets=MAX_TARGETS):
    """Filter completed clusters, then return strongest targets and full counts.

    Masked bins never participate, even inside a merged gap. Width includes
    bridged, unmasked gap bins. Peak/sum include those gaps, matching v1.
    Capacity overflow counts surviving candidates BEFORE top-N truncation.
    min_width_bins=0 disables width filtering for narrow-tone regressions.
    """
    x = _power(power)
    h = np.asarray(hit)
    if h.shape != x.shape or np.any((h != 0) & (h != 1)):
        raise ValueError('Hit/power dimensions or hit values invalid')
    width = _integer(min_width_bins, 'min_width_bins', 0, 2048)
    gap = _integer(merge_gap_bins, 'merge_gap_bins', 0, 255)
    limit = _integer(max_targets, 'max_targets', 1, MAX_TARGETS)
    blocked = mask_bins(len(x), mask_table, dc_mask)
    indices = np.flatnonzero(h.astype(bool) & ~blocked)
    groups = []
    if len(indices):
        start = previous = int(indices[0])
        for current in map(int, indices[1:]):
            if current - previous - 1 > gap or np.any(blocked[previous + 1:current]):
                groups.append((start, previous))
                start = current
            previous = current
        groups.append((start, previous))
    candidates = []
    for start, stop in groups:
        if stop - start + 1 < width:
            continue
        segment = x[start:stop + 1]
        peak = start + int(np.argmax(segment))
        candidates.append((start, stop, peak, 0, int(x[peak]),
                           min(int(segment.sum()), U32_MAX)))
    candidates.sort(key=lambda row: (-row[4], row[0]))
    overflow = len(candidates) > limit
    targets = np.empty(min(limit, len(candidates)), dtype=TARGET_DTYPE)
    for index, record in enumerate(candidates[:limit]):
        targets[index] = (*record[:3], int(overflow), *record[4:])
    return ClusterResult(targets=targets, raw_count=len(groups),
                         filtered_count=len(groups) - len(candidates),
                         candidate_count=len(candidates), hit_count=len(indices),
                         overflow=overflow)


def detect_x1(power, mode='CA', n=16, g=2, alpha_q88=1974,
              dc_mask=3, min_width_bins=2, merge_gap_bins=6, mask_table=()):
    """Return threshold, post-mask hits and clustered targets for one frame.

    Masks suppress CUT decisions; reference-window power is NOT removed or
    renormalized. The automatic DC range is also a hard clustering boundary.
    """
    table = tuple(mask_table)
    blocked = mask_bins(len(power), table, dc_mask)
    threshold, hit = cfar(power, mode=mode, n=n, g=g, alpha_q88=alpha_q88,
                          dc_mask=-1)
    hit[blocked] = 0
    result = cluster_x1(hit, power, min_width_bins=min_width_bins,
                        merge_gap_bins=merge_gap_bins, mask_table=table,
                        dc_mask=dc_mask)
    return threshold, hit, result
