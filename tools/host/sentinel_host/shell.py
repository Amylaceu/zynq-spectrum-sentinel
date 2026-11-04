"""Three-column workbench. All device commands use the existing receiver.

The legacy analysis view remains available. The frozen twin renderer and wire
protocol are reused without edits; only its desktop viewport is adapted here.
"""
import json
import hashlib
from pathlib import Path
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

from .gui import Window as AnalysisWindow
from .twin import TwinCanvas
from .theme import QSS
from .panels.signals import Signals
from .panels.occupancy import Occupancy
from .panels.health import Health
from .panels.target_card import TargetCard, ClassificationHistory
from .panels.constellation import Constellation
from .panels.audio import Audio
from .panels.timeline import Timeline
from .panels.telemetry import Telemetry
from .panels.confusion import Confusion
from .panels.panorama import Panorama
from .panels.system import System
from .panels.sessions import Sessions

PAGES = ('监测', '识别', '音频', '闭环评测', '全景', '系统', '回放', '分析视图')


def demo_page(header):
    """Matches the explicit G4+ segment map, never guesses transmitted truth."""
    group = header.get('group')
    segment = header.get('segment', header.get('segment_id'))
    if group == 'B' and segment in (5, 6):
        return 3
    if segment == 8:
        return 5
    if group == 'A':
        return {2: 1, 3: 2}.get(segment, 0)
    return 0


