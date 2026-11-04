"""Verify user-facing exports contain the received data, not placeholders."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import csv
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/host'),str(ROOT/'src/ps')]
from PySide6 import QtWidgets
from sentinel_host.gui import Window


def test_csv_iq_png_and_known_truth_matrix(tmp_path,monkeypatch):
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w=Window();w.show()
    w.model.targets=[dict(key=9,frequency_hz=95800000,bandwidth_hz=150000,
        power=123,label='FM',confidence=.85,first_seen_mono=1234)]
    w.model.iq=np.exp(2j*np.pi*np.arange(512)/17).astype('<c8')
    w.model.confusion[('QPSK','QPSK')]=3
    w.model.confusion[('QPSK','FM')]=1
    w.refresh();app.processEvents()
    output=[tmp_path/'targets.csv']
    monkeypatch.setattr(QtWidgets.QFileDialog,'getSaveFileName',lambda *a,**k:(str(output[0]),''))
    w.export_csv()
    with output[0].open(encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==1 and rows[0]['frequency_hz']=='95800000' and rows[0]['label']=='FM'
    output[0]=tmp_path/'iq.npy';w.export_iq()
    assert np.array_equal(np.load(output[0],allow_pickle=False),w.model.iq)
    assert np.array_equal(np.fromfile(output[0].with_suffix('.cf32'),dtype='<c8'),w.model.iq)
    output[0]=tmp_path/'matrix.png';w.export_matrix()
    assert output[0].read_bytes().startswith(b'\x89PNG')
    output[0]=tmp_path/'screen.png';w.screenshot()
    from PIL import Image
    with Image.open(output[0]) as image:
        assert image.format == 'PNG' and image.width >= 800 and image.height >= 480
    w.close()
