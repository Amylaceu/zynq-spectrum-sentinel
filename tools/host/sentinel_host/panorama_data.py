"""Read verified F4 finite snapshot artifacts, without a radio connection."""
import hashlib
import json
from pathlib import Path

import numpy as np


def checked(path, expected=None):
    path = Path(path)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('全景文件 SHA256 不匹配: '+path.name)
    if expected is not None and actual != expected:
        raise ValueError('全景清单摘要不匹配: '+path.name)
    return path


def local_file(root, name):
    if not isinstance(name, str) or Path(name).name != name or '\\' in name:
        raise ValueError('全景文件必须位于结果目录内')
    path = root/name
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise ValueError('全景文件越出结果目录')
    return path


def load_panorama(path):
    path = checked(Path(path))
    record = json.loads(path.read_text(encoding='utf-8'))
    if (record.get('status') != 'PASS_SNAPSHOT_SCAN' or record.get('group') not in ('A', 'D')
            or record.get('source') != 'RX1A_ANTENNA'
            or record.get('scope') != 'FINITE_DISCONTINUOUS_RAW_DMA_SNAPSHOTS'
            or record.get('rf_transmission_requested') is not False
            or record.get('baseline_restore', {}).get('rate_hz') != 3840000
            or record.get('stopped') != dict(gpio=0, source=0, audio=0)
            or record.get('buffers_quarantined') is not False):
        raise ValueError('需要完成恢复及安全停止的真实扫频文件')
    if not isinstance(record.get('tiles'), list) or not record['tiles']:
        raise ValueError('缺少原始快照清单')
    for tile in record['tiles']:
        checked(local_file(path.parent, tile['file']), tile['sha256'])
    panorama = checked(local_file(path.parent, record['panorama']), record['panorama_sha256'])
    with np.load(panorama, allow_pickle=False) as values:
        frequency, power, count = (values[key].copy() for key in
                                   ('frequency_hz', 'psd_fs2_per_hz', 'count'))
    if (frequency.ndim != 1 or not len(frequency) or power.shape != frequency.shape
            or count.shape != frequency.shape or not np.all(np.isfinite(frequency))
            or not np.all(np.diff(frequency) > 0) or not np.issubdtype(count.dtype, np.integer)
            or np.any(count < 0) or np.any(power[count > 0] < 0)
            or not np.all(np.isfinite(power[count > 0])) or not np.all(np.isnan(power[count == 0]))):
        raise ValueError('全景数组无效或缺口被填补')
    db = 10*np.log10(np.maximum(power, 1e-20))
    return record, frequency, db, count
