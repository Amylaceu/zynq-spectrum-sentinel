"""The most recently received IQ snapshot, explicitly associated with its track."""
import numpy as np
from .base import Panel, plot


class Constellation(Panel):
    def __init__(self, instantaneous=False):
        super().__init__('瞬时频率快照' if instantaneous else 'IQ 星座快照', '快照数据，非连续采样')
        self.instantaneous = instantaneous
        self.track = self.label('等待 IQ 数据', muted=True)
        graph = plot()
        graph.setAspectLocked(not instantaneous)
        self.trace = graph.plot(pen='#62E5DC' if instantaneous else None,
            symbol=None if instantaneous else 'o', symbolSize=3, symbolBrush='#62E5DC')
        self.body.addWidget(graph, 1)

    def refresh(self, model, twin):
        if not self.changed(id(model.iq)) or not len(model.iq):
            return
        self.track.setText('最近 IQ：目标 %s · %d 点' % (model.iq_track, len(model.iq)))
        if self.instantaneous:
            # No sample rate is guessed: phase increment is shown in rad/sample.
            values = np.angle(model.iq[1:]*model.iq[:-1].conj())
            self.trace.setData(np.arange(len(values)), values)
            self.heading.setText('瞬时相位差 / rad·sample⁻¹')
        else:
            self.trace.setData(model.iq.real, model.iq.imag)
