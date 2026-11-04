"""Local, SHA-verified finite snapshot panorama; no change to wire protocol."""
from PySide6 import QtCore, QtWidgets
from .base import Panel, plot
from ..panorama_data import load_panorama
from ..panorama_live import LivePanorama


class Panorama(Panel):
    file_loaded = QtCore.Signal(str)

    def __init__(self):
        super().__init__('宽频全景 · 有限快照')
        self.state = self.label('尚未载入实测结果', metric=True)
        self.label('A：70–512 MHz；D：512 MHz–2.7 GHz。两种天线分开展示。'
                   '\n纵轴 dBFS/Hz，未经射频功率标定；各频点为不同时刻的接收快照。', muted=True)
        button = QtWidgets.QPushButton('打开全景 result.json（校验 SHA256）')
        button.clicked.connect(self.open_file)
        self.body.addWidget(button)
        self.graph = plot('接收全景 · 滚轮缩放 / 拖动平移')
        self.graph.setLabel('bottom', '频率', units='MHz')
        self.graph.setLabel('left', 'PSD', units='dBFS/Hz')
        self.trace = self.graph.plot(pen='#62E5DC', connect='finite')
        self.body.addWidget(self.graph, 1)
        self.label('频段参考：FM 87–108 MHz；常见对讲 136–174 / 400–470 MHz；'
                   '蜂窝业务与 Wi-Fi 请结合当地频率划分确认。谱峰不等于业务识别。', muted=True)
        self.loaded_path = None
        self.live = LivePanorama()

    def apply_tile(self, packet):
        x, y = self.live.apply(packet)
        self.trace.setData(x, y, connect='finite')
        if len(self.live.tiles) == 1:
            low, high = (70, 512) if self.live.group == 'A' else (512, 2700)
            self.graph.setXRange(low, high, padding=0)
        self.state.setText('实时快照 %s 组 · %d/%d 段\n扫描进行中，最终恢复及 SHA256 待验证' %
                           (self.live.group, len(self.live.tiles), self.live.total))

    def load_file(self, path):
        record, frequency, db, count = load_panorama(path)
        self.trace.setData(frequency/1e6, db)
        self.graph.enableAutoRange()
        coverage = 100*int((count > 0).sum())/len(count)
        self.state.setText('实测 %s 组 · %d 段 · 覆盖 %.2f%%\n已恢复 3.84 MSPS，TX 关闭' %
                           (record['group'], len(record['tiles']), coverage))
        self.loaded_path = str(path)

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, '打开实测全景结果', '', 'JSON (*.json)')
        if path:
            try:
                self.load_file(path)
                self.file_loaded.emit(path)
            except (OSError, ValueError, KeyError, IndexError) as error:
                QtWidgets.QMessageBox.warning(self, '全景校验未通过', str(error))

    def refresh(self, model, twin):
        pass
