"""Detection occupancy, not calibrated channel utilisation."""
import numpy as np
from .base import Panel, plot


class Occupancy(Panel):
    def __init__(self):
        super().__init__('频段占用度', '最近10秒 CFAR 检出比例，非校准占用率')
        graph = plot()
        graph.setYRange(0, 1)
        self.trace = graph.plot(pen='#FFD257', fillLevel=0, brush=(255, 210, 87, 40))
        self.body.addWidget(graph)

    def refresh(self, model, twin):
        signature = (model.spectrum_count, model.occupancy[-1][0] if model.occupancy else None)
        if self.changed(signature):
            self.trace.setData(model.frequency/1e6, model.occupancy_ratio())
