"""Uncalibrated classifier output and actual recent votes."""
from PySide6 import QtWidgets
from .base import Panel, current, plot


class TargetCard(Panel):
    def __init__(self):
        super().__init__('选中目标 · Top-5', '实验模型输出，未校准')
        self.name = self.label('等待板端选择', metric=True)
        self.details = self.label('无 Top-5 数据', muted=True)
        self.bars = []
        for _ in range(5):
            label = self.label('—')
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            self.body.addWidget(bar)
            self.bars.append((label, bar))
        self.votes = self.label('最近5票：尚无记录', muted=True)

    def refresh(self, model, twin):
        target, amc = current(model, twin)
        if not self.changed(repr((target, amc, list(model.amc_history)[-5:]))):
            return
        self.name.setText(amc.get('prediction', target.get('label', '?') if target else '未选中'))
        self.details.setText(('%.4f MHz · 模型分数 %.1f%%' % (
            target['frequency_hz']/1e6, amc.get('score', target.get('confidence', 0))*100))
            if target else '请从信号列表或 LCD 选择目标')
        if amc.get('top5_scope') == 'coarse8_softmax':
            self.details.setText(self.details.text()+'\nTop-5：八大类粗分类分数，非十类概率')
        top5 = amc.get('top5', [])
        for i, (label, bar) in enumerate(self.bars):
            entry = top5[i] if i < len(top5) else None
            label.setText('%s  %.1f%%' % (entry['label'], entry['score']*100) if entry else '— 尚未上报')
            bar.setValue(round(max(0, min(1, entry['score']))*1000) if entry else 0)
        votes = [a['prediction'] for a in model.amc_history if target and a['track'] == target['key']][-5:]
        self.votes.setText('最近5票：' + (' → '.join(votes) if votes else '尚无记录'))


class ClassificationHistory(Panel):
    def __init__(self):
        super().__init__('识别分布与历史', '实验性预测计数，不代表正式准确率')
        self.summary = self.label('等待识别结果', metric=True)
        self.history = QtWidgets.QPlainTextEdit()
        self.history.setReadOnly(True)
        self.body.addWidget(self.history, 1)

    def refresh(self, model, twin):
        if self.changed(repr((model.histogram, list(model.amc_history)[-15:]))):
            self.summary.setText('\n'.join('%s   %d' % pair for pair in model.histogram.most_common(10)))
            self.history.setPlainText('\n'.join('%.2fs  目标%s  %s  %.1f%%' % (
                a.get('t_mono', 0), a['track'], a['prediction'], a.get('score', 0)*100)
                for a in list(model.amc_history)[-15:]))
