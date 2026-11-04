"""Session controls delegate verified replay and exports to the shell."""
from PySide6 import QtCore, QtWidgets
from .base import Panel


class Sessions(Panel):
    action = QtCore.Signal(str)

    def __init__(self, exports=False):
        super().__init__('会话导出' if exports else '会话录制与回放')
        self.info = self.label('回放会先校验 SHA256；不会向板端发送命令。', muted=True)
        items = [('保存整窗截图', 'screenshot'), ('导出目标 CSV', 'export_csv'),
                 ('导出当前 IQ 快照', 'export_iq'), ('导出演示混淆矩阵', 'export_matrix'),
                 ('导出观察摘要 HTML', 'export_html')] if exports else [
                 ('打开 .zsr 会话', 'replay'), ('开始 / 停止录制', 'record'),
                 ('暂停 / 继续', 'pause'), ('切换回放速度', 'speed')]
        for label, action in items:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _, a=action: self.action.emit(a))
            self.body.addWidget(button)
        self.label('IQ 导出为 512 点快照；HTML 为当前保留数据摘要。连续 IQ 与 WAV 未通过验收。', muted=True)
        self.body.addStretch(1)

    def refresh(self, model, twin):
        pass
