"""Single-owner UI scheduler; never changes the frozen LCD driver or PL.

5 Hz right panel, 2 Hz status, coalesced bank writes. Measurements distinguish
CPU draw/pack/submit from the subsequent hardware acknowledgement wait.
"""
from collections import Counter, deque
import time

import numpy as np

from ..lcd_x5 import draw_ui, displayed_label
from ..ui_events import EventLog
from .layout import draw_ui_v3


class Presenter:
    def __init__(self, lcd, version='v3', clock=time.monotonic):
        if version not in ('v2', 'v3'):
            raise ValueError('Unknown UI version')
        self.lcd, self.version, self.clock = lcd, version, clock
        self.started = clock()
        self.events = EventLog()
        self.events.add('MODE', 'UI '+version)
        self.histogram = Counter()
        self.state = {}
        self.right = self.status = None
        self.last_list = self.last_status = -float('inf')
        self.samples = deque(maxlen=20000)
        self.ack_samples = deque(maxlen=20000)
        self.submissions = self.skipped = self.errors = 0
        self.last_token = None
        self.current_view = None
        self.right_transform = None
        self.rendered_labels = {}
        self.ui_state = None
        self.on_applied = None
        self.last_tracks = []

    def classification(self, label):
        self.histogram[str(label)] += 1

    def present(self, tracks, force=False, **kwargs):
        now = self.clock()
        self.last_tracks = list(tracks)
        self.state.update(kwargs)
        if self.ui_state is not None:
            self.state.update(self.ui_state.options())
        due_list = force or now-self.last_list >= .2
        due_status = force or now-self.last_status >= .5
        if not due_list and not due_status:
            self.skipped += 1
            return None
        self.events.observe(tracks)
        started = self.clock()
        try:
            options = dict(self.state)
            if self.version == 'v3':
                self.current_view = options.get('view') or ('SIG', 'TGT', 'STAT')[int(now//6) % 3]
                options.update(now=now, uptime_s=now-self.started,
                               events=self.events.latest(), histogram=dict(self.histogram))
                if self.ui_state is not None:
                    options['ui_state'] = self.ui_state.snapshot()
                right, status = draw_ui_v3(tracks, **options)
            else:
                for key in ('view', 'selftest_checks', 'sent_label', 'accuracy',
                            'pc_connected', 'histogram', 'events', 'uptime_s', 'now'):
                    options.pop(key, None)
                right, status = draw_ui(tracks, **options)
            if self.right_transform is not None:
                right = self.right_transform(right)
            if not due_list and self.right is not None:
                right = self.right
            if not due_status and self.status is not None:
                status = self.status
            unchanged = (self.right is not None and np.array_equal(right, self.right)
                         and np.array_equal(status, self.status))
            if due_list:
                self.last_list = now
            if due_status:
                self.last_status = now
            if unchanged:
                self.skipped += 1
                return None
            token = self.lcd.submit_ui(right, status)
            submitted = self.clock()
            self.lcd.wait_ui(token)
            applied = self.clock()
            self.samples.append(1000*(submitted-started))
            self.ack_samples.append(1000*(applied-submitted))
            self.submissions += 1
            self.last_token = token
            self.right, self.status = right, status
            if self.on_applied is not None:
                self.on_applied(self, token, right, status)
            if due_list:
                page = int(options.get('page', 0)) % max(1, (len(tracks)+3)//4)
                shown = tracks[page*4:(page+1)*4]
                if self.version == 'v3':
                    if self.current_view == 'TGT':
                        selected = next((t for t in tracks if t.key == options.get('selected')), None)
                        shown = [selected] if selected else tracks[:1]
                    elif self.current_view == 'STAT':
                        shown = []
                self.rendered_labels = {t.key: displayed_label(t) for t in shown}
            return token
        except BaseException:
            self.errors += 1
            raise

    def summary(self):
        samples = list(self.samples)
        return dict(version=self.version, submissions=self.submissions,
                    skipped=self.skipped, errors=self.errors,
                    elapsed_s=self.clock()-self.started,
                    timing_scope='draw + palette pack + MMIO submit; excludes acknowledgement wait',
                    median_ms=float(np.median(samples)) if samples else None,
                    p95_ms=float(np.percentile(samples, 95)) if samples else None,
                    acknowledgement_p95_ms=(float(np.percentile(self.ack_samples, 95))
                                            if self.ack_samples else None),
                    retained_samples=len(samples), timing_samples_ms=samples,
                    classification_counts=dict(self.histogram))
