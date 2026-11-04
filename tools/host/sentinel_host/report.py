"""Export a bounded, explicitly scoped desktop observation, with SHA256."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path


LIMITATIONS = [
    '这是上位机当前保留数据的观察摘要，不是正式准确率或射频标定报告。',
    '分类分数为未校准的八大类模型输出，识别准确率未达标记录保留。',
    'IQ 为当前 512 点快照，不代表连续 5 秒采集。',
    'PC 连续音频未通过 DMA 长测，本报告不包含 WAV 或喇叭播放 PCM。',
    'PL 画面为抽样重建；PS 界面帧使用板端提交的原始数据。',
]


def export_report(model, path, *, source, session=None):
    """Write new HTML/JSON/sidecars; do not overwrite an existing artifact."""
    path = Path(path)
    if path.suffix.lower() != '.html' or source not in ('live', 'replay', 'offline'):
        raise ValueError('Require .html path and explicit live/replay/offline source')
    side = path.with_suffix('.json')
    destinations = [path, side, Path(str(path)+'.sha256'), Path(str(side)+'.sha256')]
    if any(p.exists() for p in destinations):
        raise FileExistsError('Preserve previous export; use a new filename')
    latest = model.telemetry[-1][1] if model.telemetry else None
    data = dict(schema='sentinel_observation/1', source=source, session=session,
        created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Current bounded desktop state; not complete historical session',
        received_spectra=model.spectrum_count, last_hello=model.hello,
        targets=model.targets[:32], classifications=list(model.amc_history)[-256:],
        telemetry_latest=latest, events=list(model.events)[-100:],
        demo=model.demo, histogram=dict(model.histogram),
        demo_confusion=[dict(transmitted=a, predicted=b, count=n)
                        for (a,b),n in sorted(model.confusion.items())],
        iq_snapshot_samples=int(model.iq.size), limitations=LIMITATIONS)
    encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    content = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<title>频谱终端观察摘要</title><style>body{max-width:1100px;margin:30px auto;'
        'font:16px sans-serif;line-height:1.7}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        '</style><h1>频谱终端观察摘要</h1><p>数据模式：'+html.escape(source.upper())+
        '</p><h2>范围与限制</h2><ul>'+''.join('<li>'+html.escape(s)+'</li>' for s in LIMITATIONS)+
        '</ul><h2>保留的实测字段</h2><pre>'+html.escape(encoded)+'</pre></html>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    side.write_text(encoded, encoding='utf-8')
    for artifact in (path, side):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        Path(str(artifact)+'.sha256').write_text(digest+'  '+artifact.name+'\n', encoding='ascii')
    return data
