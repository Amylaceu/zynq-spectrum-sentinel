"""Bounded display state and detection-based occupancy; no RF assumptions."""
from collections import Counter, deque
import time

import numpy as np


class Model:
    def __init__(self, occupancy_seconds=10):
        self.frequency = np.arange(1024, dtype=float)
        self.power = np.zeros(1024)
        self.peak = np.full(1024, -327.68)
        self.waterfall = np.full((300, 1024), -327.68, dtype=np.float32)
        self.iq = np.empty(0, dtype=np.complex64)
        self.targets = []
        self.events = deque(maxlen=2000)
        self.telemetry = deque(maxlen=120)
        self.histogram = Counter()
        self.confusion = Counter()
        self.classifications = {}
        self.demo = {}
        self.hello = {}
        self.amc_history = deque(maxlen=256)
        self.iq_track = None
        self.audio = {}
        self.audio_pcm = np.empty(0, dtype='<i2')
        self.build_info = {}
        self.window = occupancy_seconds
        self.occupancy = deque(maxlen=4096)
        self.spectrum_count = 0
        self.lo = None

    def apply(self, header, payload=b'', observed=None):
        # Use source time for identical occupancy/telemetry windows at 1x and 2x.
        now = header.get('t_mono', time.monotonic() if observed is None else observed)
        kind = header['type']
        if kind == 'hello':
            self.hello = dict(header)
        elif kind == 'spectrum':
            if len(payload) != 2048:
                raise ValueError('Expected 1024 int16 spectrum bins')
            if self.lo != header['lo_hz']:
                self.peak[:] = -327.68
                self.waterfall[:] = -327.68
                self.occupancy.clear()
                self.lo = header['lo_hz']
            self.frequency = header['frequency_start_hz']+np.arange(1024)*header['bin_spacing_hz']
            self.power = np.frombuffer(payload, dtype='<i2').astype(float)/100
            self.peak = np.maximum(self.peak, self.power)
            self.waterfall[1:] = self.waterfall[:-1]
            self.waterfall[0] = self.power
            self.spectrum_count += 1
        elif kind == 'detections':
            self.targets = list(header['targets'])[:32]
            mask = np.zeros(1024, dtype=bool)
            for target in self.targets:
                mask |= np.abs(self.frequency-target['frequency_hz']) <= max(
                    target['bandwidth_hz']/2, 1875)
            self.occupancy.append((now, mask))
            while self.occupancy and now-self.occupancy[0][0] > self.window:
                self.occupancy.popleft()
        elif kind == 'iq':
            if len(payload) != 4096:
                raise ValueError('Expected 512 complex64 IQ samples')
            self.iq = np.frombuffer(payload, dtype='<c8').copy()
            self.iq_track = header.get('target_key')
        elif kind == 'amc':
            self.amc_history.append(dict(header))
            label = header['prediction']
            self.histogram[label] += 1
            # Truth must belong to this exact capture, never to a previous segment.
            if header.get('transmitted') is not None:
                self.confusion[(header['transmitted'], label)] += 1
            self.classifications[header['track']] = dict(header)
            if len(self.classifications) > 128:
                del self.classifications[next(iter(self.classifications))]
        elif kind == 'event':
            self.events.append(dict(header))
        elif kind == 'telemetry':
            self.telemetry.append((now, dict(header)))
            while self.telemetry and now-self.telemetry[0][0] > 60:
                self.telemetry.popleft()
        elif kind == 'demo':
            self.demo = dict(header)
        elif kind == 'audio':
            if len(payload) % 2 or len(payload) > 192000:
                raise ValueError('Invalid bounded int16 PCM payload')
            self.audio = dict(header)
            self.audio_pcm = np.frombuffer(payload, dtype='<i2').copy()

    def occupancy_ratio(self):
        if not self.occupancy:
            return np.zeros(1024)
        return np.mean([mask for _,mask in self.occupancy], axis=0)
