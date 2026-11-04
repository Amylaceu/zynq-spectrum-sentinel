"""Presenter controls reuse the receiver and frozen twin; no hardware imports.

Readiness always comes from a matching board response. A timeout is uncertain,
not a cancellation: lock new scenes until a reply, reconnect or confirmed stop.
"""
from pathlib import Path
import re
import sys
import time

import yaml
from PySide6 import QtCore, QtGui, QtWidgets

from .session import Replay


IDS = ('check', 'pano', 'fm', 'listen', 'wifi', 'ota', 'perf')


def scene_path():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))/'scenes.yaml'


def load_scenes(path=None):
    value = yaml.safe_load(Path(path or scene_path()).read_text(encoding='utf-8'))
    if value.get('schema') != 1 or [s.get('id') for s in value['scenes']] != list(IDS):
        raise ValueError('Invalid ordered presentation scenes')
    for scene in value['scenes']:
        if (type(scene['available']) is not bool or type(scene['page']) is not int or
                not 0 <= scene['page'] < 7 or not 0 < scene['target_s'] <= 10 or
                not 1 <= scene['seconds'] <= 240):
            raise ValueError('Invalid scene bounds')
    return value


class Presenter(QtCore.QObject):
    def __init__(self, window, config=None, clock=time.monotonic):
        super().__init__(window)
        self.window, self.clock = window, clock
        self.config = config or load_scenes()
        self.scenes = self.config['scenes']
        self.active = self.checked = self.forced = False
        self.index = 0
        self.pending = None
        self.state = 'OFF'
        self.records = []
        self.live_address = self.live_token = None
        self.started = self.segment_started = None
        self._last_time = ''
        self._styles = []
        self.bar = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.bar)
        row.setContentsMargins(0, 0, 0, 0)
        self.buttons = []
        for index, scene in enumerate(self.scenes):
            button = QtWidgets.QPushButton(scene['title'])
            button.setCheckable(True)
            button.setMinimumHeight(72)
            button.clicked.connect(lambda _, i=index: self.request(i))
            row.addWidget(button, 1)
            self.buttons.append(button)
        self.station = QtWidgets.QComboBox()
        self.station.addItem('95.8 MHz · 已验证', 95.8)
        self.station.setToolTip('当前服务仅配置此已确认电台；不发送未经支持的频率参数')
        row.insertWidget(4, self.station)
        stop = QtWidgets.QPushButton('■ 停止')
        stop.setMinimumHeight(72)
        stop.setStyleSheet('background:#7B2731;color:white;font-size:20px;')
        stop.clicked.connect(self.stop)
        row.addWidget(stop)
        self.bar.hide()

        self.banner = QtWidgets.QLabel('讲解模式 · 等待板端预检')
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet('font-size:32px;color:#FFD257;padding:8px;')
        self.banner.hide()
        self.dialog = QtWidgets.QDialog(window)
        self.dialog.setWindowTitle('讲解者 · 提词与计时（不投影）')
        self.dialog.resize(540, 420)
        layout = QtWidgets.QVBoxLayout(self.dialog)
        self.title = QtWidgets.QLabel()
        self.title.setStyleSheet('font-size:26px;color:#62E5DC;')
        self.notes = QtWidgets.QLabel()
        self.notes.setWordWrap(True)
        self.notes.setStyleSheet('font-size:18px;')
        self.times = QtWidgets.QLabel()
        self.times.setStyleSheet('font-size:30px;')
        self.health = QtWidgets.QLabel('板端状态未知')
        self.health.setWordWrap(True)
        self.health.setStyleSheet('font-size:18px;')
        for widget in (self.title, self.notes, self.times, self.health):
            layout.addWidget(widget)
        actions = QtWidgets.QHBoxLayout()
        for title, callback in (('上一场景', lambda: self.advance(-1)),
                                ('下一场景', lambda: self.advance(1)),
                                ('停止', self.stop)):
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        actions = QtWidgets.QHBoxLayout()
        self.retry = QtWidgets.QPushButton('重试当前场景')
        self.retry.clicked.connect(lambda: self.request(self.index))
        self.fallback = QtWidgets.QPushButton('播放兜底 · REPLAY')
        self.fallback.clicked.connect(self.play_fallback)
        self.return_live = QtWidgets.QPushButton('返回实时并预检')
        self.return_live.clicked.connect(self.resume_live)
        for button in (self.retry, self.fallback, self.return_live):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.force = QtWidgets.QPushButton('明确跳过预检门禁（仅接收）')
        self.force.clicked.connect(self.force_continue)
        layout.addWidget(self.force)
        exit_button = QtWidgets.QPushButton('退出讲解模式 P（先静音待机）')
        exit_button.clicked.connect(self.toggle)
        layout.addWidget(exit_button)
        # A single filter serves both top-level windows. Duplicate shortcuts on
        # parent/dialog can become ambiguous when the presenter has focus.
        self.entry_shortcut = QtGui.QShortcut(QtGui.QKeySequence('P'), window,
                                              activated=self.toggle)
        self.entry_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.update_controls()

    def eventFilter(self, watched, event):
        if (event.type() != QtCore.QEvent.Type.KeyPress or
                not isinstance(watched, QtWidgets.QWidget) or
                watched.window() not in (self.window, self.dialog) or
                event.modifiers() != QtCore.Qt.KeyboardModifier.NoModifier or event.isAutoRepeat()):
            return False
        key = event.key()
        if key == QtCore.Qt.Key.Key_P:
            self.toggle()
            return True
        if not self.active:
            return False
        if QtCore.Qt.Key.Key_1 <= key <= QtCore.Qt.Key.Key_7:
            self.request(key-QtCore.Qt.Key.Key_1)
        elif key in (QtCore.Qt.Key.Key_PageDown, QtCore.Qt.Key.Key_Right):
            self.advance(1)
        elif key in (QtCore.Qt.Key.Key_PageUp, QtCore.Qt.Key.Key_Left):
            self.advance(-1)
        elif key == QtCore.Qt.Key.Key_Escape:
            self.stop()
        else:
            return False
        return True

    def close(self):
        self.timer.stop()
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self.dialog.close()

    def live(self):
        worker = self.window.worker
        return bool(worker and not worker.session and
                    self.window.model.hello.get('mode') == 'resident' and
                    self.window.last_packet_time is not None and
                    self.clock()-self.window.last_packet_time < 3)

    def log(self, **fields):
        self.records.append(dict(t_mono=self.clock(), **fields))
        self.records = self.records[-512:]

    def toggle(self):
        if self.active:
            if self.pending:
                self.banner.setText('场景请求尚未结束，请先停止或等待回复')
                return
            if self.live():
                self.window.send('scene', id='idle')
            self.active = False
            QtWidgets.QApplication.instance().removeEventFilter(self)
            self.bar.hide()
            self.banner.hide()
            self.dialog.hide()
            self.window.projection_layout(False)
            for widget, style in self._styles:
                widget.setStyleSheet(style)
            self._styles = []
            return
        self.active, self.checked, self.forced = True, False, False
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.started = self.segment_started = self.clock()
        self.window.projection_layout(True)
        self._styles = [(w, w.styleSheet()) for w in
                        [self.window]+self.window.findChildren(QtWidgets.QWidget)
                        if w is not self.dialog and not self.dialog.isAncestorOf(w)]
        for widget, style in self._styles:
            widget.setStyleSheet(re.sub(r'font-size:\s*(\d+)px',
                lambda m: 'font-size:%dpx' % max(18, int(m[1])), style))
        self.bar.show()
        self.banner.show()
        self.dialog.show()
        screens = QtWidgets.QApplication.screens()
        if len(screens) > 1:
            self.dialog.move(screens[1].availableGeometry().topLeft()+QtCore.QPoint(20, 20))
        else:
            self.dialog.move(self.window.geometry().bottomRight()-QtCore.QPoint(555, 435))
        self.request(0)

    def available(self, index):
        scene = self.scenes[index]
        if not scene['available']:
            return False, scene.get('reason', '功能未验收')
        if self.pending:
            return False, '上一条请求未结束；不排队执行过期场景'
        if not self.live():
            return False, '请连接常驻接收服务；回放和普通监测不接受场景控制'
        if index != 0 and not (self.checked or self.forced):
            return False, '先通过预检，或在讲解者窗口明确跳过'
        return True, '已验证接收场景'

    def update_controls(self):
        for index, button in enumerate(self.buttons):
            available, reason = self.available(index)
            button.setEnabled(available)
            button.setToolTip(reason)
            button.setChecked(index == self.index and self.state == 'READY')
            if index == self.index and self.state in ('STARTING', 'TIMEOUT'):
                button.setText(self.scenes[index]['title']+' · '+('启动中' if self.state == 'STARTING' else '待确认'))
            else:
                button.setText(self.scenes[index]['title'])
            button.setProperty('nextScene', index == self.index+1)
        self.retry.setEnabled(self.available(self.index)[0])
        path, error = self.fallback_path()
        self.fallback.setEnabled(path is not None and self.pending is None)
        self.fallback.setToolTip(error or '核验完整会话后回放；不发送射频命令')
        self.return_live.setEnabled(bool(self.window.worker and self.window.worker.session))
        self.force.setEnabled(self.live() and not self.checked and not self.pending)

    def force_continue(self):
        self.forced = True
        self.log(event='PRECHECK_BYPASS', scope='receive-only')
        self.health.setText('已手动跳过预检；未验收功能仍不可用，发射始终禁用')
        self.update_controls()

    def request(self, index):
        if not self.active:
            return
        available, reason = self.available(index)
        if not available:
            self.banner.setText(reason)
            return
        scene = self.scenes[index]
        seq = self.window.send('scene', id=scene['id'])
        if seq is None:
            self.banner.setText('命令未入队，请检查实时连接')
            return
        self.index, self.state = index, 'STARTING'
        self.segment_started = self.clock()
        self.pending = dict(seq=seq, scene=scene['id'], start=self.clock(),
                            deadline=self.clock()+2*scene['target_s'])
        self.log(event='REQUEST', **self.pending)
        self.window.select_page(scene['page'])
        self.title.setText(scene['title'])
        self.notes.setText(scene['notes'])
        self.banner.setText(scene['title']+' · 启动中…等待板端就绪检查')
        self.update_controls()

    def advance(self, direction):
        if not self.active or self.pending:
            return
        for index in range(self.index+direction, 7 if direction > 0 else -1, direction):
            if self.available(index)[0]:
                self.request(index)
                return

    def packet(self, header, received):
        if not self.active:
            return
        if header['type'] == 'hello':
            self.checked = self.forced = False
            if self.pending:
                self.state, self.pending = 'DISCONNECTED', None
                self.banner.setText('服务连接已更换，旧命令状态作废；请重新预检')
            if self.live():
                self.request(0)
        pending = self.pending
        if (not pending or header['type'] not in ('reply', 'error') or
                header.get('request_seq') != pending['seq']):
            return
        elapsed = received-pending['start']
        result = header.get('scene', {})
        ok = (header.get('ok') is True and result.get('status') == 'READY' and
              result.get('scene') == pending['scene'] and
              result.get('readiness', {}).get('ready') is True)
        if pending['scene'] == '__stop__':
            ok = header.get('ok') is True
        self.state, self.pending = ('READY' if ok else 'FAILED'), None
        self.log(event='REPLY', elapsed_s=elapsed, ready=ok, reply=header,
                 scope='PC enqueue to matching response; includes dispatch and readiness')
        if ok and result.get('scene') == 'check':
            self.checked = result.get('readiness', {}).get('checks', {}).get('passed') is True
        self.banner.setText('已发送受控停止；硬件归零另行核验' if pending['scene'] == '__stop__' and ok else
            self.scenes[self.index]['title']+' · '+('已就绪' if ok else '未就绪：'+str(header.get('error', result.get('error', '板端检查未通过')))))
        self.health.setText('往返 %.3f s（含处理，非纯网络RTT）\n%s' % (elapsed,
            str(result.get('readiness', result))[:900]))
        self.update_controls()

    def stop(self):
        if not self.active:
            return
        self._fallback_after_idle = None
        if self.window.worker and self.window.worker.session:
            self.window.stop_worker()
            self.state, self.pending = 'STOPPED', None
            self.banner.setText('REPLAY 已停止；硬件状态不由回放推断')
        elif self.live():
            seq = self.window.send('stop')
            if seq is not None:
                self.pending = dict(seq=seq, scene='__stop__', start=self.clock(), deadline=self.clock()+10)
                self.state = 'STARTING'
                self.banner.setText('受控停止中…等待回复；硬件归零另行核验')
        else:
            self.banner.setText('连接不可用，未确认板端停止；请检查服务，不要直接断电')
        self.checked = self.forced = False
        self.log(event='STOP_REQUEST')
        self.update_controls()

    def fallback_path(self):
        relative = self.scenes[self.index].get('fallback')
        if not relative:
            return None, 'I6尚未注册此场景的核验回放素材'
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[3]))
        path = (base/relative).resolve()
        if not path.is_relative_to(base.resolve()) or path.suffix != '.zsr':
            return None, '素材路径须位于项目或发布目录内'
        if not (path/'manifest.json.sha256').is_file():
            return None, '回放素材缺失或未完成校验'
        return path, ''

    def play_fallback(self):
        path, error = self.fallback_path()
        if self.pending or path is None:
            self.banner.setText(error or '请先等待当前请求结束')
            return
        # Do not disconnect from a live speaker while it is still playing.
        # Current version requires an explicitly completed idle transition.
        if self.live() and self.state != 'IDLE_FOR_REPLAY':
            seq = self.window.send('scene', id='idle')
            if seq is not None:
                self.pending = dict(seq=seq, scene='idle', start=self.clock(), deadline=self.clock()+4)
                self.state = 'MUTING_FOR_REPLAY'
                self._fallback_after_idle = path
                self.banner.setText('回放前静音待机…等待板端确认')
            return
        self._start_replay(path)

    def _start_replay(self, path):
        try:
            replay = Replay(path)
            if replay.manifest['source'] != 'live' or not sum(1 for _ in replay):
                raise ValueError('讲解兜底只接受完整、非空的真实接收会话')
        except (OSError, ValueError, KeyError) as error:
            self.banner.setText('素材核验失败：'+str(error))
            return
        worker = self.window.worker
        if worker and not worker.session:
            self.live_address, self.live_token = worker.address, worker.token
        self.window.start_worker(session=str(path))
        self.state, self.pending, self.checked = 'REPLAY', None, False
        self.banner.setText('REPLAY / 记录回放 · '+self.scenes[self.index]['title'])
        self.log(event='REPLAY', path=str(path))
        self.update_controls()

    def resume_live(self):
        if not self.live_address:
            self.banner.setText('无先前实时地址，请用连接按钮恢复')
            return
        self.window.start_worker(address=self.live_address, token=self.live_token)
        self.state, self.checked = 'CONNECTING', False
        self.banner.setText('正在返回实时；连接完成后按①重新预检')

    def tick(self):
        if not self.active:
            return
        now = self.clock()
        if self.pending and now > self.pending['deadline'] and self.state != 'TIMEOUT':
            self.state = 'TIMEOUT'
            self.banner.setText('场景未在目标两倍时间内就绪；等待回复或按停止，不重复排队')
            self.log(event='TIMEOUT', request=dict(self.pending))
        if getattr(self, '_fallback_after_idle', None) and not self.pending:
            path, self._fallback_after_idle = self._fallback_after_idle, None
            if self.state == 'READY':
                self._start_replay(path)
        total = max(0, now-(self.started if self.started is not None else now))
        segment = max(0, now-(self.segment_started if self.segment_started is not None else now))
        text = '本段 %02d:%02d / %ds   总计 %02d:%02d / 04:00' % (
            int(segment)//60, int(segment)%60, self.scenes[self.index]['seconds'],
            int(total)//60, int(total)%60)
        if text != self._last_time:
            self.times.setText(text)
            self.times.setStyleSheet('font-size:30px;color:%s;' % (
                '#FF5A5A' if total > 240 or segment > self.scenes[self.index]['seconds'] else
                '#FFD257' if segment > .8*self.scenes[self.index]['seconds'] else '#00C86E'))
            self._last_time = text
        self.update_controls()
