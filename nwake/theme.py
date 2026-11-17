"""Visual tokens and a shared app, taskbar and tray icon."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

BACKGROUND = "#EAF0F4"
SURFACE = "#FFFFFF"
SUBTLE = "#F3F7FA"
INK = "#142E3E"
MUTED = "#495F6C"
LINE = "#CDD9E0"
OCEAN = "#163B51"
MINT = "#B8F1D9"
TEAL = "#0D6559"
FOCUS = "#245EAA"
AMBER = "#7A4A0C"
DANGER = "#9C3436"
STATUS = {
    "online": ("在线", TEAL),
    "quiet": ("无响应", MUTED),
    "checking": ("待检测", MUTED),
    "waiting": ("等待上线", AMBER),
    "error": ("检测异常", DANGER),
}


def brand_image(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 64, size / 64)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(OCEAN))
    painter.drawRoundedRect(QRectF(1, 1, 62, 62), 13, 13)
    pen = QPen(QColor(SURFACE), 5.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(17, 47))
    path.lineTo(17, 18)
    path.lineTo(46, 47)
    path.lineTo(46, 18)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(MINT))
    painter.drawEllipse(QPointF(46, 18), 5.5, 5.5)
    painter.end()
    return image


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 96, 128, 256):
        icon.addPixmap(QPixmap.fromImage(brand_image(size)))
    return icon


STYLESHEET = f"""
QWidget {{ color: {INK}; }}
QMainWindow, QDialog, QWidget#main {{ background: {BACKGROUND}; }}
QFrame#masthead {{ background: {OCEAN}; border-radius: 12px; }}
QLabel[header="true"] {{ color: {SURFACE}; background: transparent; }}
QLabel#headerSub {{ color: #C9E5EE; }}
QLabel#counter {{ color: {MINT}; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel#feedback[tone="error"], QLabel#errorText {{ color: {DANGER}; }}
QLabel#feedback[tone="success"] {{ color: {TEAL}; }}
QFrame#empty, QTableWidget {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px;
}}
QTableWidget:focus {{ border-color: {FOCUS}; }}
QTableWidget {{ alternate-background-color: {SUBTLE}; outline: 0; }}
QTableWidget::item {{ padding: 0 8px; }}
QTableWidget::item:hover {{ background: #EEF5FA; }}
QTableWidget::item:selected {{ background: #DCEAF5; color: {INK}; }}
QTableWidget::item:focus {{ border-bottom: 1px solid {FOCUS}; }}
QHeaderView {{ background: {SUBTLE}; }}
QHeaderView::section {{
    background: {SUBTLE}; color: {MUTED}; padding: 6px 8px;
    border: 0; border-bottom: 1px solid {LINE}; font-weight: 600;
}}
QPushButton {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px;
    min-height: 28px; padding: 2px 10px; font-weight: 600;
}}
QPushButton:hover {{ background: #F3F8FC; border-color: #819CAC; }}
QPushButton:pressed {{ background: #DCEAF5; }}
QPushButton[variant="primary"] {{ background: {TEAL}; border-color: {TEAL}; color: white; }}
QPushButton[variant="primary"]:hover {{ background: #095348; }}
QPushButton[variant="primary"]:pressed {{ background: #084238; }}
QPushButton[variant="danger"] {{ background: {DANGER}; border-color: {DANGER}; color: white; }}
QPushButton[variant="danger"]:hover {{ background: #812528; }}
QPushButton[variant="danger"]:pressed {{ background: #6B1B1E; }}
QPushButton:disabled, QPushButton[variant="primary"]:disabled {{
    background: {SUBTLE}; border-color: {LINE}; color: #657781;
}}
QPushButton:focus, QCheckBox:focus {{ border-color: {FOCUS}; }}
QCheckBox {{ spacing: 6px; padding: 2px; border: 2px solid transparent; border-radius: 4px; }}
QCheckBox:hover {{ background: #F3F8FC; }}
QCheckBox:disabled {{ color: #657781; }}
QLineEdit {{
    background: {SURFACE}; border: 1px solid #9AADB9; border-radius: 6px;
    padding: 5px 8px; min-height: 23px; selection-background-color: {FOCUS};
}}
QLineEdit:focus {{ border-color: {FOCUS}; }}
QLineEdit[invalid="true"] {{ border-color: {DANGER}; }}
QPlainTextEdit {{ background: {SURFACE}; border: 1px solid {LINE}; padding: 4px; }}
QPlainTextEdit:focus {{ border-color: {FOCUS}; }}
QScrollBar:vertical {{ width: 13px; background: {SUBTLE}; margin: 0; }}
QScrollBar::handle:vertical {{ background: #849CA9; min-height: 24px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: #647F8E; }}
QScrollBar::handle:vertical:pressed {{ background: {OCEAN}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QToolTip {{ background: {INK}; color: {SURFACE}; padding: 5px; border: 0; }}
"""
