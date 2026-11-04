"""Acquisition-owner UI state shared by the LCD and remote observers.

No hardware calls or second copy of UI state lives in the desktop client.
"""
import time


class UIState:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.view = self.selected = None
        self.page = 0
        self.listening = self.recording = False
        self.hint = ''
        self.revision = 0
        self.action = None
        self.rect = None
        self.pressed_until = self.flash_until = 0.
        self.request = None

    def change(self, action, rect=None, request=None):
        self.revision += 1
        self.action, self.rect, self.request = action, rect, request
        now = self.clock()
        self.pressed_until, self.flash_until = now+.3, now+.5

    def snapshot(self):
        now = self.clock()
        return dict(view=self.view, selected=self.selected, page=self.page,
                    listening=self.listening, recording=self.recording,
                    hint=self.hint, revision=self.revision, action=self.action,
                    rect=self.rect if now < self.flash_until else None,
                    pressed=now < self.pressed_until, request=self.request)

    def options(self):
        result = dict(page=self.page)
        if self.view is not None:
            result['view'] = self.view
        if self.selected is not None:
            result['selected'] = self.selected
        return result
