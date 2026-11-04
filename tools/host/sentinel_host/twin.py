"""LCD physical-pixel canvas. State comes only from board UI messages."""
import hashlib
import zlib

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from sentinel.display_twin import decompress_exact, ui_layer, UI_BYTES
from sim.golden.render import render_frame, x5_levels


def rgb888(words):
    a = np.asarray(words, dtype=np.uint16)
    rgb = np.empty(a.shape+(3,), dtype=np.uint8)
    rgb[..., 0] = ((a >> 11)*255//31).astype(np.uint8)
    rgb[..., 1] = (((a >> 5) & 63)*255//63).astype(np.uint8)
    rgb[..., 2] = ((a & 31)*255//31).astype(np.uint8)
    return rgb


class Twin:
    def __init__(self):
        self.ui = np.full((480, 800), 0xf81f, dtype=np.uint16)
        self.spec = self.threshold = None
        self.waterfall = np.zeros((240, 560), dtype=np.uint8)
        self.ui_state = {}
        self.header = {}
        self.epoch = None
        self.count = self.pl_count = self.ui_count = 0
        self.lo = None

    def apply(self, header, payload):
        if header['type'] == 'ui_frame':
            raw = decompress_exact(payload, UI_BYTES)
            if hashlib.sha256(raw).hexdigest() != header['sha256']:
                raise ValueError('UI frame digest mismatch')
            self.ui = ui_layer(payload)
            self.epoch = header['epoch']
            self.ui_count += 1
        elif header['type'] == 'ui_state':
            self.ui_state = dict(header)
        elif header['type'] == 'pl_frame':
            if header.get('profile') != 'x5_frozen':
                raise ValueError('Unknown frozen LCD profile')
            raw = decompress_exact(payload, 1120)
            self.spec = np.frombuffer(raw, dtype='<i2').copy()
            if self.lo != header.get('lo_hz'):
                self.waterfall[:] = 0
                self.lo = header.get('lo_hz')
            self.waterfall[1:] = self.waterfall[:-1]
            self.waterfall[0] = x5_levels(self.spec)[1]
            self.header = dict(header)
            self.pl_count += 1
        else:
            return
        self.count += 1

    def render(self):
        return render_frame(self.spec, None, self.threshold, None, self.waterfall, None,
                            self.ui, cfg=dict(profile='x5_frozen'))


class TwinCanvas(QtWidgets.QWidget):
    click = QtCore.Signal(int, int)
    double_click = QtCore.Signal(int, int)
    context = QtCore.Signal(int, int)
    lo_steps = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 480)
        self.setMouseTracking(True)
        self.image = None
        self.hover = None
        self.setToolTip('LCD twin: PS pixels from active UI bank; PL is sampled reference reconstruction')

    def sizeHint(self):
        return QtCore.QSize(800, 480)

    def viewport(self):
        scale = max(1, min(self.width()//800, self.height()//480))
        return QtCore.QRect((self.width()-800*scale)//2, (self.height()-480*scale)//2, 800*scale, 480*scale)

    def physical(self, position):
        rect = self.viewport()
        if not rect.contains(position.toPoint()):
            return None
        return int((position.x()-rect.x())*800/rect.width()), int((position.y()-rect.y())*480/rect.height())

    def set_frame(self, frame):
        rgb = np.ascontiguousarray(rgb888(frame))
        self.image = QtGui.QImage(rgb.data, 800, 480, rgb.strides[0], QtGui.QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor('#071018'))
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        if self.image:
            p.drawImage(self.viewport(), self.image)
        else:
            p.setPen(QtGui.QColor('cyan'))
            p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, 'Waiting for board LCD twin frames')

    def mousePressEvent(self, event):
        point = self.physical(event.position())
        if point:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.click.emit(*point)
            elif event.button() == QtCore.Qt.MouseButton.RightButton:
                self.context.emit(*point)

    def mouseDoubleClickEvent(self, event):
        point = self.physical(event.position())
        if point and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.double_click.emit(*point)

    def mouseMoveEvent(self, event):
        point = self.physical(event.position())
        self.hover = point
        if point:
            self.setToolTip('LCD x=%d y=%d' % point)

    def wheelEvent(self, event):
        steps = event.angleDelta().y()//120
        if steps:
            self.lo_steps.emit(steps)
        event.accept()
