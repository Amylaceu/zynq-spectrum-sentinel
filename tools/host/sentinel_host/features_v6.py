"""J6 live feature cards. No fixtures, historic measurements or auto RF start."""
import json
import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .gui import Receiver
from .model import Model
from .twin import Twin
from .shell import AdaptiveCanvas
from .product import STYLE


CARDS = (
    ('F1', '实时频谱与瀑布', '现场 FM 接收 · 实时刷新'),
    ('F2', '测试三音', '理论频点与 PL 检出逐项比对'),
    ('F3', '窗函数切换', 'BH4 / 矩形窗 · 实测主瓣宽度'),
    ('F4', 'Welch 平均', 'AVG_SHIFT · 底噪起伏对比'),
    ('F5', 'CFAR 检测', 'CA / GO / SO · 有界门限调节'),
    ('F6', 'PL 数字注噪', '真实接收 + MODE3 噪声'),
    ('F7', 'PFB + NCO 提取', '16 通道 · 480 kSPS IQ'),
    ('F8', 'FM 广播监听', '解调 / 去加重 / I2S → 喇叭'),
    ('F9', '硬件逐位比对', '本轮输入 8192 字 · 黄金值比对'),
    ('F10', 'FPGA / CPU 计时', '相同 IQ · 分别标注计时范围'),
)


