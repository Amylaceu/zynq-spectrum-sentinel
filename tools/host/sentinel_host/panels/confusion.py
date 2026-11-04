"""Only per-capture transmitted truth contributes to the demonstration matrix."""
import numpy as np
import pyqtgraph as pg
from .base import Panel, plot


class Confusion(Panel):
    def __init__(self, sequence=False):
        super().__init__('发送与识别记录' if sequence else '混淆矩阵', '演示累计，非正式评测')
        self.value = self.label('等待带发送真值的识别样本', metric=True)
        self.sequence = sequence
        if sequence:
            self.records = self.label('无发送真值时不计算准确率', muted=True)
            self.body.addStretch(1)
        else:
            self.graph = plot()
            self.image = pg.ImageItem(axisOrder='row-major')
            self.image.setLookupTable(pg.colormap.get('CET-L9').getLookupTable())
            self.graph.addItem(self.image)
            self.body.addWidget(self.graph, 1)

    def refresh(self, model, twin):
        if not self.changed(repr(model.confusion)):
            return
        labels = sorted({v for pair in model.confusion for v in pair})
        total = sum(model.confusion.values())
        if not total:
            return
        accuracy = sum(v for (a, b), v in model.confusion.items() if a == b)/total
        self.value.setText('累计 %.1f%% · %d 样本' % (accuracy*100, total))
        if self.sequence:
            self.records.setText('\n'.join('%s → %s   %d' % (a, b, v)
                for (a, b), v in model.confusion.items()))
        else:
            values = np.array([[model.confusion[(a, b)] for b in labels] for a in labels])
            self.image.setImage(values, autoLevels=False, levels=(0, max(1, values.max())))
            ticks = [list(enumerate(labels))]
            self.graph.getAxis('bottom').setTicks(ticks)
            self.graph.getAxis('left').setTicks(ticks)
