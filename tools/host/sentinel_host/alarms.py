"""Detection occupancy alerts with explicit relative-power scope."""
from pathlib import Path
import math
import yaml


class Alarms:
    def __init__(self, rules=()):
        self.rules = list(rules)
        self.last = {}
        for rule in self.rules:
            if set(rule) != {'name','min_hz','max_hz','ratio','cooldown_s'}:
                raise ValueError('Unexpected occupancy rule fields')
            if not isinstance(rule['name'], str) or len(rule['name']) > 80:
                raise ValueError('Invalid occupancy rule name')
            if any(type(rule[k]) not in (int,float) or not math.isfinite(rule[k])
                   for k in ('min_hz','max_hz','ratio','cooldown_s')):
                raise ValueError('Non-finite occupancy rule')
            if not (0 <= rule['min_hz'] < rule['max_hz'] and 0 <= rule['ratio'] <= 1 and rule['cooldown_s'] >= 1):
                raise ValueError('Invalid occupancy threshold or frequency interval')

    @classmethod
    def load(cls, path):
        data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or set(data) != {'occupancy'} or not isinstance(data['occupancy'], list) or len(data['occupancy']) > 32:
            raise ValueError('Expected up to 32 occupancy rules')
        return cls(data['occupancy'])

    def evaluate(self, frequency, ratio, stamp):
        result = []
        for i, rule in enumerate(self.rules):
            selected = ratio[(frequency >= rule['min_hz']) & (frequency <= rule['max_hz'])]
            if selected.size and selected.max() >= rule['ratio'] and stamp-self.last.get(i, -1e30) >= rule['cooldown_s']:
                self.last[i] = stamp
                result.append(dict(type='event', event_kind='OCCUPANCY_ALERT',
                    name=rule['name'], t_mono=stamp, text='CFAR detection occupancy threshold reached',
                    ratio=float(selected.max()), min_hz=rule['min_hz'], max_hz=rule['max_hz']))
        return result
