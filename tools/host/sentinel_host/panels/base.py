"""Shared panel shell and change detection."""
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg


class Panel(QtWidgets.QFrame):
    command = QtCore.Signal(str, object)

    def __init__(self, title, note=None):
        super().__init__()
        self.setProperty('panel', True)
        self.body = QtWidgets.QVBoxLayout(self)
        self.body.setContentsMargins(12, 10, 12, 10)
        self.heading = QtWidgets.QLabel(title)
        self.heading.setProperty('heading', True)
        self.body.addWidget(self.heading)
        if note:
            self.label(note, muted=True)
        self._signature = None

    def label(self, text='', metric=False, muted=False):
        item = QtWidgets.QLabel(text)
        item.setWordWrap(True)
        if metric:
            item.setProperty('metric', True)
        if muted:
            item.setStyleSheet('color:#91A9B9;font-size:12px;')
        self.body.addWidget(item)
        return item

    def changed(self, signature):
        if signature == self._signature:
            return False
        self._signature = signature
        return True


def plot(title=None):
    item = pg.PlotWidget(title=title, background='#121E28')
    item.showGrid(x=True, y=True, alpha=.15)
    item.setMinimumSize(120, 75)
    item.getPlotItem().hideButtons()
    return item


def current(model, twin):
    key = twin.ui_state.get('selected')
    target = next((t for t in model.targets if t['key'] == key), None)
    # No local selection: absent board selection remains absent.
    return target, model.classifications.get(key, {})
