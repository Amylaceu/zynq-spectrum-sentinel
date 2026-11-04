"""Source-timed telemetry shared by all workbench pages."""
import numpy as np
from .base import Panel, plot


class Telemetry(Panel):
    def __init__(self):
        super().__init__('实时遥测 · 青：fps / 黄：温度°C / 紫：RSSI dBm（不同单位）')
        graph = plot()
        self.curves = [graph.plot(pen=c) for c in ('#62E5DC', '#FFD257', '#CFB2FF')]
        self.body.addWidget(graph, 1)

    def refresh(self, model, twin):
        if model.telemetry and self.changed(repr(model.telemetry[-1])):
            x = np.array([t for t, _ in model.telemetry])
            x -= x[-1]
            for curve, key in zip(self.curves, ('display_fps', 'temperature_c', 'rx_rssi_dbm')):
                curve.setData(x, [t.get(key, float('nan')) for _, t in model.telemetry])
