"""LAN-only board web QR; showing a URL does not start or verify a service."""
import ipaddress
import qrcode
from PySide6 import QtCore, QtGui, QtWidgets

def board_url(address):
    value = ipaddress.IPv4Address(address.strip())
    if value.is_unspecified or value.is_multicast or value == ipaddress.IPv4Address('255.255.255.255'):
        raise ValueError('请输入开发板实际IPv4地址')
    return 'http://%s:8080/' % value

class NetworkShareDialog(QtWidgets.QDialog):
    def __init__(self, address, parent=None):
        super().__init__(parent)
        self.url = board_url(address)
        self.setWindowTitle('手机监看 · 局域网二维码')
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel('手机与开发板连接同一路由器，然后扫码')
        layout.addWidget(title)
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
        qr.add_data(self.url)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        scale = 8
        image = QtGui.QImage(len(matrix)*scale,len(matrix)*scale,QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        painter = QtGui.QPainter(image)
        for row, bits in enumerate(matrix):
            for col, black in enumerate(bits):
                if black:
                    painter.fillRect(col*scale,row*scale,scale,scale,QtCore.Qt.GlobalColor.black)
        painter.end()
        label = QtWidgets.QLabel()
        label.setPixmap(QtGui.QPixmap.fromImage(image))
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.address_label = QtWidgets.QLabel(self.url)
        self.address_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.address_label)
        note = QtWidgets.QLabel('需板端监测/服务正在运行；二维码本身不启动服务，也不证明网络已连通。\n不使用访客隔离网络；不要将服务端口暴露到公网。')
        note.setWordWrap(True)
        layout.addWidget(note)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.close)
        layout.addWidget(close)
