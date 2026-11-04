"""Ten-page J-v4 candidate. Navigation never sends hardware commands.

The legacy shell remains available for rollback. This candidate does not import
the cancelled presenter controls, change twin.py, or implement RF transmission.
"""
import json
import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .catalog import LIVE_SCENES, repository
from .live_catalog import FEATURES, BY_KEY, PAGES, DOCUMENT_ONLY, executable
from .gui import Window as AnalysisWindow
from .shell import AdaptiveCanvas, Window as LegacyWindow
from .panels.target_card import TargetCard
from .panels.base import current

STYLE = '''
QMainWindow,QWidget {background:#0B121B;color:#E4EDF4;font-family:"Microsoft YaHei UI";font-size:18px;}
QLabel {background:transparent;}
QFrame[card="true"] {background:#13202E;border:1px solid #2B4054;border-radius:10px;}
QPushButton {background:#182B3C;border:1px solid #314C61;border-radius:7px;padding:10px 8px;}
QPushButton:hover {border-color:#64E4D4;}
QPushButton:checked {background:#18483F;color:#6CF3D6;border-color:#6CF3D6;}
QPushButton:disabled {color:#748A9B;}
QListWidget,QTextBrowser,QLineEdit,QComboBox {background:#0F1C29;border:1px solid #293F51;border-radius:6px;padding:5px;}
QListWidget::item {padding:9px 4px;border-bottom:1px solid #1B3042;}
QListWidget::item:selected {background:#214438;color:#96F5DA;}
QProgressBar {background:#132C3D;border:0;height:12px;}
QProgressBar::chunk {background:#45BCB0;}
QTabBar::tab {padding:7px;background:#152A3B;}
QTabBar::tab:selected {color:#72E5D6;}
QScrollArea {border:0;}
'''
DEFAULT_KEYS = ('1', '9', '14', '24', '31', '36', '43', '49a', '50', '52a')


