"""Bounded CFAR target scheduler: newly observed first, then round robin.

Votes are per target, from at most five captures; model confidence remains an
uncalibrated score. Nothing in this module assumes that a peak is an FM station.
"""
from collections import Counter, deque
from dataclasses import dataclass, field
import math


@dataclass
class Track:
    key: int
    frequency_hz: float
    bandwidth_hz: float
    power: int
    first_seen: float
    last_seen: float
    last_attempt: float = -math.inf
    last_result: float = -math.inf
    votes: deque = field(default_factory=lambda: deque(maxlen=5))
    label: str = 'PENDING'
    confidence: float = 0.0
    display_latency_ms: float = None


class TargetTracker:
    def __init__(self, match_hz=15000, expiry_s=5, max_tracks=32):
        if match_hz <= 0 or expiry_s <= 0 or not 1 <= max_tracks <= 32:
            raise ValueError('Invalid tracking limits')
        self.match_hz, self.expiry_s, self.max_tracks = match_hz, expiry_s, max_tracks
        self.tracks = {}
        self.next_id = 0

    def update(self, targets, lo_hz, rate_hz, now):
        self.tracks = {k:t for k,t in self.tracks.items() if now-t.last_seen <= self.expiry_s}
        unmatched = set(self.tracks)
        additions = []
        for target in sorted(targets, key=lambda t:t.peak_power, reverse=True)[:self.max_tracks]:
            frequency = lo_hz + ((target.start+target.stop)*.5-1024)*rate_hz/2048
            bandwidth = (target.stop-target.start+1)*rate_hz/2048
            candidates = [self.tracks[k] for k in unmatched
                          if abs(self.tracks[k].frequency_hz-frequency) <= self.match_hz]
            if candidates:
                track = min(candidates, key=lambda t:abs(t.frequency_hz-frequency))
                unmatched.remove(track.key)
                track.frequency_hz, track.bandwidth_hz = frequency, bandwidth
                track.last_seen, track.power = now, target.peak_power
            else:
                additions.append((frequency, bandwidth, target.peak_power))
        # Finish matching before evicting: a later target may match an old ID.
        # Missing historical targets must not block newly observed ones at capacity.
        for frequency, bandwidth, power in additions:
            if len(self.tracks) >= self.max_tracks:
                if not unmatched:
                    break
                victim = min(unmatched, key=lambda k:self.tracks[k].last_seen)
                unmatched.remove(victim)
                del self.tracks[victim]
            key = self.next_id
            self.next_id += 1
            self.tracks[key] = Track(key, frequency, bandwidth, power, now, now)
        return self.visible(now)

    def visible(self, now):
        return sorted((t for t in self.tracks.values() if now-t.last_seen <= 1.5),
                      key=lambda t:(-t.power, t.key))

    def next(self, now):
        visible = self.visible(now)
        if not visible:
            return None
        # Newly seen tracks receive one attempt before revisiting any prior one.
        return min(visible, key=lambda t:(t.last_attempt != -math.inf, t.last_attempt, -t.power))

    def mark_attempt(self, key, now):
        self.tracks[key].last_attempt = now

    def record(self, key, prediction, now):
        track = self.tracks[key]
        label, score = prediction['label'], float(prediction['confidence'])
        if not isinstance(label, str) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid classifier result')
        track.votes.append((label, score))
        counts = Counter(name for name,_ in track.votes)
        # Tie: most recent tied label. Stable and independent of dict ordering.
        winners = {name for name,n in counts.items() if n == max(counts.values())}
        track.label = next(name for name,_ in reversed(track.votes) if name in winners)
        track.confidence = sum(v for name,v in track.votes if name == track.label)/counts[track.label]
        track.last_result = now
        return track
