"""Row layout and keyboard selection shared by the two device lists."""

from PySide6.QtCore import QModelIndex, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
)

from nwake.theme import STATUS


class DeviceTable(QTableWidget):
    def __init__(self, name: str, last_column: str, last_width: int):
        super().__init__(0, 4)
        self.setAccessibleName(name)
        self.setHorizontalHeaderLabels(("", "主机名", "IPv4 地址", last_column))
        self.address_font = QFont("Consolas", 10)
        self.setColumnWidth(0, 40)
        self.setColumnWidth(
            2, max(132, QFontMetrics(self.address_font).horizontalAdvance("255.255.255.255") + 22)
        )
        self.setColumnWidth(3, last_width)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setFixedHeight(max(32, header.fontMetrics().height() + 14))
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(36)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setTabKeyNavigation(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        check = self.item(self.currentRow(), 0)
        if event.key() == Qt.Key.Key_Space and not event.modifiers() and check is not None:
            checked = check.checkState() == Qt.CheckState.Checked
            check.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
            event.accept()
            return
        super().keyPressEvent(event)


class StatusPill(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        key = index.data(Qt.ItemDataRole.UserRole)
        if key not in STATUS:
            super().paint(painter, option, index)
            return
        text, foreground, background = STATUS[key]
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)
        cell.text = ""
        cell.widget.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, cell, painter, cell.widget
        )

        metrics = cell.fontMetrics
        height = metrics.height() + 8
        width = metrics.horizontalAdvance(text) + 28
        pill = QRectF(cell.rect.left() + 10, cell.rect.center().y() - height / 2, width, height)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setBrush(QColor(foreground))
        painter.drawEllipse(QRectF(pill.left() + 8, pill.center().y() - 2.5, 5, 5))
        painter.setFont(cell.font)
        painter.setPen(QColor(foreground))
        painter.drawText(pill.adjusted(19, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()
