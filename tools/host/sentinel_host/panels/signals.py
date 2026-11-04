"""Detected signals; selection is delegated to the board owner."""
from PySide6 import QtCore, QtWidgets
from .base import Panel


class Signals(Panel):
    def __init__(self):
        super().__init__('信号列表', '频率 / 调制 / 模型置信分数 · 单击同步选择')
        self.list = QtWidgets.QListWidget()
        self.list.setStyleSheet('QListWidget::item {padding:12px 4px;font-size:20px;}')
        self.body.addWidget(self.list, 1)
        self.list.itemClicked.connect(lambda item: self.command.emit(
            'select_target', {'key': item.data(QtCore.Qt.ItemDataRole.UserRole)}))

    def refresh(self, model, twin):
        if not self.changed(repr((model.targets, twin.ui_state.get('selected')))):
            return
        self.list.clear()
        for target in model.targets:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, target['key'])
            item.setSizeHint(QtCore.QSize(0, 86))
            self.list.addItem(item)
            card = QtWidgets.QWidget()
            card.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout = QtWidgets.QVBoxLayout(card)
            layout.setContentsMargins(6, 6, 6, 6)
            frequency = QtWidgets.QLabel('%.4f MHz' % (target['frequency_hz']/1e6))
            frequency.setStyleSheet('font:20px Consolas;color:#DFE9EF;')
            detail = QtWidgets.QLabel('%s  %.0f%% · 原始功率 %s' % (
                target.get('label', '?'), target.get('confidence', 0)*100, target['power']))
            detail.setStyleSheet('font-size:12px;color:#AFC4D2;')
            detail.setWordWrap(True)
            layout.addWidget(frequency)
            layout.addWidget(detail)
            self.list.setItemWidget(item, card)
            if target['key'] == twin.ui_state.get('selected'):
                self.list.setCurrentItem(item)
