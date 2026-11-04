"""Bounded event list, exposing activation to the shell."""
from PySide6 import QtCore, QtGui, QtWidgets
from .base import Panel


class Timeline(Panel):
    activated = QtCore.Signal(object)

    def __init__(self):
        super().__init__('事件时间轴')
        self.list = QtWidgets.QListWidget()
        self.list.setFlow(QtWidgets.QListView.Flow.LeftToRight)
        self.list.itemClicked.connect(lambda item: self.activated.emit(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.body.addWidget(self.list)

    def refresh(self, model, twin):
        events = list(model.events)[-12:]
        if not self.changed(repr(events)):
            return
        self.list.clear()
        for event in events:
            kind = event.get('event_kind', 'EVENT')
            item = QtWidgets.QListWidgetItem('● %s  %s' % (kind, event.get('text', event.get('name', ''))))
            color = '#FF5A5A' if kind == 'ALARM' else '#FFD257' if kind == 'MOD CHG' else '#62E5DC'
            item.setForeground(QtGui.QColor(color))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, event)
            self.list.addItem(item)
