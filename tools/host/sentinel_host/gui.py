"""Single-window desktop UI. Network worker owns sockets, Qt owns all widgets."""
import csv
from datetime import datetime
import json
from pathlib import Path
import queue
import socket
import itertools
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
import pyqtgraph.exporters

from sentinel.app.hostlink_protocol import Decoder, encode
from .model import Model
from .session import Recorder, Replay
from .alarms import Alarms
from .twin import Twin, TwinCanvas


class Receiver(QtCore.QThread):
    packet = QtCore.Signal(object, object, float)
    state = QtCore.Signal(str)

    def __init__(self, address=None, session=None, port=9000, token=None):
        super().__init__()
        self.address, self.session = address, session
        self.port, self.token = port, token
        self.requests = queue.Queue(maxsize=32)
        self.speed = 1.
        self.paused = False
        self._sequence = itertools.count(1)

    def command(self, name, **args):
        if self.session:
            return None
        seq = next(self._sequence)
        try:
            self.requests.put_nowait((seq, name, args))
            return seq
        except queue.Full:
            self.state.emit('命令队列已满')

    def run(self):
        if self.session:
            try:
                self.state.emit('回放 / '+str(self.session))
                previous = 0.
                for elapsed, header, payload in Replay(self.session):
                    remaining = max(0, elapsed-previous)
                    while remaining > 0 or self.paused:
                        if self.isInterruptionRequested():
                            return
                        before = time.monotonic()
                        self.msleep(10)
                        if not self.paused:
                            remaining -= (time.monotonic()-before)*self.speed
                    if self.isInterruptionRequested():
                        return
                    self.packet.emit(header, payload, time.monotonic())
                    previous = elapsed
                self.state.emit('回放完成')
            except Exception as error:
                self.state.emit('回放失败：'+str(error))
            return
        while not self.isInterruptionRequested():
            try:
                with socket.create_connection((self.address, self.port), timeout=2) as client:
                    client.settimeout(.1)
                    decoder = Decoder()
                    self.state.emit('已连接 / '+self.address)
                    while not self.isInterruptionRequested():
                        for _ in range(8):
                            try:
                                seq, name, args = self.requests.get_nowait()
                            except queue.Empty:
                                break
                            request = dict(type='command', seq=seq, len=0,
                                t_mono=time.monotonic(), command=name, args=args)
                            if self.token:
                                request['token'] = self.token
                            client.sendall(encode(request))
                        try:
                            data = client.recv(65536)
                        except socket.timeout:
                            continue
                        if not data:
                            raise ConnectionError('Board disconnected')
                        for header, payload in decoder.feed(data):
                            self.packet.emit(header, payload, time.monotonic())
            except Exception as error:
                # A reconnect must never execute stale scene/audio requests.
                while True:
                    try:
                        self.requests.get_nowait()
                    except queue.Empty:
                        break
                self.state.emit('连接已断开 / '+str(error))
                for _ in range(20):
                    if self.isInterruptionRequested():
                        return
                    self.msleep(100)


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('SentinelHost — 实时频谱监测终端')
        self.resize(1600, 950)
        self.model, self.worker, self.recorder = Model(), None, None
        self.twin = Twin()
        self.last_twin_painted = -1
        self.twin_painted = 0
        self._pending_lo = None
        self.last_painted = -1
        self.latencies = []
        self.last_received = None
        self.recording_count = 0
        self.data_errors = []
        self.painted_frames = 0
        self.alarms = Alarms()
        self.alert_popups = True
        self.alerts = []
        self._active_popups = []
        self._targets_signature = None
        self._event_signature = None
        self.toolbar = self.addToolBar('连接与会话')
        self.address = QtWidgets.QLineEdit('192.168.2.99')
        self.address.setMaximumWidth(140)
        self.toolbar.addWidget(self.address)
        self.token = QtWidgets.QLineEdit()
        self.token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('可选访问令牌')
        self.token.setMaximumWidth(100)
        self.toolbar.addWidget(self.token)
        for label, callback in [('连接', self.connect_board), ('录制会话', self.record),
                                ('回放', self.replay), ('暂停/继续', self.pause),
                                ('回放速度', self.speed), ('截图', self.screenshot),
                                ('目标CSV', self.export_csv), ('IQ快照', self.export_iq),
                                ('混淆矩阵', self.export_matrix), ('告警规则', self.load_alarms),
                                ('放大＋', self.zoom_in), ('缩小－', self.zoom_out), ('全屏 F11', self.fullscreen)]:
            self.toolbar.addAction(label, callback)
        self.status = QtWidgets.QLabel('离线')
        self.toolbar.addWidget(self.status)
        self.title = QtWidgets.QLabel('FPGA 实时频谱监测 / 相对原始功率')
        self.title.setStyleSheet('font: bold 22px monospace; color: #62e5dc; padding:8px')
        central = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(central)
        self.views = QtWidgets.QTabWidget()
        self.twin_page = QtWidgets.QWidget()
        twin_layout = QtWidgets.QVBoxLayout(self.twin_page)
        self.twin_canvas = TwinCanvas()
        self.zoom_level = 1
        self.twin_canvas.setFixedSize(800, 480)
        self.twin_scroll = QtWidgets.QScrollArea()
        self.twin_scroll.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.twin_scroll.setWidget(self.twin_canvas)
        twin_layout.addWidget(self.twin_scroll, 1)
        self.twin_scope = QtWidgets.QLabel('PS：等待与LCD相同的界面帧；PL：频谱抽样重建，冻结位流暂不支持门限读回。点击“放大＋”可按整数倍放大。')
        self.twin_scope.setWordWrap(True)
        twin_layout.addWidget(self.twin_scope)
        self.views.addTab(self.twin_page, 'LCD 孪生视图')
        self.views.addTab(central, '分析视图')
        self.setCentralWidget(self.views)
        self.twin_canvas.click.connect(self.twin_click)
        self.twin_canvas.double_click.connect(self.twin_listen)
        self.twin_canvas.context.connect(self.twin_context)
        self.twin_canvas.lo_steps.connect(self.twin_wheel)
        self.lo_timer = QtCore.QTimer(self)
        self.lo_timer.setSingleShot(True)
        self.lo_timer.timeout.connect(self.commit_lo)
        grid.addWidget(self.title, 0, 0, 1, 3)
        pg.setConfigOptions(antialias=False, background='#101820', foreground='#dceaf3')
        self.spectrum = pg.PlotWidget(title='实时频谱 / 历史峰值 — 原始整数功率参考')
        self.spectrum.setLabel('bottom', '频率', units='MHz')
        self.spectrum.setLabel('left', '相对功率', units='dB')
        self.trace = self.spectrum.plot(pen=pg.mkPen('#60e5d6', width=2))
        self.peak = self.spectrum.plot(pen=pg.mkPen('#c6a15c', width=1))
        self.markers = self.spectrum.plot(pen=None, symbol='t', symbolBrush='#ffd257', symbolSize=10)
        grid.addWidget(self.spectrum, 1, 0, 1, 2)
        self.water = pg.PlotWidget(title='瀑布图 / 最近300帧')
        self.water_image = pg.ImageItem(axisOrder='row-major')
        self.water.addItem(self.water_image)
        self.water.setLabel('bottom', '频率', units='MHz')
        self.water.setLabel('left', '帧序')
        self.water_image.setLookupTable(pg.colormap.get('CET-L9').getLookupTable())
        grid.addWidget(self.water, 2, 0, 1, 2)
        self.occupancy_plot = pg.PlotWidget(title='CFAR 检出占用度 / 最近10秒')
        self.occupancy_trace = self.occupancy_plot.plot(pen='#ffd257', fillLevel=0, brush=(255,210,87,70))
        self.occupancy_plot.setMaximumHeight(100)
        self.occupancy_plot.setYRange(0,1)
        grid.addWidget(self.occupancy_plot, 3, 0, 1, 2)
        self.scatter = pg.PlotWidget(title='选中目标 IQ / 512点快照')
        self.scatter.setAspectLocked(True)
        self.scatter_item = self.scatter.plot(pen=None, symbol='o', symbolSize=3, symbolBrush='#61e1dd')
        grid.addWidget(self.scatter, 4, 0)
        self.telemetry = pg.PlotWidget(title='运行状态 / 最近60秒（帧率 / 温度 / RSSI）')
        self.curves = [self.telemetry.plot(pen=color) for color in ('#60e5d6','#ffd257','#d9c1ff')]
        grid.addWidget(self.telemetry, 4, 1)
        self.targets = QtWidgets.QTableWidget(0, 6)
        self.targets.setHorizontalHeaderLabels(['频率MHz','带宽kHz','原始功率','调制','置信度','首次出现时间'])
        self.targets.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.targets.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.targets.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.targets.cellClicked.connect(self.select_target)
        grid.addWidget(self.targets, 1, 2, 2, 1)
        self.hist = QtWidgets.QLabel('实验性识别结果 / 准确率尚未认证')
        self.hist.setWordWrap(True)
        grid.addWidget(self.hist, 3, 2, 2, 1)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('搜索事件日志')
        self.search.textChanged.connect(self.show_events)
        grid.addWidget(self.search, 5, 0, 1, 3)
        self.events = QtWidgets.QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumHeight(110)
        grid.addWidget(self.events, 6, 0, 1, 3)
        self.footer = QtWidgets.QLabel('FPGA 实时处理 · 3.84 MSPS · 100 MHz / 上位机不提供发射控制')
        grid.addWidget(self.footer, 7, 0, 1, 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        for row in (1,2,4):
            grid.setRowStretch(row, 1)
        QtGui.QShortcut(QtGui.QKeySequence('F11'), self, activated=self.fullscreen)
        QtGui.QShortcut(QtGui.QKeySequence('Tab'), self,
            activated=lambda: self.views.setCurrentIndex(1-self.views.currentIndex()))
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(50)
        self.setStyleSheet('QMainWindow,QWidget{background:#101820;color:#dceaf3;} '
            'QLineEdit,QPlainTextEdit,QTableWidget{background:#182630;color:#dceaf3;}'
            'QHeaderView::section{background:#24404e;color:#dceaf3;padding:4px;}'
            'QToolBar{spacing:8px;border-bottom:1px solid #315364;}')

    def stop_worker(self):
        if self.worker:
            self.worker.requestInterruption()
            if not self.worker.wait(4000):
                raise RuntimeError('Network/replay worker did not stop')
            self.worker = None

    def start_worker(self, **kwargs):
        self.stop_worker()
        if self.recorder:
            self.recorder.close()
            self.recorder = None
        self.model = Model()
        self.twin = Twin()
        self.last_twin_painted = -1
        self._pending_lo = None
        self.lo_timer.stop()
        self.last_painted = -1
        self.worker = Receiver(**kwargs)
        self.worker.packet.connect(self.packet)
        self.worker.state.connect(self.status.setText)
        self.worker.start()

    def connect_board(self):
        self.start_worker(address=self.address.text().strip(), token=self.token.text() or None)

    def packet(self, header, payload, received):
        try:
            if self.recorder:
                self.recorder.append(header, payload)
                self.recording_count += 1
            self.model.apply(header, payload, observed=received)
            self.twin.apply(header, payload)
            if header['type'] == 'spectrum':
                self.last_received = received
        except Exception as error:
            self.data_errors.append(str(error))
            self.data_errors = self.data_errors[-32:]
            self.status.setText('数据或录制错误：'+str(error))
            if self.recorder:
                self.recorder.close()
                self.recorder = None

    def refresh(self):
        if self.twin.count != self.last_twin_painted:
            self.twin_canvas.set_frame(self.twin.render())
            self.last_twin_painted = self.twin.count
            self.twin_painted += 1
            if self.twin.ui_count:
                self.twin_scope.setText('放大 %d× | PS：LCD原始界面帧 %s | PL：功率抽样重建，暂不含门限 | 已收频谱 %d / 界面 %d 帧' %
                    (self.zoom_level, self.twin.epoch, self.twin.pl_count, self.twin.ui_count))
        m = self.model
        if m.spectrum_count != self.last_painted:
            self.trace.setData(m.frequency/1e6, m.power)
            self.peak.setData(m.frequency/1e6, m.peak)
            self.water_image.setImage(m.waterfall, autoLevels=False,
                levels=(float(np.percentile(m.power,10))-5, float(np.max(m.power))+2))
            self.water_image.setRect(QtCore.QRectF(m.frequency[0]/1e6,0,
                (m.frequency[-1]-m.frequency[0]+3750)/1e6,300))
            self.occupancy_trace.setData(m.frequency/1e6, m.occupancy_ratio())
            if self.last_received is not None:
                self.latencies.append(1000*(time.monotonic()-self.last_received))
                self.latencies = self.latencies[-20000:]
            self.last_painted = m.spectrum_count
            self.painted_frames += 1
        if len(m.iq):
            self.scatter_item.setData(m.iq.real, m.iq.imag)
        signature = json.dumps(m.targets, sort_keys=True)
        if signature != self._targets_signature:
            indices = [int(np.argmin(np.abs(m.frequency-t['frequency_hz']))) for t in m.targets]
            self.markers.setData([m.frequency[i]/1e6 for i in indices], [m.power[i] for i in indices])
            self.targets.setRowCount(len(m.targets))
            for row, target in enumerate(m.targets):
                values = [f"{target['frequency_hz']/1e6:.4f}",f"{target['bandwidth_hz']/1e3:.1f}",
                    str(target['power']), target.get('label','?'),f"{target.get('confidence',0):.2f}",
                    f"{target.get('first_seen_mono',0):.1f}"]
                for column, value in enumerate(values):
                    self.targets.setItem(row, column, QtWidgets.QTableWidgetItem(value))
            self._targets_signature = signature
        if m.telemetry:
            x = np.array([t for t,_ in m.telemetry]); x -= x[-1]
            for curve, key in zip(self.curves, ('display_fps','temperature_c','rx_rssi_dbm')):
                curve.setData(x, [t.get(key,float('nan')) for _,t in m.telemetry])
        self.hist.setText('调制类别计数（实验性结果）\n\n'+'\n'.join(
            '%s: %d' % item for item in m.histogram.most_common())+
            '\n\n具有发送真值的识别样本数：'+str(sum(m.confusion.values())))
        if m.demo:
            self.title.setText('%s  %s   %.1f s' % (m.demo.get('group',''),
                m.demo.get('title',''), m.demo.get('remaining_s',0)))
        elif m.hello:
            self.title.setText('%s / 本振 %.3f MHz / %.2f MSPS / 相对原始功率' %
                ('回放' if self.worker and self.worker.session else '实时',
                 (m.lo or m.hello.get('lo_hz',0))/1e6,m.hello.get('sample_rate_hz',0)/1e6))
        if m.occupancy:
            for alert in self.alarms.evaluate(m.frequency,m.occupancy_ratio(),m.occupancy[-1][0]):
                self.alerts.append(alert)
                self.alerts = self.alerts[-128:]
                m.events.append(alert)
                if self.alert_popups and len(self._active_popups) < 3:
                    box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Icon.Information,
                        '频段占用度告警', alert['name'],parent=self)
                    self._active_popups.append(box)
                    box.finished.connect(lambda _, b=box: self._active_popups.remove(b))
                    box.open()
        event_signature = repr(list(m.events))
        if event_signature != self._event_signature:
            self.show_events()
            self._event_signature = event_signature

    def send(self, name, **args):
        if self.worker and not self.worker.session:
            return self.worker.command(name, **args)

    def twin_click(self, x, y):
        self.send('click', x=x, y=y)

    def twin_listen(self, x, y):
        # A double click still sends physical click first. Board owns selection.
        # The follow-up soft key resolves that selection in the same command FIFO.
        self.twin_click(x, y)
        self.twin_click(515, 465)

    def twin_context(self, x, y):
        menu = QtWidgets.QMenu(self)
        menu.addAction('在LCD上选中', lambda: self.twin_click(x, y))
        menu.addAction('监听已识别的FM', lambda: self.twin_listen(x, y))
        menu.addAction('板端数据快照', lambda: self.send('snapshot'))
        menu.addAction('保存PNG截图', self.screenshot)
        menu.exec(QtGui.QCursor.pos())

    def twin_wheel(self, steps):
        if (self.worker is None or self.worker.session or self.model.hello.get('mode') != 'monitor'):
            return
        current = self._pending_lo if self._pending_lo is not None else self.model.lo
        if current is not None:
            self._pending_lo = max(70000000, min(2700000000, current+steps*100000))
            self.lo_timer.start(500)

    def commit_lo(self):
        if self._pending_lo is not None:
            self.send('set_lo', hz=self._pending_lo)
            self._pending_lo = None

    def set_zoom(self, value):
        self.zoom_level = max(1, min(4, int(value)))
        self.twin_canvas.setFixedSize(800*self.zoom_level, 480*self.zoom_level)
        self.twin_canvas.update()

    def zoom_in(self):
        self.set_zoom(self.zoom_level+1)

    def zoom_out(self):
        self.set_zoom(self.zoom_level-1)

    def show_events(self):
        needle = self.search.text().lower()
        lines = [json.dumps(item, ensure_ascii=False) for item in self.model.events]
        self.events.setPlainText('\n'.join(line for line in lines if needle in line.lower()))

    def load_alarms(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, '选择占用度告警规则', '', 'YAML (*.yaml *.yml)')
        if path:
            try:
                self.alarms = Alarms.load(path)
            except (ValueError,OSError) as error:
                self.status.setText('告警规则无效：'+str(error))

    def select_target(self, row, column):
        if self.worker and not self.worker.session and row < len(self.model.targets):
            self.worker.command('select_target', key=self.model.targets[row]['key'])
            self.worker.command('set_page', page='TGT')

    def record(self):
        if self.recorder:
            self.recorder.close()
            self.recorder = None
            self.status.setText('会话录制已保存')
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '创建新会话录制目录',
            'session_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.zsr', 'ZSR directory (*.zsr)')
        if path:
            self.recorder = Recorder(path, source='replay' if self.worker and self.worker.session else 'live')
            self.status.setText('正在录制 '+path)

    def replay(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, '选择已校验的 .zsr 会话目录')
        if path:
            self.start_worker(session=path)

    def pause(self):
        if self.worker and self.worker.session:
            self.worker.paused = not self.worker.paused

    def speed(self):
        if self.worker and self.worker.session:
            self.worker.speed = 2. if self.worker.speed == 1. else 1.

    def screenshot(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '保存 PNG 截图', 'sentinel.png','PNG (*.png)')
        if path:
            self.grab().save(path)

    def export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '导出目标 CSV', 'targets.csv','CSV (*.csv)')
        if path:
            with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
                fields = ['key','frequency_hz','bandwidth_hz','power','label','confidence','first_seen_mono']
                writer = csv.DictWriter(stream, fields, extrasaction='ignore')
                writer.writeheader(); writer.writerows(self.model.targets)

    def export_iq(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '导出当前 512 点 IQ 快照', 'target.npy','NumPy (*.npy)')
        if path and len(self.model.iq):
            path = Path(path)
            np.save(str(path), self.model.iq, allow_pickle=False)
            self.model.iq.astype('<c8').tofile(path.with_suffix('.cf32'))

    def export_matrix(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '导出演示累计混淆矩阵', 'confusion.png','PNG (*.png)')
        if not path:
            return
        labels = sorted({item for pair in self.model.confusion for item in pair})
        if not labels:
            self.status.setText('没有对应采样的发送真值，不能导出准确率矩阵')
            return
        counts = np.array([[self.model.confusion[(a,b)] for b in labels] for a in labels])
        plot = pg.PlotWidget(title='演示累计，非正式评测 / 行：发送；列：识别')
        plot.addItem(pg.ImageItem(counts, axisOrder='row-major'))
        plot.getAxis('bottom').setTicks([list(enumerate(labels))])
        plot.getAxis('left').setTicks([list(enumerate(labels))])
        pg.exporters.ImageExporter(plot.plotItem).export(path)
        plot.close()

    def fullscreen(self):
        active = not self.isFullScreen()
        self.toolbar.setVisible(not active)
        self.showFullScreen() if active else self.showNormal()

    def closeEvent(self, event):
        self.stop_worker()
        if self.recorder:
            self.recorder.close()
        event.accept()
