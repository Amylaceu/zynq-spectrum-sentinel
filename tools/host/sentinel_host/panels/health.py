"""Reported health values; never substitutes missing PS metrics."""
from .base import Panel


class Health(Panel):
    def __init__(self):
        super().__init__('系统健康')
        self.value = self.label('等待遥测', metric=True)
        self.detail = self.label('PS CPU / 内存：尚未上报', muted=True)

    def refresh(self, model, twin):
        if not model.telemetry or not self.changed(repr(model.telemetry[-1])):
            return
        t = model.telemetry[-1][1]
        def value(key, pattern):
            return pattern % t[key] if t.get(key) is not None else '—'
        self.value.setText('%s fps\n%s °C\n%s dBm' % (
            value('display_fps', '%.1f'), value('temperature_c', '%.1f'), value('rx_rssi_dbm', '%.1f')))
        cpu = value('ps_cpu_pct', '%.1f%%')
        memory = ('%.1f MB' % (t['ps_memory_bytes']/1024**2)
                  if t.get('ps_memory_bytes') is not None else '尚未上报')
        self.detail.setText('PS CPU：%s\nPS 已用内存：%s' % (cpu, memory))