class Window(QtWidgets.QMainWindow):
    def __init__(self, root):
        super().__init__()
        self.root = Path(root)
        self.setWindowTitle('频谱监测终端 · FPGA 功能对比')
        self.resize(1700, 1000)
        self.setStyleSheet(STYLE)
        self.model, self.twin = Model(), Twin()
        self.worker = None
        self.removed = set()
        self.pending = None
        self.target_pending = None
        self.active = None
        self.selected = 'F1'
        self.last_packet = 0.
        self.last_ready_received = 0.
        self.results = []
        self.last_result = None
        self.closing = False
        self.frozen = True
        self.last_count = -1
        self.last_twin = -1
        self.cards = {}
        self.data_errors = []
        central = QtWidgets.QWidget(); outer = QtWidgets.QVBoxLayout(central)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel('频谱监测终端  /  FPGA 典型功能'))
        top.addStretch()
        self.address = QtWidgets.QLineEdit('192.168.2.99'); self.address.setMaximumWidth(160)
        top.addWidget(self.address)
        connect = QtWidgets.QPushButton('连接'); connect.clicked.connect(self.connect_board); top.addWidget(connect)
        self.status = QtWidgets.QLabel('未连接'); top.addWidget(self.status)
        stop = QtWidgets.QPushButton('■ 全部停止  Esc'); stop.clicked.connect(self.stop_feature); top.addWidget(stop)
        outer.addLayout(top)
        self.notice = QtWidgets.QLabel('100 MHz / 3.84 MSPS · S1 接线 · TX 关闭 · 仅现场数据')
        outer.addWidget(self.notice)
        row = QtWidgets.QHBoxLayout()
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumWidth(350); scroll.setMaximumWidth(380)
        self.nav_scroll = scroll
        nav = QtWidgets.QWidget(); nav_layout = QtWidgets.QVBoxLayout(nav)
        nav_layout.setSpacing(5); nav_layout.setContentsMargins(5, 5, 5, 5)
        for identity, title, subtitle in CARDS:
            box = QtWidgets.QFrame(); box.setProperty('card', True)
            layout = QtWidgets.QHBoxLayout(box); layout.setSpacing(4); layout.setContentsMargins(6, 6, 6, 6)
            box.setToolTip(subtitle); box.setFixedHeight(44)
            name = QtWidgets.QLabel(identity+'  '+title); name.setStyleSheet('font-size:14px;'); layout.addWidget(name, 1)
            start = QtWidgets.QPushButton('▶'); start.setToolTip('启动 '+title)
            start.clicked.connect(lambda _, key=identity: self.start_feature(key)); layout.addWidget(start)
            halt = QtWidgets.QPushButton('■'); halt.setToolTip('停止并恢复')
            halt.clicked.connect(self.stop_feature); layout.addWidget(halt)
            for button in (start, halt):
                button.setFixedSize(28, 28); button.setStyleSheet('padding:0px;font-size:15px;')
            lamp = QtWidgets.QLabel('●'); lamp.setStyleSheet('color:#6B7A89;'); layout.addWidget(lamp)
            nav_layout.addWidget(box)
            self.cards[identity] = (box, lamp, start, halt)
        nav_layout.addStretch(); scroll.setWidget(nav); row.addWidget(scroll)
        middle = QtWidgets.QVBoxLayout()
        self.title = QtWidgets.QLabel('选择功能开始现场对比'); middle.addWidget(self.title)
        self.plot = pg.PlotWidget(background='#101E2B'); self.plot.showGrid(x=True, y=True, alpha=.2)
        self.plot.setLabel('bottom', 'FFT bin (shifted)'); self.plot.setLabel('left', '相对整数功率', units='dB')
        self.plot.addLegend()
        self.plot.scene().sigMouseClicked.connect(self.pick_signal)
        self.before = self.plot.plot(pen=pg.mkPen('#D4D8E0', width=3, style=QtCore.Qt.PenStyle.DashLine), name='启动前')
        self.before.setZValue(5)
        self.after = self.plot.plot(pen=pg.mkPen('#66E4D0', width=2), name='启动后 / 现场')
        self.threshold = self.plot.plot(pen=pg.mkPen('#FFC35A', width=1), name='门限（软件重建）')
        self.peaks = self.plot.plot(pen=None, symbol='s', symbolSize=9, symbolPen='#FFD15A')
        middle.addWidget(self.plot, 3)
        self.tabs = QtWidgets.QTabWidget()
        self.water = pg.PlotWidget(background='#101E2B'); self.water_image = pg.ImageItem(axisOrder='row-major'); self.water.addItem(self.water_image)
        self.water_image.setLookupTable(pg.colormap.get('viridis').getLookupTable())
        self.tabs.addTab(self.water, '实时瀑布')
        self.twin_canvas = AdaptiveCanvas(); self.tabs.addTab(self.twin_canvas, 'J22 数字孪生')
        self.twin_canvas.click.connect(self.click_twin)
        self.twin_toggle = QtWidgets.QPushButton('对照 LCD  ·  T')
        self.twin_toggle.clicked.connect(self.toggle_twin); middle.addWidget(self.twin_toggle)
        self.previous_tab = 0
        middle.addWidget(self.tabs, 2); row.addLayout(middle, 1)
        right_widget = QtWidgets.QWidget(); right_widget.setMinimumWidth(480); right_widget.setMaximumWidth(550)
        right = QtWidgets.QVBoxLayout(right_widget)
        right.addWidget(QtWidgets.QLabel('本轮前后对比'))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['指标', '启动前', '启动后', '变化'])
        self.table.setStyleSheet('font-size:17px;')
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(240); self.table.verticalHeader().hide(); right.addWidget(self.table)
        self.state = QtWidgets.QLabel('等待本轮操作'); self.state.setWordWrap(True); right.addWidget(self.state)
        controls = QtWidgets.QHBoxLayout()
        self.cfar_mode = QtWidgets.QComboBox(); self.cfar_mode.addItems(['CA', 'GO', 'SO']); controls.addWidget(self.cfar_mode)
        self.alpha = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal); self.alpha.setRange(256, 8192); self.alpha.setValue(1974); controls.addWidget(self.alpha)
        right.addLayout(controls)
        self.alpha_label = QtWidgets.QLabel('CFAR ALPHA = 1974 (Q8.8)'); right.addWidget(self.alpha_label)
        self.alpha.valueChanged.connect(lambda x: self.alpha_label.setText('CFAR ALPHA = %d (Q8.8)' % x))
        self.alpha.sliderReleased.connect(self.apply_cfar); self.cfar_mode.currentTextChanged.connect(self.apply_cfar)
        self.iq_plot = pg.PlotWidget(background='#101E2B'); self.iq_plot.setTitle('窄带 IQ 星座'); self.iq_scatter = self.iq_plot.plot(pen=None, symbol='o', symbolSize=3)
        right.addWidget(self.iq_plot, 1)
        self.narrow_plot = pg.PlotWidget(background='#101E2B'); self.narrow_plot.setTitle('窄带频谱 / kHz（CPU 显示 FFT）'); self.narrow = self.narrow_plot.plot(pen='#6DE8D3'); right.addWidget(self.narrow_plot, 1)
        self.performance = QtWidgets.QLabel(); self.performance.setWordWrap(True)
        self.performance.setStyleSheet('font-size:25px;color:#66E4D0;'); right.addWidget(self.performance)
        self.scope = QtWidgets.QLabel('ⓘ 说明'); self.scope.setStyleSheet('font-size:15px;color:#A2BDCE;'); right.addWidget(self.scope)
        menu_button = QtWidgets.QPushButton('工具与导出'); menu = QtWidgets.QMenu(self)
        menu.addAction('保存本窗口 PNG', self.save_png)
        menu.addAction('导出本轮结果 JSON', self.export_result)
        menu.addAction('显示本轮 Wi-Fi 名称', self.wifi_names)
        self.tools_menu = menu
        menu_button.setMenu(menu); right.addWidget(menu_button)
        row.addWidget(right_widget); outer.addLayout(row, 1)
        self.setCentralWidget(central)
        QtGui.QShortcut(QtGui.QKeySequence('Escape'), self, activated=self.stop_feature)
        QtGui.QShortcut(QtGui.QKeySequence('T'), self, activated=self.toggle_twin)
        QtGui.QShortcut(QtGui.QKeySequence('F11'), self, activated=lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())
        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(100)

    def connect_board(self):
        if self.worker:
            self.state.setText('已有连接；关闭窗口前会安全停止。'); return
        self.worker = Receiver(address=self.address.text().strip())
        self.worker.packet.connect(self.packet); self.worker.state.connect(self.network_state); self.worker.start()

    def network_state(self, value):
        self.status.setText(value)
        if value.startswith('连接已断开'):
            self.active = None; self.pending = None; self.frozen = True
            self.state.setText('连接中断；硬件状态待重新确认')
            for _, lamp, _, _ in self.cards.values(): lamp.setStyleSheet('color:#6B7A89;')

    def start_feature(self, identity):
        if identity in self.removed:
            self.state.setText('该项未通过连续验收，已移除'); return
        if self.pending or not self.worker or time.monotonic()-self.last_packet > 3:
            self.state.setText('请等待连接或上一命令完成'); return
        self.selected = identity
        self.clear_comparison()
        if self.model.spectrum_count: self.before.setData(np.arange(1024)*2, self.model.power.copy())
        else: self.before.clear()
        self.model.waterfall[:] = -327.68
        self.water_image.clear()
        self.threshold.clear(); self.peaks.clear(); self.iq_scatter.clear(); self.narrow.clear()
        seq = self.worker.command('feature', id=identity, action='start', mode=self.cfar_mode.currentText(), alpha=self.alpha.value())
        self.pending = dict(seq=seq, id=identity, action='start', started=time.monotonic())
        self.title.setText(next(title for key, title, _ in CARDS if key == identity))
        self.state.setText('停止上一功能 → 恢复默认 → 启动本轮…')
        self.frozen = False

    def apply_cfar(self, *_):
        if self.active == 'F5': self.start_feature('F5')

    def stop_feature(self):
        if not self.worker: return
        seq = self.worker.command('feature', id=self.selected, action='stop', mode='CA', alpha=1974)
        self.pending = dict(seq=seq, id=self.selected, action='stop', started=time.monotonic())
        self.state.setText('正在静音、停止、恢复并读回默认值…')

    def click_twin(self, x, y):
        if self.worker and self.active:
            if 560 <= x <= 800 and y < 50:
                self.worker.command('set_page', page=('SIG', 'TGT', 'STAT')[min(2, (x-560)//80)])

    def pick_signal(self, event):
        if self.active != 'F7' or not self.worker or not self.model.targets: return
        point = self.plot.plotItem.vb.mapSceneToView(event.scenePos())
        hz = self.model.hello.get('lo_hz', 96050000)+(point.x()-1024)*1875
        target = min(self.model.targets, key=lambda t: abs(t['frequency_hz']-hz))
        self.target_pending = self.worker.command('select_target', key=target['key'])

    def packet(self, header, payload, received):
        self.last_packet = received
        try:
            self.model.apply(header, payload, received); self.twin.apply(header, payload)
            if (header['type'] in ('reply', 'error') and self.target_pending is not None
                    and header.get('request_seq') == self.target_pending):
                self.target_pending = None
                if not header.get('ok'):
                    self.state.setText('目标提取未完成：'+str(header.get('error', '请重新选取现场目标')))
            if header['type'] == 'reply' and not self.pending and self.active == 'F7' and header.get('feature', {}).get('channel'):
                self.last_result = header['feature']
                self.display_metrics(self.last_result['metrics'])
            if header['type'] == 'telemetry' and not self.pending:
                remote = header.get('scene', 'idle')
                if self.active and remote != self.active and received-self.last_ready_received > 2:
                    self.active = None; self.frozen = True
                    for _, lamp, _, _ in self.cards.values(): lamp.setStyleSheet('color:#6B7A89;')
                    self.state.setText('硬件场景已切换为 '+remote+'；本窗口此前运行状态已撤销')
                if self.active == 'F8' and self.selected == 'F8':
                    audio = header.get('audio', {}); pilot = header.get('pilot') or {}
                    playing = audio.get('output_unmuted', False)
                    self.state.setText('广播播放中' if playing else '信号质量不足 · 自动静音，等待恢复')
                    self.display_metrics({
                        '电台': dict(before='—', after=audio.get('station_hz', 95800000)/1e6, unit='MHz'),
                        '播放样本': dict(before=0, after=audio.get('pcm_samples', 0), unit='样本'),
                        '下溢': dict(before=0, after=audio.get('underflows', 0), unit='次'),
                        '导频突出度': dict(before='—', after=round(pilot.get('pilot_prominence_db', 0), 2), unit='dB')})
                    self.scope.setToolTip('%.3f MHz · 板载喇叭 0 dB。' % (audio.get('station_hz', 95800000)/1e6)+('质量门控已放音。' if playing else '质量门控静音，未降低门限强行出声。')+'导频突出度不是射频信噪比。')
            if header['type'] == 'file' and self.pending and header.get('request_seq') == self.pending['seq']:
                values = np.frombuffer(payload, dtype='<f4')
                if values.size != 2048: raise ValueError('Feature plot must have 2048 bins')
                (self.before if header.get('feature_plot') == 'comparison_power_db' else self.threshold).setData(np.arange(2048), values)
            if header['type'] in ('reply', 'error') and self.pending and header.get('request_seq') == self.pending['seq']:
                pending = self.pending; self.pending = None
                result = dict(header.get('feature') or {})
                if 'status' not in result:
                    result.update(id=pending['id'], status='FAILED',
                        error=header.get('error', 'Missing feature result'))
                result['host_round_trip_s'] = received-pending['started']
                self.last_result = result; self.results.append(result)
                for _, lamp, _, _ in self.cards.values(): lamp.setStyleSheet('color:#6B7A89;')
                if header.get('ok') is True and result.get('status') == 'READY' and result.get('id') == pending['id']:
                    self.active = pending['id']; self.frozen = False
                    self.last_ready_received = received
                    self.cards[self.active][1].setStyleSheet('color:#65E5B1;')
                    self.state.setText('运行中 · %.2f s 就绪' % result['elapsed_s'])
                    if result.get('within_target') is False:
                        self.state.setToolTip('原启动时限未达标；实测 %.2f s' % result['elapsed_s'])
                    self.display_metrics(result.get('metrics', {}))
                    self.scope.setToolTip(self.scope_text(result))
                elif result.get('status') == 'STOPPED' and result.get('restored'):
                    self.active = None; self.frozen = True
                    self.state.setText('已恢复默认 ✓ · 静音 / 源停止 / 画面冻结')
                    if self.closing: QtCore.QTimer.singleShot(0, self.close)
                else:
                    self.active = None; self.frozen = True
                    self.cards[pending['id']][1].setStyleSheet('color:#F16D77;')
                    self.state.setText('未通过'); self.state.setToolTip(str(result.get('error', header.get('error'))))
        except Exception as error:
            self.data_errors.append(repr(error)); self.state.setText('数据错误：'+str(error))

    def scope_text(self, result):
        if result['id'] == 'F10': return '同一输入 IQ。CPU：浮点窗/FFT＋整数门限，不含聚类；PL：首个IQ至目标列表，含串行输入和聚类。倍率仅为所列口径比值，不是等价算法纯计算加速比。'
        if result['id'] == 'F3': return '整数频点三音：矩形窗的主瓣可能更窄。只显示实测变化，不预设结论。'
        if result['id'] == 'F5': return '目标数来自 PL；黄色门限由本轮 PL 功率及当前参数的软件黄金模型重建，非门限寄存器读回。'
        if result['id'] == 'F6': return 'MODE3 对真实 RF 接收加数字噪声；峰值/中位底噪不是标定的射频信噪比。'
        return '本轮真板采集；灰线是启动前快照。停止须完成默认寄存器读回。'

    def display_metrics(self, metrics):
        self.table.setRowCount(len(metrics))
        for row, (key, pair) in enumerate(metrics.items()):
            a, b = pair['before'], pair['after']; change = '→'
            if isinstance(a, (float, int)) and isinstance(b, (float, int)): change = '%+.3g' % (b-a)
            fmt = lambda v: (('%.3f' if pair.get('unit') == 'MHz' else '%.3g') % v
                             if isinstance(v, float) else str(v))
            for col, value in enumerate((key, fmt(a), fmt(b)+' '+pair.get('unit', ''), change)):
                item = QtWidgets.QTableWidgetItem(str(value).replace(',', ', '))
                item.setToolTip(str(value))
                self.table.setItem(row, col, item)
        self.table.resizeRowsToContents()
        if self.selected == 'F10' and '处理时间' in metrics and 'CPU/PL比值' in metrics:
            timing = metrics['处理时间']
            self.performance.setText('CPU %.2f ms │ FPGA %.2f ms\n约 %.1f 倍' %
                (timing['before'], timing['after'], metrics['CPU/PL比值']['after']))

    def clear_comparison(self):
        self.table.setRowCount(0); self.last_result = None
        self.performance.clear(); self.scope.setToolTip(''); self.state.setToolTip('')

    def toggle_twin(self):
        if self.tabs.currentIndex() == 1:
            self.tabs.setCurrentIndex(self.previous_tab)
        else:
            self.previous_tab = self.tabs.currentIndex(); self.tabs.setCurrentIndex(1)
        self.last_twin = -1

    def refresh(self):
        if self.pending:
            self.cards[self.pending['id']][1].setStyleSheet('color:'+('#FFD25B' if int(time.monotonic()*4)%2 else '#76653B')+';')
            limit = 12 if self.pending['id'] in ('F8', 'F10') else 6
            if time.monotonic()-self.pending['started'] > limit:
                self.state.setText('响应超时 · 硬件状态未知，请等待停止确认')
        if not self.frozen and self.model.spectrum_count != self.last_count:
            m = self.model
            self.after.setData(np.arange(1024)*2, m.power)
            # At the measured ~6 spectrum snapshots/s, 24 rows cover ~4 s.
            # Only actual received rows are shown; never fill with fabricated history.
            history = m.waterfall[:min(24, m.spectrum_count)]
            valid = np.flatnonzero(np.any(history != -327.68, axis=1))
            if len(valid):
                self.water_image.setImage(history[:valid[-1]+1], autoLevels=False,
                    levels=(float(np.percentile(m.power, 10))-3, float(m.power.max())+2))
                self.water.setYRange(0, len(valid), padding=0)
                self.water.invertY(True)
            self.last_count = m.spectrum_count
            if self.last_result and self.active == 'F5':
                indices = [t['peak_bin']//2 for t in self.last_result.get('targets', [])]
                self.peaks.setData(np.array(indices)*2, m.power[indices])
        if self.twin.count != self.last_twin:
            self.twin_canvas.set_frame(self.twin.render()); self.last_twin = self.twin.count
        if self.active == 'F7' and len(self.model.iq):
            iq = self.model.iq; self.iq_scatter.setData(iq.real, iq.imag)
            self.narrow.setData(np.fft.fftshift(np.fft.fftfreq(len(iq), 1/480000))/1000, 20*np.log10(np.maximum(np.abs(np.fft.fftshift(np.fft.fft(iq))), 1e-9)))
        if time.monotonic()-self.last_packet > 3 and self.worker:
            self.notice.setText('连接或数据已过期 · 不代表当前硬件状态')
        elif self.model.telemetry:
            t = self.model.telemetry[-1][1]
            fps = '%.1f fps' % t['display_fps'] if not self.frozen and t.get('display_fps', 0) > 0 else '—'
            self.notice.setText('100 MHz / 3.84 MSPS · TX 关闭 · %s · %.1f°C' % (fps, t.get('temperature_c', 0)))

    def wifi_names(self):
        from .product import Window as Product
        Product.open_wifi_names(self)

    def save_png(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '保存本轮截图', 'fpga_comparison.png', 'PNG (*.png)')
        if path: self.grab().save(path)

    def export_result(self):
        from sentinel.release_support import write_result
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '导出本轮结果', 'feature_results.json', 'JSON (*.json)')
        if path: write_result(Path(path), dict(results=self.results))

    def closeEvent(self, event):
        if self.worker and (self.active or self.pending):
            self.closing = True; self.stop_feature(); event.ignore(); return
        if self.worker:
            self.worker.requestInterruption(); self.worker.wait(3000)
        event.accept()
