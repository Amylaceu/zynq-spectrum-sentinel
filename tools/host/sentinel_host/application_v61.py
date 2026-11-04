"""Live application cards; acquisition stays on the board, SSID decoding on PC."""
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from . import features_v6 as base


FPGA_CARDS = (('F0', 'AD9361 接口 PN 自检', 'RX 内部 PN9 · 不发射 · 状态校验'),)+tuple(
    (c[0], '测试三音 + 逐位比对', '三条谱线 · 本轮8192字黄金比对') if c[0] == 'F2' else c
    for c in base.CARDS if c[0] not in ('F3', 'F8', 'F9'))
APP_CARDS = (
    ('F8', '广播收听与换台', '自动搜台 · 手动调谐 · 实时收听'),
    ('F11', '70–512 MHz 全景扫描', '现场逐段扫描 · 最强五个频点'),
    ('F12', '现场电台调制识别', '强台验证 · 五票结果 · 置信度'),
    ('F13', '十类调制现场推理', 'F3 实测空口录波输入 · 本次不发射'),
    ('F14', 'Wi-Fi 名称', 'AD9361 实采 · 电脑解码信标'),
)
base.CARDS = FPGA_CARDS+APP_CARDS
APP_IDS = {'F0'} | {c[0] for c in APP_CARDS}
RECORDING_AVAILABLE = False  # Three integrated board trials overflowed; retain diagnostics only.
RECORDING_UNAVAILABLE = '同步录音未通过连续采集验收；广播收听、搜台和换台可用'


def fetch_current(root, address, data, kind):
    """Copy only the exact per-request directory; no historic file picker."""
    run_id, remote = data['run_id'], data['remote_raw']
    if not re.fullmatch(r'[0-9a-f]{32}', run_id) or not re.fullmatch(
            r'/home/xilinx/sentinel/release/[a-z0-9_]+/measurements/[a-z0-9_]+/application_'+run_id+r'/raw', remote):
        raise ValueError('Unexpected acquisition identity/path')
    if not re.fullmatch(r'[a-zA-Z0-9.:-]+', address): raise ValueError('Invalid board address')
    output = Path(root)/'board/measurements'/('j7_'+kind+'_'+run_id)
    output.mkdir(parents=True, exist_ok=False)
    with (output/'transfer.log').open('xb') as log:
        subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=8', '-r', 'xilinx@'+address+':'+remote, str(output/'raw')],
            check=True, stdout=log, stderr=subprocess.STDOUT, timeout=240,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return output


class AudioDecode(QtCore.QThread):
    complete = QtCore.Signal(object)

    def __init__(self, root, address, data):
        super().__init__(); self.root, self.address, self.data = Path(root), address, data

    def run(self):
        sys.path.insert(0, str(self.root/'tools'))
        from x2_transport import verified, sha, write_evidence
        from current_fm_audio import decode_current_owner
        try:
            output = fetch_current(self.root, self.address, self.data, 'recording')
            raw = verified(output/'raw/result.json')
            if raw['session_id'] != self.data['run_id'] or sha(output/'raw/result.json') != self.data['capture_sha256']:
                raise ValueError('Recording identity/digest differs')
            write_evidence(output/'validation.json', dict(source='RESIDENT_OWNER_STOPPED_RECORDING',
                session_id=raw['session_id'], capture_sha256=sha(output/'raw/result.json')))
            _, result = decode_current_owner(output, raw['session_id'])
            self.complete.emit(dict(result=result, directory=str(output), session_id=raw['session_id']))
        except Exception as error:
            self.complete.emit(dict(result=dict(status='FAIL', error=repr(error))))


class WifiDecode(QtCore.QThread):
    progress = QtCore.Signal(str)
    complete = QtCore.Signal(object)

    def __init__(self, root, address, data):
        super().__init__()
        self.root, self.address, self.data = Path(root), address, data

    def run(self):
        sys.path.insert(0, str(self.root/'tools'))
        from x2_transport import verified, sha, write_evidence
        from j_ssid_decode import decode
        try:
            run_id = self.data['run_id']
            remote = self.data['remote_raw']
            if not re.fullmatch(r'[0-9a-f]{32}', run_id) or not re.fullmatch(
                    r'/home/xilinx/sentinel/release/[a-z0-9_]+/measurements/[a-z0-9_]+/application_'+run_id+r'/raw', remote):
                raise ValueError('Unexpected acquisition path')
            if not re.fullmatch(r'[a-zA-Z0-9.:-]+', self.address):
                raise ValueError('Invalid board address')
            output = self.root/'board/measurements'/('j61_wifi_'+run_id)
            output.mkdir(parents=True, exist_ok=False)
            self.progress.emit('正在取回本轮 IQ，随后解码 Wi-Fi 名称…')
            with (output/'transfer.log').open('xb') as log:
                subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'ConnectTimeout=8', '-r', 'xilinx@'+self.address+':'+remote, str(output/'raw')],
                    check=True, stdout=log, stderr=subprocess.STDOUT, timeout=240,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            raw = verified(output/'raw/result.json')
            if raw['session_id'] != run_id or sha(output/'raw/result.json') != self.data['capture_sha256']:
                raise ValueError('Acquisition identity or digest differs')
            write_evidence(output/'validation.json', dict(status=raw['status'], session_id=run_id,
                boot_id=raw['boot_id'], capture_sha256=sha(output/'raw/result.json'),
                capture_ended_host_utc=self.data['received_utc']))
            self.progress.emit('AD9361 已完成采集并恢复基线，电脑正在解码信标…')
            result = decode(output, output/'decoded', run_id)
            self.complete.emit(dict(result=result, path=str(output/'decoded/result.json')))
        except Exception as error:
            self.complete.emit(dict(result=dict(status='FAIL', error=repr(error))))


