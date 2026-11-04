"""Bounded, timestamped UI events. No RF or hardware access on import."""
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

from .lcd_x5 import displayed_label


@dataclass(frozen=True)
class Event:
    timestamp_utc: str
    kind: str
    text: str


class EventLog:
    def __init__(self, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.events = deque(maxlen=5)
        self.labels = OrderedDict()

    def add(self, kind, text):
        if kind not in ('NEW', 'AMC', 'ALARM', 'MODE'):
            raise ValueError('Unknown event kind')
        stamp = self.clock()
        if stamp.tzinfo is None:
            raise ValueError('Event clock must be timezone aware')
        clean = ''.join(c if 32 <= ord(c) <= 126 else '?' for c in str(text))[:40]
        item = Event(stamp.astimezone(timezone.utc).strftime('%H:%M:%SZ'), kind, clean)
        self.events.append(item)
        return item

    def observe(self, tracks):
        for track in tracks:
            label = displayed_label(track)
            if track.key not in self.labels:
                self.add('NEW', '%.3fM %s' % (track.frequency_hz/1e6, label))
            elif self.labels[track.key] != label:
                self.add('AMC', '%.3fM %s>%s' %
                         (track.frequency_hz/1e6, self.labels[track.key], label))
            self.labels[track.key] = label
            self.labels.move_to_end(track.key)
            while len(self.labels) > 512:
                self.labels.popitem(last=False)

    def latest(self):
        return tuple(reversed(self.events))
