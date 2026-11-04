"""Bounded F4 evidence storage and strict long-run criteria, hardware-free.

The active monitor integration is separate. These helpers alone do not run
or certify a one-hour board test. RSS measures this process, not Linux cache.
"""
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path

from .artifacts import atomic_write


def resident_bytes(status_path='/proc/self/status'):
    """Read current resident size, not the historical maximum from getrusage."""
    for line in Path(status_path).read_text().splitlines():
        parts = line.split()
        if parts and parts[0] == 'VmRSS:':
            if len(parts) != 3 or parts[2] != 'kB' or int(parts[1]) <= 0:
                raise ValueError('Invalid Linux VmRSS')
            return int(parts[1]) * 1024
    raise ValueError('Linux process RSS unavailable')


class EvidenceStream:
    """Append-only JSONL; bounded recent records, monotonic independent index.

    Final SHA256 describes the complete closed file, including a trailing
    newline. No silently truncated/dropped telemetry is allowed. Call close
    from the acquisition finally block even on an early stop or failure.
    """
    def __init__(self, path, recent_limit=32):
        if type(recent_limit) is not int or recent_limit < 1:
            raise ValueError('Positive bounded record limit required')
        self.path = Path(path)
        self.recent = deque(maxlen=recent_limit)
        self.count = 0
        self.digest = hashlib.sha256()
        self.stream = self.path.open('xb')
        self.closed = False

    def append(self, record):
        if self.closed:
            raise ValueError('Evidence stream is closed')
        # Serialize before any write: NaN/Infinity cannot produce a partial line.
        data = (json.dumps(record, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
        self.stream.write(data)
        self.stream.flush()
        self.digest.update(data)
        self.count += 1
        # Decouple recent records from caller mutation without unbounded storage.
        self.recent.append(json.loads(data))

    def close(self):
        if not self.closed:
            try:
                self.stream.flush()
                os.fsync(self.stream.fileno())
            finally:
                self.stream.close()
                self.closed = True
            data = (self.digest.hexdigest() + '  ' + self.path.name + '\n').encode('ascii')
            atomic_write(str(self.path) + '.sha256', lambda stream: stream.write(data))
        return dict(filename=self.path.name, count=self.count, sha256=self.digest.hexdigest())


class StabilityStats:
    """Constant-memory full-run telemetry extrema; no warm-up samples excluded.

    Feed baseline at elapsed=0 after the normal startup quality check and
    before the timed loop. Keep all later samples. Missing/invalid values,
    >10 s telemetry gaps, early exits and absent inference fail acceptance.
    Memory threshold is 10,000,000 bytes (strictly less than 10 MB).
    """
    REQUIRED_SECONDS = 3600
    MAX_RSS_GROWTH = 10000000

    def __init__(self):
        self.count = 0
        self.first = self.last = None
        self.baseline_rss = self.peak_rss = None
        self.max_temperature = self.min_fps = None
        self.faults = 0
        self.invalid = 0
        self.max_gap = 0.0

    def observe(self, sample):
        fields = ('elapsed_s', 'rss_bytes', 'temperature_c', 'display_fps', 'processing_status')
        values = [sample.get(k) for k in fields]
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or sample['rss_bytes'] <= 0 or sample['elapsed_s'] < 0
                or sample['display_fps'] <= 0 or not 30 <= sample['temperature_c']
                or type(sample['processing_status']) is not int
                or sample['processing_status'] < 0):
            self.invalid += 1
            raise ValueError('Missing or invalid stability telemetry')
        now = sample['elapsed_s']
        if self.last is not None and now <= self.last:
            self.invalid += 1
            raise ValueError('Telemetry time must increase')
        if self.first is None:
            self.first = now
            self.baseline_rss = sample['rss_bytes']
            self.peak_rss = sample['rss_bytes']
            self.max_temperature = sample['temperature_c']
            self.min_fps = sample['display_fps']
        else:
            self.max_gap = max(self.max_gap, now - self.last)
        self.last = now
        self.count += 1
        self.peak_rss = max(self.peak_rss, sample['rss_bytes'])
        self.max_temperature = max(self.max_temperature, sample['temperature_c'])
        self.min_fps = min(self.min_fps, sample['display_fps'])
        self.faults += int(sample['processing_status'] != 0)

    def finish(self, elapsed_s, completed, inference_count, noise_events):
        if (type(elapsed_s) not in (int, float) or not math.isfinite(elapsed_s) or elapsed_s < 0
                or type(inference_count) is not int or inference_count < 0
                or type(noise_events) is not int or noise_events < 0 or type(completed) is not bool):
            raise ValueError('Invalid final counters')
        growth = None if self.peak_rss is None else self.peak_rss - self.baseline_rss
        coverage = (self.count >= 2 and self.first <= 1 and self.max_gap <= 10
                    and self.last >= self.REQUIRED_SECONDS - 10
                    and 0 <= elapsed_s - self.last <= 10)
        checks = dict(full_hour=elapsed_s >= self.REQUIRED_SECONDS,
                      completed_normally=completed, telemetry_coverage=bool(coverage),
                      valid_telemetry=self.invalid == 0,
                      zero_processing_faults=self.count > 0 and self.faults == 0,
                      memory_growth_under_10MB=growth is not None and growth < self.MAX_RSS_GROWTH,
                      temperature_below_85C=self.max_temperature is not None and self.max_temperature < 85,
                      live_inference_present=inference_count > 0)
        return dict(status='PASS' if all(checks.values()) else 'FAIL', checks=checks,
                    elapsed_s=elapsed_s, telemetry_samples=self.count,
                    peak_minus_baseline_rss_bytes=growth, memory_limit_bytes=self.MAX_RSS_GROWTH,
                    max_temperature_c=self.max_temperature, min_display_fps=self.min_fps,
                    max_telemetry_gap_s=self.max_gap, fault_samples=self.faults,
                    inference_count=inference_count, noise_event_count=noise_events,
                    scope='Timed monitor process; startup quality check precedes baseline; not a PL bandwidth test')
