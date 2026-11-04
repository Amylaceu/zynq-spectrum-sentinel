"""Frozen build evidence supplied by the shell, not invented runtime values."""
from .base import Panel


class System(Panel):
    def __init__(self, architecture=False):
        super().__init__('软硬件数据流' if architecture else 'FPGA 资源与时序', '数据来自冻结版本构建报告，非运行时测量')
        self.architecture = architecture
        self.value = self.label('', metric=not architecture)
        self.detail = self.label('', muted=True)
        self.body.addStretch(1)

    def refresh(self, model, twin):
        if not self.changed(repr(model.build_info)):
            return
        if self.architecture:
            self.value.setText('AD9361 射频输入\n↓\nPL：FFT / CFAR / LCD / FM音频\n↓\nPS：目标跟踪 / 实验模型 / hostlink\n↓\nPC：孪生显示 / 记录与分析')
            self.detail.setText('PS 并行 FM 与连续 DMA 尚待验收。\n模型、CFAR 和 100 MHz 位流保持冻结。')
            return
        data = model.build_info
        if not data:
            self.value.setText('构建报告不可用')
            return
        r, t = data['resources'], data['final_timing']
        self.value.setText('LUT  %s\nBRAM  %s\nDSP  %s' % (r['Slice LUTs'], r['Block RAM Tile'], r['DSPs']))
        self.detail.setText('WNS  %+.3f ns\nWHS  %+.3f ns\n100 MHz / 3.84 MSPS\n历史未达标结论保留' % (t['WNS_ns'], t['WHS_ns']))
