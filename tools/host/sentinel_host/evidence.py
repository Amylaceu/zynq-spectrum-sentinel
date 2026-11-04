"""Read-only evidence browser with pinned hashes and explicit source dates."""
import hashlib
import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets, QtMultimedia


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def original_date(path):
    """Never relabel filesystem copy time as the original measurement date."""
    if path.suffix == '.json':
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(value, dict):
                for key in ('started_utc', 'created_utc', 'timestamp_utc', 'date'):
                    if value.get(key):
                        return str(value[key])
        except (ValueError, OSError):
            pass
    return '原日期未记录；请查看关联测量'


def record_file(path, root):
    digest = sha256(path)
    sidecar = Path(str(path)+'.sha256')
    status = 'CURRENT_SNAPSHOT_HASH_ONLY'
    if sidecar.is_file():
        tokens = sidecar.read_text(encoding='utf-8-sig').split()
        status = 'ORIGINAL_SIDECAR_MATCH' if tokens and tokens[0].lower() == digest else 'HASH_MISMATCH'
    return dict(path=path.relative_to(root).as_posix(), sha256=digest,
                bytes=path.stat().st_size, original_date=original_date(path), integrity=status)


class EvidenceDialog(QtWidgets.QDialog):
    """Local media only; closes PC playback without altering board ownership."""
    def __init__(self, feature, files, root, parent=None):
        super().__init__(parent)
        self.root, self.files = root, files
        self.setWindowTitle(feature.key+' · '+feature.title+' · 实测资料')
        self.resize(1320, 900)
        outer = QtWidgets.QVBoxLayout(self)
        self.badge = QtWidgets.QLabel('实测结果 / 工程资料 · 不操作开发板')
        self.badge.setStyleSheet('color:#FFD257;font-size:18px;padding:8px;')
        outer.addWidget(self.badge)
        splitter = QtWidgets.QSplitter()
        self.list = QtWidgets.QListWidget()
        self.list.setMinimumWidth(280)
        self.list.setMaximumWidth(420)
        for path in files:
            item = QtWidgets.QListWidgetItem(path.relative_to(root).as_posix())
            item.setToolTip(item.text())
            self.list.addItem(item)
        splitter.addWidget(self.list)
        self.stack = QtWidgets.QStackedWidget()
        self.text = QtWidgets.QTextBrowser()
        self.text.setOpenExternalLinks(False)
        self.text.setStyleSheet('font-size:18px;')
        self.stack.addWidget(self.text)
        self.image = QtWidgets.QLabel()
        self.image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.image)
        scroll.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(scroll)
        self.wave = QtWidgets.QWidget()
        wave_layout = QtWidgets.QVBoxLayout(self.wave)
        import pyqtgraph as pg
        self.waveform = pg.PlotWidget(title='历史录音波形 · PC 播放，非实时同声')
        self.curve = self.waveform.plot(pen='#62E5DC')
        wave_layout.addWidget(self.waveform)
        self.play_button = QtWidgets.QPushButton('▶ PC 播放 / 暂停')
        wave_layout.addWidget(self.play_button)
        self.stack.addWidget(self.wave)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)
        self.details = QtWidgets.QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.details)
        self.audio = QtMultimedia.QAudioOutput(self)
        self.audio.setVolume(.25)
        self.player = QtMultimedia.QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(lambda *_: self.details.setText('音频播放失败：'+self.player.errorString()))
        self.play_button.clicked.connect(self.toggle_audio)
        self.list.currentRowChanged.connect(self.select_file)
        if files:
            self.list.setCurrentRow(0)
        else:
            self.text.setPlainText('当前交接包没有找到该项资料。入口已保留，不能判定本项已验收。')

    def select_file(self, row):
        if not 0 <= row < len(self.files):
            return
        path = self.files[row]
        self.player.stop()
        try:
            info = record_file(path, self.root)
            self.details.setText(info['path']+'\nSHA256 '+info['sha256']+' · '+info['integrity'])
            self.badge.setText('实测结果 / 工程资料 · '+info['original_date'])
            if info['integrity'] == 'HASH_MISMATCH':
                raise ValueError('文件与原始 SHA256 不符，拒绝展示内容')
            if path.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                pixmap = QtGui.QPixmap(str(path))
                if pixmap.isNull():
                    raise ValueError('图片无法读取')
                # Native resolution in a scroll area: every gallery image can be enlarged.
                self.image.setPixmap(pixmap)
                self.image.resize(pixmap.size())
                self.stack.setCurrentIndex(1)
            elif path.suffix.lower() == '.wav':
                import wave
                import numpy as np
                with wave.open(str(path)) as stream:
                    channels, width, rate = stream.getnchannels(), stream.getsampwidth(), stream.getframerate()
                    if width != 2:
                        raise ValueError('波形预览仅支持 int16 WAV；原文件保持不变')
                    values = np.frombuffer(stream.readframes(min(stream.getnframes(), rate*600)), dtype='<i2')
                    values = values.reshape(-1, channels)[:, 0]
                step = max(1, len(values)//20000)
                self.curve.setData(np.arange(0, len(values), step)/rate, values[::step]/32768.)
                self.player.setSource(QtCore.QUrl.fromLocalFile(str(path)))
                self.badge.setText('REPLAY · '+path.name+' · '+info['original_date'])
                self.stack.setCurrentIndex(2)
            else:
                if path.stat().st_size > 2*1024*1024:
                    raise ValueError('文本超过 2 MiB，请使用离线分析工具查看')
                value = path.read_text(encoding='utf-8-sig')
                if path.suffix == '.md':
                    self.text.setMarkdown(value)
                else:
                    if path.suffix == '.json':
                        value = json.dumps(json.loads(value), ensure_ascii=False, indent=2)
                    self.text.setPlainText(value)
                self.stack.setCurrentIndex(0)
        except (OSError, ValueError, KeyError) as error:
            self.stack.setCurrentIndex(0)
            self.text.setPlainText(str(error))

    def toggle_audio(self):
        if self.player.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def closeEvent(self, event):
        self.player.stop()
        event.accept()