class AdaptiveCanvas(TwinCanvas):
    """Nearest-neighbour fractional viewport; inherited physical() maps hits."""
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 192)
        self.zoom_limit = None
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    def viewport(self):
        scale = min(self.width()/800, self.height()/480)
        if self.zoom_limit is not None:
            scale = min(scale, self.zoom_limit)
        width, height = max(1, round(800*scale)), max(1, round(480*scale))
        return QtCore.QRect((self.width()-width)//2, (self.height()-height)//2, width, height)


class TwinTitle(QtWidgets.QLabel):
    double_click = QtCore.Signal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.double_click.emit()


class Window(AnalysisWindow):
    def __init__(self):
        super().__init__()
        self.timer.stop()
        self.focused = False
        self.active_page = 0
        self.manual_until = 0.
        self.last_packet_time = None
        self.paint_times = []
        self.switch_times = []
        self._last_curves = self._last_tables = -1.
        self._demo_signature = None
        self._panel_list = []
        self._build_info = self.load_build_info()
        self.model.build_info = self._build_info
        self.setWindowTitle('SentinelHost · 频谱监测终端')
        self.resize(1920, 1080)
        self.toolbar.hide()
        # Keep the original widgets and export code for the optional analysis page.
        self.legacy_views = self.takeCentralWidget()
        self.analysis_page = self.legacy_views.widget(1)
        self.legacy_views.removeTab(1)
        self.legacy_views.hide()
        self.legacy_title = self.title
        root = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)
        top = QtWidgets.QHBoxLayout()
        self.header_layout = top
        self.title = QtWidgets.QLabel('频谱监测终端  /  SentinelHost')
        self.title.setProperty('heading', True)
        self.mode_badge = QtWidgets.QLabel('离线')
        self.status.setMaximumWidth(190)
        self.status.setWordWrap(True)
        self.tx_badge = QtWidgets.QLabel('TX 状态未知')
        top.addWidget(self.title)
        top.addWidget(self.mode_badge)
        top.addStretch(1)
        top.addWidget(QtWidgets.QLabel('FPGA 100 MHz · 3.84 MSPS'))
        top.addWidget(self.tx_badge)
        # Moving these widgets out of the old toolbar preserves connection logic.
        self.address = QtWidgets.QLineEdit(self.address.text())
        self.address.setFixedWidth(125)
        self.address.setToolTip('开发板 IP 地址')
        self.token = QtWidgets.QLineEdit()
        self.token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('可选令牌')
        self.token.setFixedWidth(85)
        self.status = QtWidgets.QLabel('离线')
        self.status.setMaximumWidth(120)
        self.status.setWordWrap(True)
        top.addWidget(self.address)
        top.addWidget(self.token)
        top.addWidget(self.status)
        icons = [('连接', 'SP_DialogApplyButton', self.connect_board),
                 ('手机监看二维码', 'SP_ComputerIcon', self.show_network_qr),
                 ('录制会话', 'SP_DialogSaveButton', self.record),
                 ('打开回放', 'SP_MediaPlay', self.replay),
                 ('保存截图', 'SP_FileIcon', self.screenshot),
                 ('导出目标 CSV', 'SP_DialogOpenButton', self.export_csv),
                 ('导出观察摘要 HTML', 'SP_FileDialogDetailedView', self.export_html),
                 ('载入告警规则', 'SP_MessageBoxWarning', self.load_alarms),
                 ('聚焦模式 F', 'SP_TitleBarMaxButton', self.toggle_focus),
                 ('全屏演示 F11', 'SP_TitleBarNormalButton', self.fullscreen)]
        for tooltip, icon, callback in icons:
            button = QtWidgets.QToolButton()
            button.setIcon(self.style().standardIcon(getattr(QtWidgets.QStyle.StandardPixmap, icon)))
            button.setIconSize(QtCore.QSize(21, 21))
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            top.addWidget(button)
        outer.addLayout(top)
        self.presentation_button = QtWidgets.QPushButton('讲解模式 P')
        top.addWidget(self.presentation_button)
        self.demo_banner = QtWidgets.QLabel()
        self.demo_banner.setStyleSheet('font-size:23px;color:#FFD257;padding:4px;')
        self.demo_banner.hide()
        outer.addWidget(self.demo_banner)
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(8)
        nav = QtWidgets.QVBoxLayout()
        self.nav_layout = nav
        self.buttons = []
        for index, text in enumerate(PAGES):
            button = QtWidgets.QPushButton(text)
            button.setCheckable(True)
            button.setFixedWidth(66)
            button.setMinimumHeight(53)
            button.clicked.connect(lambda _, i=index: self.select_page(i, manual=True))
            nav.addWidget(button)
            self.buttons.append(button)
        nav.addStretch(1)
        body.addLayout(nav)
        self.workbench = QtWidgets.QWidget()
        columns = QtWidgets.QHBoxLayout(self.workbench)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)
        self.left = QtWidgets.QStackedWidget()
        self.right = QtWidgets.QStackedWidget()
        columns.addWidget(self.left)
        center = QtWidgets.QWidget()
        mid = QtWidgets.QVBoxLayout(center)
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(5)
        self.canvas_title = TwinTitle('LCD 数字孪生 · 双击标题或按 F 聚焦')
        self.canvas_title.setProperty('heading', True)
        self.canvas_title.double_click.connect(self.toggle_focus)
        mid.addWidget(self.canvas_title)
        self.twin_canvas = AdaptiveCanvas()
        self.twin_canvas.click.connect(self.twin_click)
        self.twin_canvas.double_click.connect(self.twin_listen)
        self.twin_canvas.context.connect(self.twin_context)
        self.twin_canvas.lo_steps.connect(self.twin_wheel)
        mid.addWidget(self.twin_canvas, 1)
        self.twin_scope = QtWidgets.QLabel()
        self.twin_scope.setWordWrap(True)
        self.twin_scope.setStyleSheet('font-size:12px;color:#91A9B9;')
        mid.addWidget(self.twin_scope)
        self.timeline_panel = Timeline()
        self.timeline_panel.setFixedHeight(94)
        self.timeline_panel.activated.connect(self.activate_event)
        mid.addWidget(self.timeline_panel)
        self.telemetry_panel = Telemetry()
        self.telemetry_panel.setFixedHeight(158)
        mid.addWidget(self.telemetry_panel)
        columns.addWidget(center, 1)
        columns.addWidget(self.right)
        self.panel_groups = [
            ([Signals(), Occupancy(), Health()], [TargetCard(), Constellation(), Audio()]),
            ([ClassificationHistory()], [TargetCard(), Constellation(), Constellation(True)]),
            ([Audio(library=True)], [Audio()]),
            ([Confusion(sequence=True)], [Confusion()]),
            ([Panorama()], [Panorama()]),
            ([Health(), System()], [System(architecture=True)]),
            ([Sessions()], [Sessions(exports=True)]),
        ]
        for left, right in self.panel_groups:
            self.left.addWidget(self.panel_page(left))
            self.right.addWidget(self.panel_page(right))
        self.center_stack = QtWidgets.QStackedWidget()
        self.center_stack.addWidget(self.workbench)
        self.center_stack.addWidget(self.analysis_page)
        self.panorama_panel = Panorama()
        self.center_stack.addWidget(self.panorama_panel)
        self.panorama_panel.file_loaded.connect(self.load_panorama)
        for panel in sum(self.panel_groups[4], []):
            panel.file_loaded.connect(self.load_panorama)
        body.addWidget(self.center_stack, 1)
        outer.addLayout(body, 1)
        self.notice = QtWidgets.QLabel('上位机无发射控制 · PS 区逐像素一致 · PL 区抽样重建 · 历史未达标结论保留')
        self.notice.setStyleSheet('color:#91A9B9;font-size:12px;')
        outer.addWidget(self.notice)
        self.setCentralWidget(root)
        self.setStyleSheet(QSS)
        from .presentation import Presenter
        self.presentation = Presenter(self)
        outer.insertWidget(1, self.presentation.banner)
        outer.addWidget(self.presentation.bar)
        self.presentation_button.clicked.connect(self.presentation.toggle)
        QtGui.QShortcut(QtGui.QKeySequence('F'), self, activated=self.toggle_focus)
        for shortcut in self.findChildren(QtGui.QShortcut):
            if shortcut.key() == QtGui.QKeySequence('Tab'):
                shortcut.setEnabled(False)
        QtGui.QShortcut(QtGui.QKeySequence('Tab'), self,
            activated=lambda: self.select_page((self.active_page+1) % len(PAGES), manual=True))
        self.select_page(0)
        self.timer.start(50)

    @staticmethod
    def load_build_info():
        base = getattr(sys, '_MEIPASS', None)
        path = (Path(base)/'build_evidence/acceptance.json' if base else
                Path(__file__).resolve().parents[3]/'board/overlay/sentinel_v2_100m/acceptance.json')
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=Path(str(path)+'.sha256').read_text().split()[0]:
                return {}
            data = json.loads(path.read_text(encoding='utf-8'))
            return {k: data[k] for k in ('image', 'resources', 'final_timing')}
        except (OSError, ValueError, KeyError, IndexError):
            return {}

    def panel_page(self, panels):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for panel in panels:
            layout.addWidget(panel, 1)
            panel.command.connect(lambda name, args: self.send(name, **args))
            if isinstance(panel, Sessions):
                panel.action.connect(lambda name: getattr(self, name)())
            self._panel_list.append(panel)
        return page

    def select_page(self, index, manual=False):
        before = time.perf_counter()
        if manual:
            self.manual_until = time.monotonic()+30
        self.active_page = index
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)
        self.center_stack.setCurrentIndex(1 if index == 7 else 2 if index == 4 else 0)
        if index < 7:
            self.left.setCurrentIndex(index)
            self.right.setCurrentIndex(index)
            for panel in sum(self.panel_groups[index], []):
                panel.refresh(self.model, self.twin)
        self.switch_times.append((time.perf_counter()-before)*1000)
        self.switch_times = self.switch_times[-256:]

    def show_network_qr(self):
        from .network_share import NetworkShareDialog
        try:
            self.network_share_dialog = NetworkShareDialog(self.address.text(), self)
            self.network_share_dialog.show()
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, '二维码地址无效', str(error))

    def load_panorama(self, path):
        """Display a saved verified scan; never sends a hardware command."""
        for panel in [self.panorama_panel]+sum(self.panel_groups[4], []):
            panel.load_file(path)
        self.select_page(4, manual=True)

    def start_worker(self, **kwargs):
        super().start_worker(**kwargs)
        self.model.build_info = self._build_info
        self.last_packet_time = None
        self._demo_signature = None
        for panel in self._panel_list:
            panel._signature = None

    def packet(self, header, payload, received):
        super().packet(header, payload, received)
        self.last_packet_time = received
        self.presentation.packet(header, received)
        if header['type'] == 'demo':
            signature = (header.get('group'), header.get('segment', header.get('segment_id')))
            if signature != self._demo_signature:
                self._demo_signature = signature
                if time.monotonic() >= self.manual_until:
                    self.select_page(demo_page(header))

    def refresh(self):
        if not hasattr(self, 'panel_groups'):
            return
        before = time.perf_counter()
        now = time.monotonic()
        if self.active_page == 7:
            super().refresh()
        elif self.twin.count != self.last_twin_painted:
            self.twin_canvas.set_frame(self.twin.render())
            self.last_twin_painted = self.twin.count
            self.twin_painted += 1
            self.painted_frames += 1
        rect = self.twin_canvas.viewport()
        self.twin_scope.setText('%.2f× · %d×%d px · PS 区逐像素一致 / epoch %s · PL 区抽样重建，门限不可读' % (
            rect.width()/800, rect.width(), rect.height(), self.twin.epoch))
        if now-self._last_curves >= .2:
            self._last_curves = now
            self.telemetry_panel.refresh(self.model, self.twin)
            if self.active_page < 7:
                for panel in sum(self.panel_groups[self.active_page], []):
                    if isinstance(panel, (Constellation, Audio, Occupancy)):
                        panel.refresh(self.model, self.twin)
        if now-self._last_tables >= .5:
            self._last_tables = now
            self.timeline_panel.refresh(self.model, self.twin)
            if self.active_page < 7:
                for panel in sum(self.panel_groups[self.active_page], []):
                    if not isinstance(panel, (Constellation, Audio, Occupancy)):
                        panel.refresh(self.model, self.twin)
            self.update_badges(now)
        self.paint_times.append((time.perf_counter()-before)*1000)
        self.paint_times = self.paint_times[-2400:]

    def update_badges(self, now):
        synthetic = self.model.hello.get('spectrum_source') == 'synthetic-test'
        replay = bool(self.worker and self.worker.session)
        fresh = self.last_packet_time is not None and now-self.last_packet_time < 3
        mode = '离线合成示例 · 非板测' if synthetic else 'REPLAY / 回放' if replay else 'LIVE / 实时' if fresh else '离线 / 数据已过期'
        self.mode_badge.setText(mode)
        self.mode_badge.setStyleSheet('color:%s;font-weight:bold;' % ('#FFD257' if synthetic or replay else '#62E5DC'))
        telemetry = self.model.telemetry[-1][1] if self.model.telemetry else {}
        tx = telemetry.get('tx_on') if fresh or replay else None
        self.tx_badge.setText('TX ON / 发射' if tx is True else 'TX OFF / 关闭' if tx is False else 'TX 状态未知')
        self.tx_badge.setStyleSheet('color:%s;font-weight:bold;' % ('#FF5A5A' if tx is True else '#00C86E' if tx is False else '#FFD257'))
        demo = self.model.demo
        if demo:
            self.demo_banner.setText('%s组 · %s  |  剩余 %.1f s' % (
                demo.get('group', '?'), demo.get('title', ''), demo.get('remaining_s', 0)))
            self.demo_banner.setVisible(self.isFullScreen())

    def activate_event(self, event):
        # Live selection is supported; replay seek will be enabled with its index.
        key = event.get('target_key', event.get('track'))
        if key is not None and not (self.worker and self.worker.session):
            self.send('select_target', key=key)
        elif self.worker and self.worker.session:
            self.status.setText('回放事件定位：待索引功能完成')

    def export_html(self):
        from .report import export_report
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, '导出当前保留数据的观察摘要', 'observation.html', 'HTML (*.html)')
        if not path:
            return
        replay = self.worker.session if self.worker and self.worker.session else None
        source = 'replay' if replay else 'live' if self.last_packet_time is not None else 'offline'
        try:
            export_report(self.model, path, source=source, session=str(replay) if replay else None)
            self.status.setText('HTML / JSON / SHA256 已保存')
        except (ValueError, OSError) as error:
            self.status.setText('导出失败：'+str(error))

    def toggle_focus(self):
        if self.presentation.active:
            return
        self.focused = not self.focused
        self.left.setVisible(not self.focused)
        self.right.setVisible(not self.focused)
        self.timeline_panel.setVisible(not self.focused)
        self.telemetry_panel.setVisible(not self.focused)
        self.canvas_title.setVisible(not self.focused)
        self.twin_scope.setVisible(not self.focused)
        self.notice.setVisible(not self.focused)
        self.twin_canvas.zoom_limit = 2. if self.focused else None
        self.twin_canvas.update()

    def fullscreen(self):
        if self.presentation.active:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
            return
        if self.isFullScreen():
            self.showNormal()
            if self.focused:
                self.toggle_focus()
            self.demo_banner.hide()
        else:
            if not self.focused:
                self.toggle_focus()
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'left'):
            if getattr(getattr(self, 'presentation', None), 'active', False):
                self.left.setFixedWidth(280)
                self.right.setFixedWidth(300)
                return
            # Narrower sidebars preserve >=1000px twin at the 1920px baseline.
            self.left.setFixedWidth(max(220, min(300, int(self.width()*.135))))
            self.right.setFixedWidth(max(280, min(360, int(self.width()*.172))))

    def projection_layout(self, enabled):
        """Main window becomes projector; presenter controls live in a dialog."""
        for index in range(self.header_layout.count()):
            widget = self.header_layout.itemAt(index).widget()
            if widget:
                widget.setVisible(not enabled or widget in (self.mode_badge, self.tx_badge))
        for button in self.buttons:
            button.setVisible(not enabled)
        for widget in (self.timeline_panel, self.telemetry_panel, self.twin_scope,
                       self.notice, self.canvas_title):
            widget.setVisible(not enabled)
        self.twin_canvas.zoom_limit = None
        self.left.setVisible(True)
        self.right.setVisible(True)
        if enabled:
            self.focused = False
            self.left.setFixedWidth(280)
            self.right.setFixedWidth(300)
        else:
            self.left.setFixedWidth(max(220, min(300, int(self.width()*.135))))
            self.right.setFixedWidth(max(280, min(360, int(self.width()*.172))))

    def closeEvent(self, event):
        if hasattr(self, 'presentation'):
            self.presentation.close()
        super().closeEvent(event)
