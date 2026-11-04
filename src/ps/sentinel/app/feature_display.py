"""Compact factual labels for the existing ui_v3 right panel and footer."""

NAMES = {'F0': 'PN CHECK', 'F1': 'LIVE RX', 'F2': 'TONE', 'F3': 'WINDOW',
         'F4': 'AVERAGE', 'F5': 'CFAR', 'F6': 'NOISE', 'F7': 'CHANNEL',
         'F8': 'FM AUDIO', 'F9': 'GOLDEN', 'F10': 'CPU / PL',
         'F11': 'PANORAMA', 'F12': 'FM VOTE', 'F13': 'AMC', 'F14': 'WIFI'}


def display_options(identity, result=None, progress=None, station_hz=None):
    title = identity+' '+NAMES.get(identity, '')
    metrics = (result or {}).get('metrics', {})
    fields = {'F1': ('目标数', 'TARGETS'), 'F2': ('最大误差', 'BIN'),
              'F4': ('AVG_SHIFT', 'SHIFT'), 'F5': ('PL目标数', 'TARGETS'),
              'F6': ('峰值/中位底噪', 'dB'), 'F7': ('提取通道', 'CH'),
              'F9': ('不一致', 'ERRORS'), 'F10': ('CPU/PL比值', 'X')}
    detail = 'RUN'
    if identity in fields and fields[identity][0] in metrics:
        name, unit = fields[identity]
        value = metrics[name]['after']
        detail = ('%.3g' % value if isinstance(value, (int, float)) else str(value))+' '+unit
    if identity == 'F8' and station_hz is not None:
        detail = '%.3f MHz' % (station_hz/1e6)
    if progress:
        detail = progress
    # The subtitle has 226px at BODY size; key numbers also appear in footer.
    return dict(demo_mode=identity, demo_title=title,
                model_status=title+' | '+detail+' | TX OFF')
