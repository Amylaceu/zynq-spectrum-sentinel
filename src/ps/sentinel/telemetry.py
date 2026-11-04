"""Read the kernel XADC temperature without touching RF or PL registers."""
import math
from pathlib import Path


class SystemMetrics:
    """Linux whole-system CPU delta and MemTotal-MemAvailable (not process RSS).

    The first CPU reading is unavailable. Guest ticks are already included in
    user/nice by Linux and must not be added a second time.
    """
    def __init__(self, root='/proc'):
        self.root = Path(root)
        self.previous = None

    def sample(self):
        result = dict(ps_cpu_pct=None, ps_memory_bytes=None, ps_memory_total_bytes=None,
                      ps_cpu_scope='all_cores_busy_percent_proc_stat',
                      ps_memory_scope='MemTotal_minus_MemAvailable')
        try:
            fields = (self.root/'stat').read_text().splitlines()[0].split()
            if fields[0] != 'cpu' or len(fields) < 5:
                raise ValueError('Missing aggregate CPU counters')
            ticks = [int(v) for v in fields[1:9]]
            total, idle = sum(ticks), ticks[3]+(ticks[4] if len(ticks)>4 else 0)
            if self.previous is not None:
                dt, di = total-self.previous[0], idle-self.previous[1]
                if dt>0 and 0<=di<=dt:
                    result['ps_cpu_pct'] = 100*(dt-di)/dt
            self.previous = total, idle
        except (OSError, ValueError, IndexError):
            self.previous = None
        try:
            values = {}
            for row in (self.root/'meminfo').read_text().splitlines():
                key, value = row.split(':', 1)
                if key in ('MemTotal', 'MemAvailable'):
                    number, unit = value.split()
                    if unit != 'kB':
                        raise ValueError('Unexpected kernel memory unit')
                    values[key] = int(number)*1024
            total, available = values['MemTotal'], values['MemAvailable']
            if not 0<=available<=total:
                raise ValueError('Invalid memory accounting')
            result.update(ps_memory_bytes=total-available, ps_memory_total_bytes=total)
        except (OSError, ValueError, KeyError):
            pass
        return result


def read_temperature_c(root='/sys/bus/iio/devices'):
    """Return Celsius, or None when no valid XADC reading is available.

    Linux IIO exposes temperature in millidegrees after offset/scale.
    Identify the device by name; its iio:device number may change at boot.
    """
    try:
        for device in sorted(Path(root).glob('iio:device*')):
            if (device/'name').read_text().strip() != 'xadc':
                continue
            raw = float((device/'in_temp0_raw').read_text())
            offset = float((device/'in_temp0_offset').read_text())
            scale = float((device/'in_temp0_scale').read_text())
            value = (raw + offset) * scale / 1000.0
            if scale > 0 and math.isfinite(value) and -40 <= value <= 125:
                return value
    except (OSError, ValueError):
        pass
    return None