class Window(AnalysisWindow):
    """Existing network/model/recording code, isolated new product layout."""
    def __init__(self, root=None):
        super().__init__()
        self.timer.stop()
        self.root = Path(root or repository()).resolve()
        self.active_page = 0
        self.last_packet_time = None
        self._received_by_type = {}
        self.pending_scene = None
        self.current_scene = 'unknown'
        self.scene_records = []
        self._refresh_detail_at = 0.
        self.preview_mode = False
        self.focused = False
        self._live_address = None
        self._live_token = None
        self._stop_after_reconnect = False
        self._close_after_idle = False
        self._idle_confirmed_for_close = False
        self.model.build_info = LegacyWindow.load_build_info()
        self._build_info = self.model.build_info
        self.setWindowTitle('频谱监测终端 · SentinelHost / 现场工作台')
        self.resize(1920, 1080)
        self.toolbar.hide()
        self.legacy_views = self.takeCentralWidget()
        self.legacy_views.hide()
        root_widget = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(root_widget)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(10)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel('频谱监测终端  /  SentinelHost')
        title.setStyleSheet('font-size:25px;font-weight:600;color:#7CE6D7;')
        header.addWidget(title)
        header.addWidget(QtWidgets.QLabel('100 MHz  ·  3.84 MSPS'))
        header.addStretch(1)
        self.address = QtWidgets.QLineEdit('192.168.2.99')
        self.address.setFixedWidth(155)
        self.token = QtWidgets.QLineEdit()
        self.token.hide()
        header.addWidget(self.address)
        self.connect_button = QtWidgets.QPushButton('连接')
        self.connect_button.clicked.connect(self.connect_board)
        header.addWidget(self.connect_button)
        self.status = QtWidgets.QLabel('离线 · 未连接')
        self.status.setMaximumWidth(270)
        header.addWidget(self.status)
        self.stop_button = QtWidgets.QPushButton('■ 全部停止  Esc')
        self.stop_button.setStyleSheet('background:#722F3D;color:white;border-color:#C35C6C;')
        self.stop_button.clicked.connect(self.all_stop)
        header.addWidget(self.stop_button)
        outer.addLayout(header)
        line = QtWidgets.QHBoxLayout()
        self.page_title = QtWidgets.QLabel()
        self.page_title.setStyleSheet('font-size:25px;font-weight:600;')
        self.mode_badge = QtWidgets.QLabel('离线 · 未连接开发板')
        self.mode_badge.setStyleSheet('color:#FFD257;')
        line.addWidget(self.page_title)
        line.addStretch(1)
        line.addWidget(self.mode_badge)
        outer.addLayout(line)
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(10)
        self.left = self.card()
        self.left.setFixedWidth(184)
        nav = QtWidgets.QVBoxLayout(self.left)
        nav.setContentsMargins(10, 10, 10, 10)
        nav.setSpacing(9)
        nav.addWidget(QtWidgets.QLabel('现场功能'))
        self.buttons = []
        self.live_actions = (
            ('系统自检', 'check', 0, '1'),
            ('监测识别', 'fm', 2, '14'),
            ('广播收听', 'listen', 3, '24'),
            ('性能监测', 'perf', 6, '43'),
        )
        self.live_action_index = None
        self.action_colors = {
            'idle': 'background:#182B3C;color:#E4EDF4;border-color:#314C61;',
            'starting': 'background:#765D22;color:#FFF0AE;border-color:#E5BD58;',
            'running': 'background:#18483F;color:#96F5DA;border-color:#6CF3D6;',
            'failed': 'background:#722F3D;color:white;border-color:#C35C6C;',
        }
        for index, (name, scene, page, key) in enumerate(self.live_actions):
            button = QtWidgets.QPushButton('%02d  %s' % (index+1, name))
            button.setCheckable(True)
            button.setMinimumHeight(58)
            button.clicked.connect(lambda _, i=index: self.run_live_action(i))
            nav.addWidget(button)
            self.buttons.append(button)
        nav.addStretch(1)
        self.action_state = QtWidgets.QLabel('')
        self.action_state.setWordWrap(True)
        nav.addWidget(self.action_state)
        self.tools_button = QtWidgets.QPushButton('工具与导出')
        self.tools_button.setMenu(self.tools_menu())
        nav.addWidget(self.tools_button)
        body.addWidget(self.left)
        self.center = QtWidgets.QWidget()
        mid = QtWidgets.QVBoxLayout(self.center)
        mid.setContentsMargins(0, 0, 0, 0)
        kpis = QtWidgets.QHBoxLayout()
        self.kpis = []
        for label in ('屏幕帧率', '芯片温度', '接收功率'):
            box = self.card()
            layout = QtWidgets.QVBoxLayout(box)
            text = QtWidgets.QLabel(label)
            text.setStyleSheet('color:#A2BDCE;font-size:16px;')
            value = QtWidgets.QLabel('—')
            value.setStyleSheet('font:32px Consolas;color:#E1F9F2;')
            layout.addWidget(text)
            layout.addWidget(value)
            kpis.addWidget(box)
            self.kpis.append(value)
        mid.addLayout(kpis)
        self.twin_heading = QtWidgets.QLabel('J22 LCD 数字孪生 · 按 F 聚焦，F11 全屏')
        self.twin_heading.setStyleSheet('font-size:18px;color:#A6C8D6;')
        mid.addWidget(self.twin_heading)
        self.twin_canvas = AdaptiveCanvas()
        self.twin_canvas.click.connect(self.twin_click)
        self.twin_canvas.double_click.connect(self.twin_listen)
        self.twin_canvas.context.connect(self.twin_context)
        self.canvas_stack = QtWidgets.QStackedWidget()
        self.canvas_stack.addWidget(self.twin_canvas)
        mid.addWidget(self.canvas_stack, 1)
        self.twin_scope = QtWidgets.QLabel('')
        mid.addWidget(self.twin_scope)
        body.addWidget(self.center, 1)
        self.right = self.card()
        self.right.setFixedWidth(270)
        right = QtWidgets.QVBoxLayout(self.right)
        self.detail_title = QtWidgets.QLabel('功能详情')
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet('font-size:21px;color:#7CE6D7;font-weight:600;')
        right.addWidget(self.detail_title)
        self.details = QtWidgets.QTextBrowser()
        self.details.setMaximumHeight(95)
        self.details.setOpenExternalLinks(False)
        right.addWidget(self.details)
        self.visuals = QtWidgets.QStackedWidget()
        self.chart = pg.PlotWidget(background='#13202E')
        self.chart.showGrid(x=True, y=True, alpha=.15)
        self.trace = self.chart.plot(pen=pg.mkPen('#6DE8D3', width=2), connect='finite')
        self.visuals.addWidget(self.chart)
        self.target_panel = TargetCard()
        self.visuals.addWidget(self.target_panel)
        self.picture = QtWidgets.QLabel()
        self.picture.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.picture.setMinimumSize(1, 1)
        self.visuals.addWidget(self.picture)
        self.special = QtWidgets.QTextBrowser()
        self.special.setStyleSheet('font-size:18px;')
        self.visuals.addWidget(self.special)
        right.addWidget(self.visuals, 1)
        self.files_label = QtWidgets.QLabel()
        self.files_label.setWordWrap(True)
        self.files_label.setStyleSheet('font-size:15px;color:#8FAABF;')
        right.addWidget(self.files_label)
        body.addWidget(self.right)
        outer.addLayout(body, 1)
        footer = QtWidgets.QHBoxLayout()
        self.tx_badge = QtWidgets.QLabel('TX 状态未知 · 禁止发射')
        footer.addWidget(self.tx_badge)
        footer.addStretch(1)
        footer.addWidget(QtWidgets.QLabel('现场接收 · TX 关闭'))
        outer.addLayout(footer)
        self.setCentralWidget(root_widget)
        self.setStyleSheet(STYLE)
        for shortcut in self.findChildren(QtGui.QShortcut):
            if shortcut.key() in (QtGui.QKeySequence('Tab'), QtGui.QKeySequence('Escape')):
                shortcut.setEnabled(False)
        QtGui.QShortcut(QtGui.QKeySequence('Escape'), self, activated=self.all_stop)
        QtGui.QShortcut(QtGui.QKeySequence('F'), self, activated=self.toggle_focus)
        self.select_page(0)
        self.timer.start(50)

    @staticmethod
    def card():
        frame = QtWidgets.QFrame()
        frame.setProperty('card', True)
        return frame

    def tools_menu(self):
        menu = QtWidgets.QMenu(self)
        for label, action in (('保存截图 PNG', self.screenshot), ('导出目标 CSV', self.export_csv),
                              ('导出 IQ npy / cf32', self.export_iq), ('录制新会话', self.record),
                              ('显示本轮 Wi-Fi 名称', self.open_wifi_names),
                              ('导出观察摘要 HTML', self.export_html),
                              ('全屏 F11', self.fullscreen)):
            menu.addAction(label, action)
        return menu

    def open_wifi_names(self):
        """Open only the newest verified, non-expired AD9361 SSID result."""
        from .wifi_names import show_names, verified_names

        candidates = sorted(self.root.glob('board/measurements/j_ssid_live_r*/decoded/result.json'),
                            key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            try:
                data, _ = verified_names(path, json.loads(path.read_text(encoding='utf-8'))['session_id'])
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
            self.wifi_window = show_names(path, data['session_id'], self)
            return
        QtWidgets.QMessageBox.information(
            self, 'Wi-Fi 名称', '没有可显示的当前 AD9361 信标结果，请先执行一次2.4 GHz接收采集。')

    def select_page(self, page, manual=False):
        if page not in (0, 2, 3, 6):
            raise ValueError('Unknown product page')
        self.active_page = page
        self.canvas_stack.setCurrentIndex(0)
        self.page_title.setText('%02d  %s' % (page+1, PAGES[page]))
        action_index = next((i for i, row in enumerate(self.live_actions) if row[2] == page), -1)
        for i, button in enumerate(self.buttons):
            button.setChecked(i == action_index)
            button.setStyleSheet(self.action_colors['running'] if i == action_index
                                 and self.current_scene == self.live_actions[i][1]
                                 else self.action_colors['idle'])
        key = next(row[3] for row in self.live_actions if row[2] == page)
        self.selected_feature = BY_KEY[key]
        self.detail_title.setText(self.live_actions[action_index][0])
        self.details.clear()

    def run_live_action(self, index):
        name, scene, page, key = self.live_actions[index]
        self.selected_feature = BY_KEY[key]
        self.active_page = page
        self.canvas_stack.setCurrentIndex(0)
        self.page_title.setText('%02d  %s' % (page+1, PAGES[page]))
        self.detail_title.setText(name)
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)
            button.setStyleSheet(self.action_colors['starting'] if i == index
                                 else self.action_colors['idle'])
        self.live_action_index = index
        self.action_state.setText('启动中…')
        self.start_scene(scene)

    def jump_feature(self, key, navigate=True):
        feature = BY_KEY[key]
        if feature.page in (0, 2, 3, 6):
            self.select_page(feature.page)

    def feature_changed(self, item, previous=None):
        return

    def page_visual(self, feature, files):
        if feature.page == 2:
            return
        text = ('连接开发板后，点击本页已开放的操作。\n\n'
                '未接入的功能不显示旧数据，未通过的指标保持原结论。')
        if feature.page == 3:
            text = ('现场广播 · J36 板载喇叭\n95.800 MHz\n'
                    'ROUT2：0 dB；OUT1 上限：−6 dB\n\n等待本轮播放计数和门控状态。')
        elif feature.page == 5:
            text = ('现场空口采集与识别待接入。\n\n'
                    '需按测试频段确认天线连接，完成发射前检查。\n'
                    '本次修改未启动发射。')
        elif feature.page == 7:
            text = '记录与导出本轮采集数据。\n不加载历史会话、录音或 IQ。'
        elif feature.page == 9:
            text = '现场功能索引\n\n已开放、待接入和工程文档项分别标明。\n导航不启动硬件。'
        self.special.setPlainText(text)

    def feature_files(self, feature):
        return []

    def describe_feature(self, feature, files):
        if feature.key == '42':
            text = ('现场 2.4 GHz 能量观测待接入。\n'
                    '历史热点归因结论 INCONCLUSIVE，未解码 SSID，不具备热点识别能力。')
        elif feature.key == '47':
            text = '资源与时序属于冻结版本构建资料，不是现场测量。+1 ns 优化目标未达。'
        elif feature.key in DOCUMENT_ONLY:
            text = '工程文档项，保留在项目报告。不能用历史图表代替现场功能验收。'
        elif feature.scene:
            text = '现场操作：%s\n等待开发板确认，本轮场景：%s' % (feature.scene, self.current_scene)
        elif executable(feature):
            text = '仅处理本轮现场数据；连接失效时拒绝执行。'
        else:
            text = '现场功能待接入和真板验证。尚未完成，不以历史数据替代。'
        self.details.setPlainText(text)

    def activate_feature(self):
        feature = self.selected_feature
        if feature.key not in ('13', '52a') and not self.live_ready():
            self.action_state.setText('请先连接开发板')
            return
        if feature.scene:
            self.start_scene(feature.scene)
        elif feature.key == '13':
            self.select_page(2)
            self.action_state.setText('已定位 FM 分析页；请点击“开始监测”，板端尚未动作')
        elif feature.key == '18':
            target, _ = current(self.model, self.twin)
            if target is None:
                self.action_state.setText('请先在 LCD 孪生中选择目标，再点击识别')
            elif self.send('select_target', key=target['key']) is None:
                self.action_state.setText('未连接实时服务，未发送命令')
            else:
                self.action_state.setText('已选择目标，等待下一次真实识别输出')
        elif feature.key == '22':
            self.export_iq()
        elif feature.key == '49a':
            self.record()
        elif feature.key == '49g':
            self.tools_menu().exec(QtGui.QCursor.pos())
        elif feature.key == '52a':
            self.canvas_stack.setCurrentIndex(1)

    def live_ready(self):
        return bool(self.worker and not self.worker.session and not self.preview_mode
                    and self.last_packet_time is not None
                    and time.monotonic()-self.last_packet_time < 3
                    and self.model.hello.get('mode') == 'resident')

    def start_scene(self, scene):
        if scene not in LIVE_SCENES:
            raise ValueError('Unimplemented or transmit scene refused')
        if self.pending_scene:
            self.action_state.setText('上一场景仍在切换')
            return
        fresh = self.last_packet_time is not None and time.monotonic()-self.last_packet_time < 3
        if self.model.hello.get('mode') != 'resident' or self.preview_mode or not fresh:
            self.action_state.setText('板端连接不可用')
            return
        seq = self.send('scene', id=scene)
        if seq is None:
            self.action_state.setText('连接不可用')
            return
        self.pending_scene = dict(seq=seq, scene=scene, started=time.monotonic())
        self.action_state.setText('启动中…')

    def all_stop(self):
        # Queue idle even while a previous scene is pending. Never send terminate.
        seq = self.send('scene', id='idle')
        self.pending_scene = dict(seq=seq, scene='idle', started=time.monotonic()) if seq else None
        self.action_state.setText('正在停止' if seq else '未连接')

    def packet(self, header, payload, received):
        super().packet(header, payload, received)
        self.last_packet_time = received
        self._received_by_type[header['type']] = received
        if header['type'] == 'hello':
            self.current_scene = header.get('scene', 'unknown')
            self.pending_scene = None
            if self._stop_after_reconnect or self._close_after_idle:
                self._stop_after_reconnect = False
                self.all_stop()
        pending = self.pending_scene
        # Reuse the installed protocol: reply/error + request_seq + scene result.
        if pending and header.get('type') in ('reply', 'error') and header.get('request_seq') == pending['seq']:
            result = header.get('scene', {})
            ok = (header.get('ok') is True and result.get('status') == 'READY'
                  and result.get('scene') == pending['scene']
                  and result.get('readiness', {}).get('ready') is True)
            if ok:
                self.current_scene = pending['scene']
                self.scene_records.append(dict(scene=pending['scene'],
                    end_to_end_s=received-pending['started'], response=dict(header)))
                self.action_state.setText('运行中')
                if pending['scene'] == 'idle':
                    self.live_action_index = None
                    for button in self.buttons:
                        button.setChecked(False)
                        button.setStyleSheet(self.action_colors['idle'])
                elif self.live_action_index is not None:
                    self.buttons[self.live_action_index].setStyleSheet(self.action_colors['running'])
                checks = result.get('readiness', {}).get('checks', {})
                summary = []
                if pending['scene'] == 'check' and checks:
                    summary = ['位流 '+('OK' if checks.get('bit_sha256') == self._build_info.get('bit_sha256') else '已检查'),
                               '温度 '+str(checks.get('temperature_c', '—'))+' °C',
                               '信号质量 '+('OK' if checks.get('passed') else '检查中')]
                elif pending['scene'] == 'fm':
                    summary = ['目标 '+str(result.get('readiness', {}).get('targets', '—'))]
                elif pending['scene'] == 'listen':
                    summary = ['广播 '+('播放中' if result.get('readiness', {}).get('readiness', {}).get('ready') else '静音')]
                elif pending['scene'] == 'perf':
                    summary = ['性能数据接收中']
                self.details.setPlainText(' · '.join(summary))
                self.pending_scene = None
                if self._close_after_idle and self.current_scene == 'idle':
                    self._idle_confirmed_for_close = True
                    QtCore.QTimer.singleShot(0, self.close)
            else:
                self.action_state.setText('失败 · '+str(header.get('error', result.get('error', result))))
                if self.live_action_index is not None:
                    self.buttons[self.live_action_index].setStyleSheet(self.action_colors['failed'])
                self.pending_scene = None
                self._close_after_idle = False

    def start_worker(self, **kwargs):
        if kwargs.get('session') is not None:
            raise ValueError('Live presentation does not accept recorded sessions')
        self._live_address = kwargs.get('address')
        self._live_token = kwargs.get('token')
        super().start_worker(**kwargs)
        self.model.build_info = self._build_info
        self.last_packet_time = None
        self._received_by_type.clear()
        self.pending_scene = None
        self._idle_confirmed_for_close = False

    def replay(self):
        self.action_state.setText('仅支持现场展示')

    def open_session(self, path):
        raise ValueError('Live presentation does not accept recorded sessions')

    def fallback(self):
        self.action_state.setText('请恢复开发板连接后重试')

    def show_evidence(self):
        self.action_state.setText('工程资料保留在项目文档中')

    def load_reference_panorama(self):
        self.action_state.setText('现场全景扫描待接入，不加载历史曲线')

    def record(self):
        if self.recorder or self.live_ready():
            super().record()
        else:
            self.action_state.setText('没有有效现场数据，无法开始记录')

    def export_iq(self):
        if self.live_ready() and time.monotonic()-self._received_by_type.get('iq', -1e12) < 3:
            super().export_iq()
        else:
            self.action_state.setText('没有有效现场数据，无法导出 IQ')

    def export_csv(self):
        if self.live_ready() and time.monotonic()-self._received_by_type.get('detections', -1e12) < 3:
            super().export_csv()
        else:
            self.action_state.setText('没有有效现场数据，无法导出目标')

    def export_html(self):
        if not self.live_ready():
            self.action_state.setText('没有有效现场数据，无法导出摘要')
            return
        from .report import export_report
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '导出观察摘要', 'observation.html', 'HTML (*.html)')
        if path:
            export_report(self.model, path, source='live', session=None)

    def refresh(self):
        if not hasattr(self, 'selected_feature'):
            return
        now = time.monotonic()
        if self.twin.count != self.last_twin_painted:
            frame = self.twin.render()
            self.twin_canvas.set_frame(frame)
            self.last_twin_painted = self.twin.count
            self.painted_frames += 1
            self.twin_painted += 1
        if now-self._refresh_detail_at < .2:
            return
        self._refresh_detail_at = now
        fresh = self.last_packet_time is not None and now-self.last_packet_time < 3
        if self.preview_mode:
            mode = 'OFFLINE · 合成界面预览，非板测'
        elif fresh:
            mode = '实时 · 开发板数据'
        else:
            mode = '离线 / 数据已过期'
        self.mode_badge.setText(mode)
        # A heartbeat or reply cannot make an old LCD/IQ/telemetry sample fresh.
        visual_fresh = self.preview_mode or any(now-self._received_by_type.get(kind, -1e12) < 3
                                               for kind in ('spectrum', 'ui_frame', 'pl_frame'))
        self.twin_canvas.setVisible(visual_fresh)
        self.target_panel.setVisible(self.preview_mode or
            now-self._received_by_type.get('amc', -1e12) < 3)
        self.twin_scope.clear()
        telemetry_fresh = now-self._received_by_type.get('telemetry', -1e12) < 3
        t = self.model.telemetry[-1][1] if self.model.telemetry and (telemetry_fresh or self.preview_mode) else {}
        for label, field, pattern in zip(self.kpis, ('display_fps', 'temperature_c', 'rx_rssi_dbm'),
                                         ('%.1f fps', '%.1f °C', '%.1f dBm')):
            label.setText(pattern % t[field] if t.get(field) is not None else '—')
        tx = t.get('tx_on')
        self.tx_badge.setText('TX OFF · 不发射' if tx is False else 'TX ON · 异常发射状态' if tx is True else 'TX 状态未知 · 禁止发射')
        self.tx_badge.setStyleSheet('color:'+('#6DE8D3' if tx is False else '#F0918E'))
        if self.active_page == 2:
            self.target_panel.refresh(self.model, self.twin)
        elif self.visuals.currentIndex() == 0 and self.active_page != 1:
            self.trace.setData(self.model.frequency/1e6, self.model.power)
            self.chart.setTitle('接收频谱 · 相对原始功率')
            self.chart.setLabel('bottom', '频率', units='MHz')
        if self.pending_scene and now-self.pending_scene['started'] > 15:
            self.action_state.setText('就绪超时；运行状态未知，请点全部停止后重试')
            self.pending_scene = None
            self._close_after_idle = False
            if self.live_action_index is not None:
                self.buttons[self.live_action_index].setStyleSheet(self.action_colors['failed'])

    def toggle_focus(self):
        self.focused = not self.focused
        self.left.setVisible(not self.focused)
        self.right.setVisible(not self.focused)

    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        # Keep the socket and window alive until the board confirms idle. Merely
        # enqueuing a command and closing Receiver could discard it mid-flight.
        if self.worker and not self.worker.session and not self._idle_confirmed_for_close:
            event.ignore()
            if not self._close_after_idle:
                self.all_stop()
                self._close_after_idle = bool(self.pending_scene)
            return
        super().closeEvent(event)
