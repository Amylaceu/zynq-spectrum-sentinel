"""Desktop colours and Chinese typography; independent of the LCD palette."""
from PySide6 import QtGui

BG = '#090E14'
PANEL = '#121E28'
CYAN = '#62E5DC'
YELLOW = '#FFD257'
RED = '#FF5A5A'
GREEN = '#00C86E'

QSS = '''
QMainWindow,QWidget { background:#090E14; color:#DFE9EF; font-family:"Microsoft YaHei UI","Microsoft YaHei"; font-size:13px; }
QFrame[panel="true"] { background:#121E28; border:1px solid #263B49; border-radius:7px; }
QLabel { background:transparent; }
QLabel[heading="true"] { color:#62E5DC; font-size:16px; font-weight:600; }
QLabel[metric="true"] { font-family:Consolas; font-size:24px; color:#F2F8FB; }
QPushButton,QToolButton { background:#172A36; border:1px solid #2B4554; border-radius:5px; padding:7px; }
QPushButton:checked { background:#1D4D56; color:#62E5DC; border-color:#62E5DC; }
QPushButton:hover,QToolButton:hover { border-color:#62E5DC; }
QPushButton:disabled { color:#708492; }
QLineEdit,QPlainTextEdit,QListWidget,QTableWidget { background:#0D1720; border:1px solid #263B49; border-radius:4px; padding:4px; }
QHeaderView::section { background:#1D303E; color:#AFC4D2; padding:5px; border:0; }
QProgressBar { background:#0D1720; border:0; height:14px; text-align:center; }
QProgressBar::chunk { background:#319FAD; }
QScrollArea { border:0; }
QToolBar { border:0; spacing:4px; }
QToolTip { background:#203542; color:white; border:1px solid #62E5DC; }
'''


def configure(app):
    app.setStyle('Fusion')
    app.setFont(QtGui.QFont('Microsoft YaHei UI', 10))
