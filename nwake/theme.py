"""Visual tokens and a shared app, taskbar and tray icon."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleOption, QWidget

BACKGROUND = "#EAF0F4"
SURFACE = "#FFFFFF"
SUBTLE = "#F3F7FA"
INK = "#142E3E"
MUTED = "#495F6C"
LINE = "#D0DCE4"
RULE = "#E7EEF2"
CONTROL_EDGE = "#6F8695"
OCEAN = "#163B51"
OCEAN_DEEP = "#102F42"
MINT = "#B8F1D9"
TEAL = "#0D6559"
TEAL_WASH = "#E3F4ED"
FOCUS = "#245EAA"
FOCUS_WASH = "#E2EDF9"
AMBER = "#7A4A0C"
AMBER_WASH = "#F8EDD8"
DANGER = "#9C3436"
DANGER_WASH = "#FBE9E9"
STATUS = {
    "online": ("在线", TEAL, TEAL_WASH),
    "quiet": ("无响应", MUTED, SUBTLE),
    "checking": ("待检测", MUTED, SUBTLE),
    "waiting": ("等待上线", AMBER, AMBER_WASH),
    "error": ("检测异常", DANGER, DANGER_WASH),
}


def ui_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Segoe UI", size, weight)
    font.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
    return font


class NwakeStyle(QProxyStyle):
    def __init__(self):
        super().__init__("Fusion")

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        if metric in (QStyle.PixelMetric.PM_IndicatorWidth, QStyle.PixelMetric.PM_IndicatorHeight):
            return 16
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element not in (
            QStyle.PrimitiveElement.PE_IndicatorCheckBox,
            QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
        ):
            super().drawPrimitive(element, option, painter, widget)
            return

        state = QStyle.StateFlag
        partial = bool(option.state & state.State_NoChange)
        marked = partial or bool(option.state & state.State_On)
        enabled = bool(option.state & state.State_Enabled)
        edge = TEAL if marked else CONTROL_EDGE
        fill = TEAL if marked else SURFACE
        rect = QRectF(option.rect).adjusted(1, 1, -1, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(edge if enabled else LINE), 1))
        painter.setBrush(QColor(fill if enabled else SUBTLE))
        painter.drawRoundedRect(rect, 3, 3)
        if marked:
            pen = QPen(QColor(SURFACE if enabled else MUTED), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            x, y = rect.center().x(), rect.center().y()
            if partial:
                painter.drawLine(QPointF(x - 3, y), QPointF(x + 3, y))
            else:
                painter.drawPolyline(
                    [QPointF(x - 3.5, y), QPointF(x - 1, y + 2.5), QPointF(x + 3.5, y - 2.5)]
                )
        painter.restore()


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
QFrame#masthead {{
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 {OCEAN_DEEP}, stop: 1 {OCEAN});
    border-radius: 12px;
}}
QFrame#panel {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame#scanFeedback {{ background: {SUBTLE}; border-radius: 8px; }}
QLabel[header="true"] {{ color: {SURFACE}; background: transparent; }}
QLabel#headerSub {{ color: #D5EBF1; background: transparent; }}
QLabel#counter {{ color: {MINT}; background: transparent; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel[tone="error"] {{ color: {DANGER}; }}
QLabel[tone="success"], QLabel#nameSummary {{ color: {TEAL}; }}
QLabel#formNote {{ background: {SUBTLE}; border-radius: 7px; padding: 4px 9px; }}
QLabel#formNote[tone="error"] {{ background: {DANGER_WASH}; }}
QLabel#scanEmpty {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
QTableWidget {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px;
    alternate-background-color: #FAFCFD; outline: 0;
}}
QTableWidget:focus {{ border-color: {FOCUS}; }}
QTableWidget::item {{ padding: 0 10px; border-bottom: 1px solid {RULE}; }}
QTableWidget::item:hover {{ background: {SUBTLE}; }}
QTableWidget::item:selected {{ background: {FOCUS_WASH}; color: {INK}; }}
QTableWidget::item:focus {{ border-bottom: 1px solid {FOCUS}; }}
QHeaderView {{ background: {SUBTLE}; }}
QHeaderView::section {{
    background: {SUBTLE}; color: {MUTED}; padding: 6px 10px;
    border: 0; border-bottom: 1px solid {LINE}; font-weight: 600;
}}
QPushButton {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 7px;
    min-height: 29px; padding: 2px 11px; font-weight: 600;
}}
QPushButton:hover {{ background: {SUBTLE}; border-color: #819CAC; }}
QPushButton:pressed {{ background: {FOCUS_WASH}; }}
QPushButton[variant="quiet"] {{ background: transparent; border-color: transparent; }}
QPushButton[variant="quiet"]:hover {{ background: {SUBTLE}; }}
QPushButton[variant="quiet"]:pressed {{ background: {FOCUS_WASH}; }}
QPushButton[variant="accent"] {{ background: {TEAL_WASH}; border-color: #B3DAD0; color: {TEAL}; }}
QPushButton[variant="accent"]:hover {{ background: #CFEBE0; border-color: #7EAF9D; }}
QPushButton[variant="accent"]:pressed {{ background: #BEE1D4; }}
QPushButton[variant="primary"] {{ background: {TEAL}; border-color: {TEAL}; color: white; }}
QPushButton[variant="primary"]:hover {{ background: #095348; }}
QPushButton[variant="primary"]:pressed {{ background: #084238; }}
QPushButton[variant="danger"] {{ background: {DANGER}; border-color: {DANGER}; color: white; }}
QPushButton[variant="danger"]:hover {{ background: #812528; }}
QPushButton[variant="danger"]:pressed {{ background: #6B1B1E; }}
QPushButton:disabled, QPushButton[variant="primary"]:disabled,
QPushButton[variant="accent"]:disabled {{
    background: {SUBTLE}; border-color: {LINE}; color: #657781;
}}
QPushButton[variant="quiet"]:disabled {{ background: transparent; border-color: transparent; }}
QPushButton:focus, QPushButton[variant]:focus, QCheckBox:focus {{ border-color: {FOCUS}; }}
QPushButton[variant="primary"]:focus, QPushButton[variant="danger"]:focus {{
    border: 2px solid #96CAFF; padding: 1px 10px;
}}
QCheckBox {{ spacing: 6px; padding: 2px; border: 2px solid transparent; border-radius: 4px; }}
QCheckBox:hover {{ background: {SUBTLE}; }}
QCheckBox:disabled {{ color: #657781; }}
QLineEdit {{
    background: {SURFACE}; border: 1px solid {CONTROL_EDGE}; border-radius: 7px;
    padding: 5px 9px; min-height: 24px;
    selection-background-color: {FOCUS_WASH}; selection-color: {INK};
}}
QLineEdit:focus {{
    border-color: {FOCUS}; selection-background-color: {FOCUS}; selection-color: {SURFACE};
}}
QLineEdit[invalid="true"] {{ border-color: {DANGER}; }}
QComboBox {{
    background: {SURFACE}; border: 1px solid {CONTROL_EDGE}; border-radius: 7px;
    padding: 4px 28px 4px 9px; min-height: 25px;
}}
QComboBox:hover {{ background: {SUBTLE}; }}
QComboBox:focus {{ border-color: {FOCUS}; }}
QComboBox:disabled {{ color: {MUTED}; background: {SUBTLE}; border-color: {LINE}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: top right; width: 26px; border: 0;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {LINE};
    selection-background-color: {FOCUS_WASH}; selection-color: {INK}; outline: 0;
}}
QProgressBar {{ background: {LINE}; border: 0; border-radius: 2px; }}
QProgressBar::chunk {{ background: {TEAL}; border-radius: 2px; }}
QPlainTextEdit {{ background: {SURFACE}; border: 1px solid {LINE}; padding: 4px; }}
QPlainTextEdit:focus {{ border-color: {FOCUS}; }}
QScrollBar:vertical {{ width: 11px; background: {SUBTLE}; margin: 0; }}
QScrollBar::handle:vertical {{ background: #78919F; min-height: 24px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: #647F8E; }}
QScrollBar::handle:vertical:pressed {{ background: {OCEAN}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QToolTip {{ background: {INK}; color: {SURFACE}; padding: 5px; border: 0; }}
"""
