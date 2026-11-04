"""Audio capability status. No synthetic waveform is presented as real FM."""
import numpy as np
from PySide6 import QtWidgets
from .base import Panel, plot


class Audio(Panel):
    def __init__(self, library=False):
        super().__init__('电台书签与录音库' if library else '音频监听与录音')
        self.source = self.label('PS 并行解调（与喇叭同一射频输入、独立解调）', muted=True)
        self.state = self.label('等待连续 DMA 验收', metric=True)
        if library:
            button = QtWidgets.QPushButton('监听已确认电台 · 95.80 MHz（板载喇叭）')
            button.clicked.connect(lambda: self.command.emit('listen', {'mhz': 95.8}))
            self.body.addWidget(button)
            self.label('PC 音频与录音功能尚未验收；这里不会自动生成录音。', muted=True)
            self.body.addStretch(1)
        else:
            self.level = QtWidgets.QProgressBar()
            self.level.setRange(0, 100)
            self.body.addWidget(self.level)
            graph = plot('音频波形 · 等待已标注来源的 PCM')
            self.trace = graph.plot(pen='#62E5DC')
            self.body.addWidget(graph, 1)
            row = QtWidgets.QHBoxLayout()
            for name in ('PC 监听', '开始录音', '保存 WAV'):
                button = QtWidgets.QPushButton(name)
                button.setEnabled(False)
                button.setToolTip('连续 DMA 与音频链路验证后启用')
                row.addWidget(button)
            self.body.addLayout(row)
        self.library = library

    def refresh(self, model, twin):
        if not self.changed(repr(model.audio)) or not model.audio:
            return
        source = model.audio.get('source')
        names = {'ps_parallel_demod': 'PS 并行解调（与喇叭同一射频输入、独立解调）',
                 'pl_playback_mirror': 'PL 播放 PCM 镜像', 'synthetic-test': '合成音频 · 仅离线预览，非板测'}
        self.source.setText(names.get(source, '未知音频来源 · 不可作为验收数据'))
        synthetic = model.hello.get('spectrum_source') == 'synthetic-test'
        self.state.setText('离线合成示例 · 尚未通过实测' if synthetic else '已收音频 · 连续性待认证')
        if not self.library and len(model.audio_pcm):
            values = model.audio_pcm.astype(float)/32768
            self.level.setValue(min(100, round(np.sqrt(np.mean(values**2))*100)))
            self.trace.setData(np.arange(len(values))/48, values)
