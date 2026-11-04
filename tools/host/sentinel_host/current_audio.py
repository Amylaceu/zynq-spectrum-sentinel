"""One current-session WAV player. No history browser or file picker."""
from pathlib import Path
import hashlib
import json

from PySide6 import QtCore, QtMultimedia, QtWidgets


def verified_current_audio(directory, expected_session_id):
    directory = Path(directory).resolve()
    metadata = directory/'audio.json'
    if hashlib.sha256(metadata.read_bytes()).hexdigest() != Path(str(metadata)+'.sha256').read_text().split()[0]:
        raise ValueError('Audio metadata digest mismatch')
    record = json.loads(metadata.read_text())
    if (record.get('session_id') != expected_session_id
            or record.get('status') != 'READY_FOR_LISTENING'
            or record.get('source') != 'CURRENT_RF_IQ_SOFTWARE_FM_DEMOD'
            or record.get('synthetic') is not False
            or record.get('inserted_silence_samples') != 0
            or record.get('stitched_snapshot_gaps') is not False
            or record.get('wav') != 'current_recording.wav'):
        raise ValueError('Playback requires this request and a valid current recording')
    wav = directory/record['wav']
    if hashlib.sha256(wav.read_bytes()).hexdigest() != record['wav_sha256']:
        raise ValueError('Current WAV digest mismatch')
    return wav, record


class CurrentAudioDialog(QtWidgets.QDialog):
    def __init__(self, directory, session_id, parent=None):
        super().__init__(parent)
        self.directory, self.session_id = Path(directory), session_id
        wav, record = verified_current_audio(directory, session_id)
        self.setWindowTitle('现场广播录制 · 本轮录音播放')
        self.resize(720, 320)
        self.setStyleSheet('QWidget {background:#0B121B;color:#E4EDF4;'
                          'font-family:"Microsoft YaHei UI";font-size:18px;}'
                          'QPushButton {background:#20594F;padding:12px;border-radius:6px;}')
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel('本轮现场录音 · 电脑软件解调'))
        detail = QtWidgets.QLabel('%.3f MHz 广播 | 本轮 %.2f 秒 | 48 kHz 单声道\n'
            '来自刚刚接收的 IQ；开发板喇叭现已静音。\n'
            '这段播放是本轮录音，不是实时广播。' % (record.get('station_hz', 95800000)/1e6, record['duration_s']))
        detail.setWordWrap(True)
        layout.addWidget(detail)
        self.status = QtWidgets.QLabel('录制与校验完成，请点击播放')
        layout.addWidget(self.status)
        self.audio = QtMultimedia.QAudioOutput(self)
        self.audio.setVolume(.5)
        self.player = QtMultimedia.QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setSource(QtCore.QUrl.fromLocalFile(str(wav)))
        self.player.errorOccurred.connect(lambda *_: self.status.setText('播放错误：'+self.player.errorString()))
        self.player.mediaStatusChanged.connect(self.media_status)
        self.play = QtWidgets.QPushButton('播放本轮录音')
        self.play.clicked.connect(self.play_current)
        layout.addWidget(self.play)
        stop = QtWidgets.QPushButton('停止播放')
        stop.clicked.connect(self.player.stop)
        layout.addWidget(stop)

    def media_status(self, status):
        if status == QtMultimedia.QMediaPlayer.MediaStatus.EndOfMedia:
            self.status.setText('本轮录音播放结束，可再次播放')

    def play_current(self):
        try:
            verified_current_audio(self.directory, self.session_id)
        except Exception as error:
            self.player.stop()
            self.status.setText('校验失败，已禁止播放：'+str(error))
            self.play.setEnabled(False)
            return
        self.player.setPosition(0)
        self.player.play()
        self.status.setText('正在播放本轮录音（电脑扬声器）')

    def closeEvent(self, event):
        self.player.stop()
        event.accept()
