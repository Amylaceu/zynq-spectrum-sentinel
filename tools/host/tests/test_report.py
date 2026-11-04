import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/host'), str(ROOT/'src/ps')]
import numpy as np
import pytest

from sentinel_host.model import Model
from sentinel_host.report import export_report


def test_report_escapes_text_preserves_real_data_and_hashes(tmp_path):
    model = Model()
    model.targets = [dict(key='<script>alert(1)</script>', frequency_hz=95800000)]
    model.iq = np.ones(512, dtype=np.complex64)
    path = tmp_path/'observation.html'
    result = export_report(model, path, source='replay', session='real_A.zsr')
    assert result['source'] == 'replay' and result['iq_snapshot_samples'] == 512
    text = path.read_text(encoding='utf-8')
    assert '<script>' not in text and '&lt;script&gt;' in text and 'WAV' in text
    assert json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))['targets'] == model.targets
    for p in (path, path.with_suffix('.json')):
        assert hashlib.sha256(p.read_bytes()).hexdigest() == p.with_name(p.name+'.sha256').read_text().split()[0]
    with pytest.raises(FileExistsError):
        export_report(model, path, source='live')


@pytest.mark.parametrize('source', ['unknown', 'synthetic', None])
def test_source_required(tmp_path, source):
    with pytest.raises(ValueError):
        export_report(Model(), tmp_path/'bad.html', source=source)
    assert not list(tmp_path.iterdir())