class Window(base.Window):
    def __init__(self, root):
        super().__init__(root)
        self.setWindowTitle('频谱监测终端 · FPGA 与应用功能')
        self.app_run = None
        self.app_identity = None
        self.app_history = []
        self.wifi_worker = None
        self.wifi_ignored = False
        self.wifi_result = None
        self.wifi_elapsed = None
        self.wifi_progress = '就绪'
        self.wifi_capture_result = None
        self.f12_eligible = []
        self.f12_counts = {}
        self.app_busy = False
        self.wifi_locked = False
        self.wifi_started = None
        self.after_stop = None
        self.audio_worker = None
        self.audio_dialog = None
        self.current_audio = None
        self.found_stations = []
        self.last_fm_frequency = 95800000
        nav_layout = self.cards['F1'][0].parentWidget().layout()
        nav_layout.insertWidget(0, QtWidgets.QLabel('FPGA 信号处理'))
        nav_layout.insertWidget(nav_layout.indexOf(self.cards['F8'][0]), QtWidgets.QLabel('应用功能'))
        # Expand the existing result area without changing the LCD renderer.
        panel = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(panel)
        self.app_caption = QtWidgets.QLabel('选择应用功能并启动'); self.app_caption.setWordWrap(True)
        layout.addWidget(self.app_caption)
        self.progress_bar = QtWidgets.QProgressBar(); layout.addWidget(self.progress_bar)
        self.app_plot = pg.PlotWidget(background='#101E2B'); self.app_plot.showGrid(x=True, y=True, alpha=.2)
        layout.addWidget(self.app_plot, 2)
        self.app_table = QtWidgets.QTableWidget(0, 0)
        self.app_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.app_table.cellDoubleClicked.connect(self.select_scan_target)
        layout.addWidget(self.app_table, 1)
        self.app_tab = self.tabs.addTab(panel, '应用现场结果')
        self.app_controls = {}
        self.control_layouts = {}
        for identity in ('F8', 'F12', 'F14'):
            controls = QtWidgets.QWidget(); controls_layout = QtWidgets.QVBoxLayout(controls)
            controls_layout.setContentsMargins(0, 0, 0, 0)
            layout.insertWidget(1, controls)
            self.app_controls[identity] = controls; self.control_layouts[identity] = controls_layout
        self.station = QtWidgets.QComboBox(); self.station.addItem('95.800 MHz（启动时复核）', 95800000)
        self.station.activated.connect(self.change_station)
        self.control_layouts['F8'].addWidget(self.station)
        tune = QtWidgets.QHBoxLayout()
        self.manual_frequency = QtWidgets.QDoubleSpinBox(); self.manual_frequency.setRange(87.5, 108)
        self.manual_frequency.setDecimals(1); self.manual_frequency.setSingleStep(.1)
        self.manual_frequency.setValue(95.8); self.manual_frequency.setSuffix(' MHz'); tune.addWidget(self.manual_frequency)
        manual = QtWidgets.QPushButton('调谐'); manual.clicked.connect(self.manual_tune); tune.addWidget(manual)
        self.control_layouts['F8'].addLayout(tune)
        search = QtWidgets.QPushButton('搜索 87.5–108 MHz 可用电台')
        search.setToolTip('搜台需要独占接收机，约30秒；请先停止广播。搜索完成后保留原收听频率，换台请明确选择。')
        search.clicked.connect(lambda: self.begin_application('F8', 'search'))
        self.control_layouts['F8'].addWidget(search)
        self.record_buttons = {}
        for text, callback in (('开始录制（最多3秒）', lambda: self.begin_application('F8', 'record')),
                ('停止录制', self.stop_recording), ('播放本次录音', self.play_recording),
                ('返回实时收听', self.return_live)):
            button = QtWidgets.QPushButton(text); button.clicked.connect(callback)
            self.control_layouts['F8'].addWidget(button); self.record_buttons[text] = button
        self.record_buttons['播放本次录音'].setEnabled(False)
        for button in self.record_buttons.values():
            button.setEnabled(False)
            button.hide()
        self.fm_station = QtWidgets.QComboBox(); self.fm_station.addItem('启动后进行十次资格检查', 0)
        self.control_layouts['F12'].addWidget(self.fm_station)
        self.antenna = QtWidgets.QCheckBox('RX1A 已接 2.4GHz 天线，热点已开启')
        self.antenna.setStyleSheet('font-size:12px;')
        self.control_layouts['F14'].addWidget(self.antenna)
        self.antenna.hide()
        self.ssid_filter = QtWidgets.QLineEdit(); self.ssid_filter.setPlaceholderText('输入热点名以高亮')
        self.ssid_filter.textChanged.connect(self.highlight_ssid)
        self.control_layouts['F14'].addWidget(self.ssid_filter)
        restore = QtWidgets.QPushButton('确认已换回广播天线')
        restore.clicked.connect(self.restore_antenna); self.control_layouts['F14'].addWidget(restore)
        recapture = QtWidgets.QPushButton('重新采集 Wi-Fi')
        recapture.clicked.connect(lambda: self.start_feature('F14', action='recapture'))
        self.control_layouts['F14'].addWidget(recapture)
        diagnostics = self.tools_menu.addMenu('诊断')
        diagnostics.addAction('F12 电台识别资格检查', lambda: self.start_feature('F12'))
        self.cards['F12'][0].setToolTip('启动后对本轮搜到的电台做十次质量与识别检查；无合格台时自动移入诊断，不显示单帧标签。')
        self.scan_points = []
        self.fm_scan_points = []
        self.scan_labels = []
        self.scan_label_y = -float('inf')
        self.panel_for('F1')

    def panel_for(self, identity):
        self.selected = identity
        self.plot.setVisible(identity not in APP_IDS)
        self.app_plot.setVisible(identity in ('F11', 'F13'))
        for key, controls in self.app_controls.items(): controls.setVisible(key == identity)
        for widget in (self.cfar_mode, self.alpha, self.alpha_label): widget.setVisible(identity == 'F5')
        for widget in (self.iq_plot, self.narrow_plot): widget.setVisible(identity == 'F7')
        self.table.setMaximumHeight(240 if identity in ('F7', 'F12') else 10000)

    def network_state(self, value):
        super().network_state(value)
        if value.startswith('连接已断开'):
            self.app_busy = False
            self.after_stop = None
            self.app_run = None
            self.wifi_started = None
            self.app_caption.setText('连接中断；本轮任务状态未知，未完成的录音或采集不作通过')

    def restore_antenna(self):
        if self.active or self.pending or self.app_busy:
            self.state.setText('先停止当前功能，确认停止后再换天线'); return False
        if not self.wifi_locked: return True
        answer = QtWidgets.QMessageBox.question(self, '恢复广播接收天线',
            '请确认 RX1A 已换回 20–512 MHz 磁吸天线。保持供电，不复位。\n是否已完成？',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes: return False
        self.wifi_locked = False; self.antenna.setChecked(False)
        self.wifi_unlocked_mono = time.monotonic()
        self.state.setText('低频天线已确认，接收卡片已解锁'); return True

    def wifi_confirmation(self):
        answer = QtWidgets.QMessageBox.question(self, 'Wi-Fi 接收天线确认',
            '射频已停止。请把 TX1A 的 2.4 GHz 胶棒拧到 RX1A（TX1A 空着），'
            '打开手机 2.4GHz 热点，放在约0.5米处。\n换好后选 Yes 继续；未换好选 No。',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self.wifi_locked = True; self.antenna.setChecked(True); self.start_feature('F14')

    def begin_application(self, identity, action='start', frequency=None):
        return self.start_feature(identity, action=action, frequency=frequency)

    def manual_tune(self):
        self.start_feature('F8', frequency=round(self.manual_frequency.value()*1e6))

    def stop_recording(self):
        if not RECORDING_AVAILABLE: return
        if self.worker and self.app_busy and self.app_identity == 'F8':
            self.worker.command('application', id='F8', action='record_stop', station_hz=0, antenna_2g4=False)

    def play_recording(self):
        if not RECORDING_AVAILABLE:
            self.state.setText(RECORDING_UNAVAILABLE); return
        if not self.current_audio or self.active or self.pending or self.app_busy:
            self.state.setText('等待本轮录音校验完成并停止广播'); return
        from .current_audio import CurrentAudioDialog
        self.audio_dialog = CurrentAudioDialog(self.current_audio['directory'], self.current_audio['session_id'], self)
        self.audio_dialog.show(); self.audio_dialog.play_current()

    def return_live(self):
        if self.audio_dialog: self.audio_dialog.close(); self.audio_dialog = None
        frequency = self.current_audio['result'].get('station_hz') if self.current_audio else None
        self.start_feature('F8', frequency=frequency)

    def audio_complete(self, value):
        self.app_history.append(dict(stage='audio_decode', **value))
        good = RECORDING_AVAILABLE and value['result']['status'] == 'READY_FOR_LISTENING'
        self.current_audio = value if good else None
        self.record_buttons['播放本次录音'].setEnabled(good)
        self.app_caption.setText('本轮录音校验完成；同一时段 RX1 IQ 软件 FM 解调，可播放本次录音' if good else
            '本轮录音拒绝播放：'+str(value['result'].get('error', value['result']['status'])))

    def highlight_ssid(self):
        from PySide6 import QtGui
        query = self.ssid_filter.text().strip().casefold()
        if self.selected != 'F14': return
        for row in range(self.app_table.rowCount()):
            match = bool(query and query in self.app_table.item(row, 0).text().casefold())
            for col in range(self.app_table.columnCount()):
                self.app_table.item(row, col).setBackground(QtGui.QColor('#3C5931' if match else '#101E2B'))

    def start_feature(self, identity, action='start', frequency=None):
        if identity == 'F8' and action == 'search' and self.active == 'F8':
            self.state.setText('搜台会中断广播约30秒；请先点击停止，再搜台。')
            return
        if identity == 'F8' and action in ('record', 'record_stop') and not RECORDING_AVAILABLE:
            self.state.setText(RECORDING_UNAVAILABLE); return
        if self.app_busy:
            self.state.setText('当前有限任务执行中；请先停止，再启动其他功能'); return
        if self.audio_worker and self.audio_worker.isRunning():
            self.state.setText('正在取回并校验本轮录音，请稍等'); return
        if self.audio_dialog: self.audio_dialog.close(); self.audio_dialog = None
        if identity == 'F14' and action == 'start' and (self.wifi_result is not None or
                self.wifi_worker and self.wifi_worker.isRunning()):
            self.panel_for('F14'); self.clear_comparison(); self.tabs.setCurrentIndex(self.app_tab)
            self.title.setText('Wi-Fi 名称'); self.render_wifi(); return
        if identity == 'F14' and self.wifi_worker and self.wifi_worker.isRunning():
            self.state.setText('解码进行中'); return
        if self.wifi_locked and identity not in ('F0', 'F2', 'F10', 'F13', 'F14') and not self.restore_antenna(): return
        if self.pending or not self.worker or time.monotonic()-self.last_packet > 3:
            self.state.setText('请等待连接或上一命令完成'); return
        self.panel_for(identity)
        if identity not in APP_IDS:
            self.app_run = None; self.app_identity = None
            self.tabs.setCurrentIndex(0)
            return super().start_feature(identity)
        if self.pending or not self.worker or time.monotonic()-self.last_packet > 3:
            self.state.setText('请等待连接或上一命令完成'); return
        if identity == 'F14' and not self.antenna.isChecked():
            self.after_stop = self.wifi_confirmation
            self.stop_feature(); return
        if identity == 'F14':
            self.wifi_started = time.monotonic(); self.wifi_result = None; self.wifi_capture_result = None
            self.wifi_progress = '采集中'; action = 'start'
        self.selected = identity
        self.clear_comparison()
        if frequency is None:
            frequency = int(self.station.currentData() or 0) if identity == 'F8' else int(self.fm_station.currentData() or 0) if identity == 'F12' else 0
        if action == 'record':
            self.current_audio = None; self.record_buttons['播放本次录音'].setEnabled(False)
        if self.model.spectrum_count: self.before.setData(np.arange(1024)*2, self.model.power.copy())
        else: self.before.clear()
        self.model.waterfall[:] = -327.68
        seq = self.worker.command('application', id=identity, action=action, station_hz=frequency,
                                  antenna_2g4=identity == 'F14' and self.antenna.isChecked())
        self.pending = dict(seq=seq, id=identity, action='start', started=time.monotonic())
        self.app_identity = identity; self.app_run = None; self.scan_points = []
        self.app_plot.clear(); self.app_table.clear(); self.app_table.setRowCount(0)
        self.scan_labels = []; self.scan_label_y = -float('inf')
        if identity == 'F11':
            for start, end, label, color in ((88, 108, 'FM 广播', '#264D43'),
                    (118, 137, '航空', '#3B4059'), (144, 148, '业余', '#50452C'),
                    (400, 470, '对讲 / 专网', '#403858')):
                band = pg.LinearRegionItem((start, end), movable=False, brush=color)
                band.setZValue(-10); self.app_plot.addItem(band)
                tag = pg.TextItem(label, color='#D8E5F1', anchor=(0, 1))
                tag.setPos(start, -50); self.app_plot.addItem(tag)
                self.scan_labels.append((start, tag))
        self.progress_bar.setValue(0); self.tabs.setCurrentIndex(self.app_tab)
        self.progress_bar.setFormat('%p%')
        self.frozen = True
        self.title.setText(next(t for key, t, _ in base.CARDS if key == identity))
        self.app_caption.setText('输入：F3 实测空口录波 · 开发板现场推理 · 本次不发射' if identity == 'F13' else '正在开始本轮采集…')

    def stop_feature(self):
        if self.audio_dialog: self.audio_dialog.close(); self.audio_dialog = None
        if self.selected not in APP_IDS: return super().stop_feature()
        if not self.worker: return
        seq = self.worker.command('application', id=self.selected, action='stop', station_hz=0, antenna_2g4=False)
        self.pending = dict(seq=seq, id=self.selected, action='stop', started=time.monotonic())
        self.state.setText('正在停止并读回基线…')

    def change_station(self, *_):
        if self.active == 'F8': self.start_feature('F8')

    def select_scan_target(self, row, column):
        points = self.fm_scan_points if column == 0 else self.scan_points
        if self.selected != 'F11' or row >= len(points): return
        hz = points[row]['frequency_hz']
        nearest = next((v for v in self.f12_eligible if abs(v-hz) <= 100000), None)
        if nearest is None:
            self.state.setText('此峰尚未通过强台及十次FM资格检查，不显示自动识别标签')
            return
        self.fm_station.setCurrentIndex(self.fm_station.findData(nearest))
        self.start_feature('F12')

    def show_rows(self, columns, rows):
        self.app_table.setColumnCount(len(columns)); self.app_table.setHorizontalHeaderLabels(columns)
        self.app_table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value)); item.setToolTip(str(value))
                self.app_table.setItem(r, c, item)
        self.app_table.resizeRowsToContents()

    def packet(self, header, payload, received):
        if header['type'] == 'file' and header.get('application_data'):
            self.last_packet = received
            try:
                data = json.loads(payload)
                if data['run_id'] != self.app_run: return
                self.app_history.append(data)
                self.application_data(data)
            except Exception as error:
                self.data_errors.append(repr(error)); self.state.setText('应用数据错误：'+str(error))
            return
        if (header['type'] == 'reply' and self.pending
                and header.get('request_seq') == self.pending['seq']
                and header.get('feature', {}).get('application_pending')):
            self.app_run = header['feature']['run_id']
            self.app_busy = True; self.last_packet = received
            self.pending = None; self.active = self.app_identity
            self.cards[self.app_identity][1].setStyleSheet('color:#FFD25B;')
            self.state.setText('任务已接收，执行中；尚未完成验收')
            return
        stopped_reply = (header['type'] == 'reply' and self.pending is not None
            and header.get('request_seq') == self.pending['seq']
            and self.pending['action'] == 'stop'
            and header.get('feature', {}).get('status') == 'STOPPED'
            and header['feature'].get('restored'))
        super().packet(header, payload, received)
        if self.after_stop and stopped_reply:
            callback, self.after_stop = self.after_stop, None
            QtCore.QTimer.singleShot(0, callback)
        if self.active in ('F11', 'F12', 'F13', 'F14'):
            self.frozen = True

    def application_data(self, data):
        stage = data['stage']
        if 'completed' in data:
            self.progress_bar.setValue(round(100*data['completed']/data['total']))
        if stage == 'stations':
            choice = data['selection']; self.station.blockSignals(True); self.station.clear()
            rows = []
            for c in choice['candidates']:
                s = c['station']; pilot = float(np.median([m['quality']['pilot_prominence_db'] for m in c['measurements']]))
                winner = choice['selected'] == s
                rows.append(['%.3f MHz' % (s['frequency_hz']/1e6), '%.2f dB' % pilot,
                    '%.2f' % c['median_iq_power'], '质量通过且功率最强' if winner else '质量通过' if c['trusted'] else '质量未通过'])
                if c['trusted']: self.station.addItem('%.3f MHz' % (s['frequency_hz']/1e6), s['frequency_hz'])
            for station in self.found_stations:
                if self.station.findData(station['frequency_hz']) < 0:
                    self.station.addItem('%.3f MHz' % (station['frequency_hz']/1e6), station['frequency_hz'])
            if choice['selected']:
                self.station.setCurrentIndex(self.station.findData(choice['selected']['frequency_hz']))
            self.station.blockSignals(False)
            self.show_rows(['电台', '导频突出度', '相对IQ功率', '选台理由'], rows)
            self.app_caption.setText('候选按本轮导频及质量检查筛选；相对IQ功率不是校准射频功率')
        elif stage == 'fm_search':
            self.app_caption.setText('正在搜索87.5–108 MHz：%.0f%%，待复核候选%d个' %
                (100*data['completed']/data['total'], data['candidates']))
        elif stage == 'found_stations':
            previous = int(self.station.currentData() or self.last_fm_frequency)
            self.found_stations = data['stations']; self.station.blockSignals(True); self.station.clear()
            for station in self.found_stations:
                self.station.addItem('%.3f MHz' % (station['frequency_hz']/1e6), station['frequency_hz'])
            if self.station.findData(previous) < 0:
                self.station.addItem('%.3f MHz（原频率，启动时复核）' % (previous/1e6), previous)
            self.station.setCurrentIndex(self.station.findData(previous))
            self.station.blockSignals(False)
            self.show_rows(['质量复核通过频率', '接收本振'], [['%.3f MHz' % (s['frequency_hz']/1e6),
                '%.3f MHz' % (s['lo_hz']/1e6)] for s in self.found_stations])
            self.app_caption.setText('搜台结束：%d个频率通过质量检查，可从下拉框选择收听；不代表已确认电台名称' % len(self.found_stations))
        elif stage == 'bist':
            self.show_rows(['通道', 'PN错误标志', '失步标志', '原始状态'],
                [[i, (v >> 2) & 1, (v >> 1) & 1, hex(v)] for i, v in enumerate(data['channel_status'])])
            self.display_metrics({'检查时间': dict(before='—', after=data['duration_ms'], unit='ms'),
                'PN错误标志': dict(before='—', after=str([(v >> 2) & 1 for v in data['channel_status']]), unit=''),
                '失步标志': dict(before='—', after=str([(v >> 1) & 1 for v in data['channel_status']]), unit='')})
            self.app_caption.setText('四路 PN 自检完成')
            self.scope.setToolTip('RX内部PN9状态校验；硬件未提供实际比较字数或逐位错误计数，名义样本数按采样率×时间计算。')
        elif stage == 'recording':
            self.app_caption.setText('广播同步录制：约%.1f秒 / 3秒上限，完成块 %d/%d' %
                (data['sampled_s'], data['completed'], data['total']))
        elif stage == 'recorded':
            self.app_caption.setText('广播已静音；正在取回本轮IQ并解调、校验录音…')
            self.audio_worker = AudioDecode(self.root, self.address.text().strip(), data)
            self.audio_worker.complete.connect(self.audio_complete); self.audio_worker.start()
        elif stage == 'audio_ready':
            self.display_metrics(data['feature']['metrics'])
        elif stage == 'scan_tile':
            self.app_plot.setLabel('bottom', '频率', units='MHz')
            self.app_plot.setLabel('left', '功率谱密度', units='dBFS/Hz')
            self.app_plot.plot(np.asarray(data['frequency_hz'])/1e6, data['power_db'], pen='#66E4D0')
            self.scan_label_y = max(self.scan_label_y, max(data['power_db'])+3)
            for frequency, tag in self.scan_labels: tag.setPos(frequency, self.scan_label_y)
            remaining = data.get('elapsed_s', 0)*(data['total']-data['completed'])/max(1, data['completed'])
            self.app_caption.setText('现场扫描 %d/%d 段%s' % (data['completed'], data['total'],
                ' · 预计剩余 %.0f 秒' % remaining if remaining else ''))
        elif stage == 'qualifying':
            self.app_caption.setText('%.3f MHz 正在做十次质量与FM识别资格检查：%d/10' % (data['frequency_hz']/1e6, data['completed']))
        elif stage == 'qualification':
            self.f12_eligible = data['eligible']; self.fm_station.clear()
            self.f12_counts = {s['station']['frequency_hz']:
                sum(t['label'] == 'FM' and t['confidence'] >= .5 for t in s['trials'])
                for s in data['stations']}
            for hz in self.f12_eligible: self.fm_station.addItem('%.3f MHz' % (hz/1e6), hz)
            rows = [['%.3f MHz' % (s['station']['frequency_hz']/1e6),
                sum(t['label'] == 'FM' and t['confidence'] >= .5 for t in s['trials']),
                sum(bool(t['quality_pass']) for t in s['trials']),
                '通过' if s['station']['frequency_hz'] in self.f12_eligible else '未通过'] for s in data['stations']]
            self.show_rows(['电台', 'FM次数 / 10', '质量通过 / 10', '汇总'], rows)
            self.cards['F12'][0].setVisible(bool(self.f12_eligible))
            if self.f12_eligible:
                self.fm_station.setCurrentIndex(0)
                self.display_metrics({'电台': dict(before='—', after=self.f12_eligible[0]/1e6, unit='MHz'),
                    'FM次数': dict(before='—', after=next(r[1] for r in rows if r[0] == '%.3f MHz' % (self.f12_eligible[0]/1e6)), unit='/10')})
            self.app_caption.setText('通过电台：'+(', '.join('%.3f MHz' % (hz/1e6) for hz in self.f12_eligible) or '无；不显示确定识别标签'))
        elif stage == 'vote':
            vote = data['vote']
            self.app_caption.setText('五票结果：%s · %.1f%% · 本次处理 %.1f ms' % (vote['label'], vote['confidence']*100, data['latency_ms']))
            self.show_rows(['Top-5 大类', '五帧平均概率'], [[v['label'], '%.1f%%' % (v['score']*100)] for v in vote['top5']])
            self.display_metrics({'电台': dict(before='—', after=data.get('frequency_hz', self.fm_station.currentData() or 0)/1e6, unit='MHz'),
                '五票结果': dict(before='—', after=vote['label'], unit=''),
                '十次FM次数': dict(before='—', after=self.f12_counts.get(data.get('frequency_hz', self.fm_station.currentData()), '—'), unit='/10'),
                '置信度': dict(before='—', after=vote['confidence']*100, unit='%')})
        elif stage == 'confusion':
            self.app_plot.clear()
            matrix = np.asarray(data['confusion_10'])
            image = pg.ImageItem(matrix, axisOrder='row-major'); image.setLookupTable(pg.colormap.get('viridis').getLookupTable())
            self.app_plot.addItem(image)
            self.app_plot.getAxis('bottom').setTicks([list(enumerate(data['labels']))])
            self.app_plot.getAxis('left').setTicks([list(enumerate(data['labels']))])
            self.app_plot.setLabel('bottom', '预测'); self.app_plot.setLabel('left', '输入类别')
            self.display_metrics({'已推理': dict(before=0, after=data['completed'], unit='条'),
                '十类准确率': dict(before='—', after=round(data['accuracy_10']*100, 2), unit='%'),
                '八大类准确率': dict(before='—', after=round(data['accuracy_8']*100, 2), unit='%')})
        elif stage == 'wifi_capture':
            self.app_caption.setText('正在通过AD9361采集信道 %d · %d/%d' % (data['channel'], data['completed'], data['total']))
        elif stage == 'wifi_captured':
            data['received_utc'] = datetime.now(timezone.utc).isoformat()
            self.wifi_capture_received_mono = time.monotonic()
            self.wifi_ignored = False
            self.wifi_worker = WifiDecode(self.root, self.address.text().strip(), data)
            self.wifi_worker.progress.connect(self.wifi_progress_changed)
            self.wifi_worker.complete.connect(self.wifi_complete)
            self.wifi_worker.start()
        elif stage == 'finished':
            result = data['result']; self.last_result = result; self.results.append(result)
            self.app_busy = False
            self.cards[data['id']][1].setStyleSheet('color:'+('#65E5B1' if result['status'] == 'DONE' else '#F16D77')+';')
            self.state.setText('%s · %.2f s%s' % ({'DONE': '完成', 'CANCELLED': '已停止'}.get(result['status'], '未通过'), result['elapsed_s'],
                ' · 已恢复默认' if result.get('restored') else ''))
            self.state.setToolTip(json.dumps(result, ensure_ascii=False))
            if result.get('restored'): self.active = None; self.frozen = True
            elif result['status'] == 'DONE' and data['id'] in ('F8', 'F12'):
                self.active = data['id']; self.frozen = data['id'] != 'F8'
                self.last_ready_received = time.monotonic()
                if data['id'] == 'F8':
                    station = result.get('selection', {}).get('selected')
                    if station:
                        self.last_fm_frequency = int(station['frequency_hz'])
                        self.manual_frequency.setValue(self.last_fm_frequency/1e6)
            if data['id'] == 'F11' and 'strongest' in result:
                self.scan_points = result['strongest']
                fm = result.get('fm_strongest', [])
                self.fm_scan_points = fm
                point = lambda p: '%.3f MHz · %.1f dBFS/Hz' % (p['frequency_hz']/1e6, p['power_db'])
                self.show_rows(['FM 广播段最强 5 个', '全频段最强 5 个'],
                    [[point(fm[i]) if i < len(fm) else '—', point(self.scan_points[i]) if i < len(self.scan_points) else '—']
                     for i in range(max(len(fm), len(self.scan_points)))])
                self.app_caption.setText('现场扫描完成 · %.2f 秒' % result['elapsed_s'])
                self.display_metrics({'扫描范围': dict(before='—', after='70–512', unit='MHz'),
                    '段数': dict(before='—', after=result.get('tiles', '—'), unit='段'),
                    '用时': dict(before='—', after=result['elapsed_s'], unit='秒'),
                    '最强频点': dict(before='—', after=self.scan_points[0]['frequency_hz']/1e6 if self.scan_points else '—', unit='MHz')})
            if data['id'] == 'F14':
                self.wifi_capture_result = result
                if result.get('restored') and self.wifi_locked:
                    self.wifi_prompt_scheduled_mono = time.monotonic()
                    QtCore.QTimer.singleShot(0, self.restore_antenna)
            if data['id'] == 'F13' and 'exact_predictions' in result:
                self.table.insertRow(self.table.rowCount())
                row = self.table.rowCount()-1
                for col, text in enumerate(('与参考一致', '—', '是' if result['exact_predictions'] and result['exact_confusion'] else '否', '')):
                    self.table.setItem(row, col, QtWidgets.QTableWidgetItem(text))
            if result.get('error'):
                self.app_caption.setText('未通过'); self.app_caption.setToolTip(result['error'])

    def wifi_complete(self, value):
        elapsed = time.monotonic()-self.wifi_started if self.wifi_started is not None else None
        self.wifi_started = None
        if self.wifi_ignored: return
        result = value['result']; self.app_history.append(dict(stage='wifi_decode', **value))
        self.wifi_result = result; self.wifi_elapsed = elapsed
        self.wifi_progress = '未通过' if result.get('error') or result['status'] == 'FAIL' else '结果就绪'
        self.cards['F14'][1].setToolTip(self.wifi_progress)
        if self.selected == 'F14': self.render_wifi()
        self.update_wifi_lamp()

    def wifi_progress_changed(self, text):
        self.wifi_progress = text
        if self.selected == 'F14': self.app_caption.setText(text)

    def update_wifi_lamp(self):
        if self.wifi_result is not None:
            self.cards['F14'][1].setStyleSheet('color:'+('#F16D77' if self.wifi_progress == '未通过' else '#65E5B1')+';')
            self.cards['F14'][0].findChildren(QtWidgets.QLabel)[0].setText('F14  Wi-Fi 名称 · '+self.wifi_progress)
        elif self.wifi_worker and self.wifi_worker.isRunning():
            self.cards['F14'][1].setStyleSheet('color:#FFD25B;')
            self.cards['F14'][0].findChildren(QtWidgets.QLabel)[0].setText('F14  Wi-Fi 名称 · 解码中')

    def render_wifi(self):
        self.app_plot.hide()
        if self.wifi_result is None:
            self.app_table.setRowCount(0); self.app_caption.setText(self.wifi_progress)
            return
        result, elapsed = self.wifi_result, self.wifi_elapsed
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat('处理结束'+(' · 总用时 %.0f 秒' % elapsed if elapsed is not None else ''))
        networks = result.get('networks', [])
        self.display_metrics({
            '有效网络记录': dict(before='—', after=len(networks), unit='条'),
            'FCS通过信标': dict(before='—', after=sum(v['valid_beacons'] for v in networks), unit='帧'),
            '信道数': dict(before='—', after=len((self.wifi_capture_result or {}).get('capture', {}).get('channels', [])) or '—', unit='个'),
            '用时': dict(before='—', after=elapsed if elapsed is not None else '—', unit='秒')})
        self.show_rows(['Wi-Fi名称', 'BSSID', '信道', '有效信标', '相对强度/dBFS'],
            [[v['ssid'] or '隐藏SSID', v['bssid'], v['advertised_channel'], v['valid_beacons'],
              '%.1f' % v['relative_strength_dbfs'] if v.get('relative_strength_dbfs') is not None else '—']
             for v in result.get('networks', [])])
        self.app_caption.setText(self.wifi_progress)
        self.scope.setToolTip('AD9361 RX1A采集 → PC解码；强度为有效信标头的ADC相对功率，受增益影响，非校准dBm。'+
            str(result.get('error', result['status'])))
        self.highlight_ssid()
        self.state.setText(self.wifi_progress)

    def refresh(self):
        super().refresh()
        self.update_wifi_lamp()
        if self.app_busy and self.app_identity in self.cards:
            self.cards[self.app_identity][1].setStyleSheet('color:'+('#FFD25B' if int(time.monotonic()*4)%2 else '#76653B')+';')
        if self.active == 'F12' and len(self.model.iq):
            self.iq_scatter.setData(self.model.iq.real, self.model.iq.imag)
            iq = self.model.iq
            self.narrow.setData(np.fft.fftshift(np.fft.fftfreq(len(iq), 1/480000))/1000,
                20*np.log10(np.maximum(np.abs(np.fft.fftshift(np.fft.fft(iq))), 1e-9)))
        if self.wifi_started is not None and self.selected == 'F14':
            elapsed = time.monotonic()-self.wifi_started
            self.progress_bar.setFormat('已用 %.0f 秒 · %s' % (elapsed,
                '预计剩余 %.0f 秒' % (120-elapsed) if elapsed < 120 else '仍在处理，超过初始估计'))
        if self.app_identity in ('F11', 'F14') and self.app_busy:
            self.notice.setText('有限宽带快照 · 临时30.72 MSPS · PL处理源关闭 · TX 关闭 · —')
        elif self.wifi_locked and not self.active and not self.app_busy:
            self.notice.setText('Wi-Fi采集已结束 · 已恢复3.84 MSPS · 等待确认广播天线 · TX 关闭 · —')

    def closeEvent(self, event):
        if self.audio_worker and self.audio_worker.isRunning():
            self.state.setText('录音校验尚未完成，请等待后关闭'); event.ignore(); return
        if self.audio_dialog: self.audio_dialog.close()
        if self.wifi_worker and self.wifi_worker.isRunning():
            self.state.setText('电脑解码尚未结束，请等待完成后关闭'); event.ignore(); return
        super().closeEvent(event)
