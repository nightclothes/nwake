"""Scan a local network and add a checked batch of devices."""

from collections.abc import Callable
from html import escape
from ipaddress import IPv4Interface

from PySide6.QtCore import QPointF, QSignalBlocker, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nwake.device_table import DeviceTable
from nwake.dialogs import SelectAll, button, label, set_label_tone
from nwake.discovery import LanNetwork, LanScanner, local_networks
from nwake.hosts import MAX_HOSTS, Host, HostError, StoreError
from nwake.theme import MUTED, ui_font

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked
_PARTIAL = Qt.CheckState.PartiallyChecked
_HOST = Qt.ItemDataRole.UserRole


class _NetworkPicker(QComboBox):
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(MUTED), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        x, y = self.width() - 15, self.height() / 2
        painter.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])
        painter.end()


class DiscoveryDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        scanner: LanScanner,
        existing: tuple[Host, ...],
        save: Callable[[tuple[Host, ...]], None],
    ):
        super().__init__(parent)
        self.setWindowTitle("扫描局域网")
        self.setMinimumSize(510, 376)
        self.resize(620, 454)
        self._scanner = scanner
        self._existing = existing
        self._save = save
        self._capacity = MAX_HOSTS - len(existing)
        self._rows: dict[str, int] = {}
        self._pending_names: set[str] = set()
        self._active_network: tuple[str, IPv4Interface] | None = None
        self._rescan_checked: set[tuple[str, str]] = set()
        self._total = 0
        self._named = 0
        self._save_failed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        panel = QFrame(objectName="panel")
        workspace = QVBoxLayout(panel)
        workspace.setContentsMargins(12, 12, 12, 10)
        workspace.setSpacing(10)
        layout.addWidget(panel)

        scope = QHBoxLayout()
        scope.setSpacing(8)
        self.network = _NetworkPicker()
        self.network.setAccessibleName("扫描网段")
        self.network.setAccessibleDescription("切换网段后开始扫描。")
        self.network.setPlaceholderText("—")
        self.network.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.network.setMinimumContentsLength(12)
        self.network.setMaxVisibleItems(8)
        self.network.currentIndexChanged.connect(self._begin)
        scope_label = label("扫描网段", muted=True)
        scope_label.setBuddy(self.network)
        scope.addWidget(scope_label)
        scope.addWidget(self.network, 1)
        self.scan_button = button("重新扫描")
        self.scan_button.setFixedWidth(self.scan_button.sizeHint().width())
        self.scan_button.setAutoDefault(False)
        self.scan_button.clicked.connect(self._toggle_scan)
        scope.addWidget(self.scan_button)
        workspace.addLayout(scope)

        feedback = QFrame(objectName="scanFeedback")
        feedback_layout = QVBoxLayout(feedback)
        feedback_layout.setContentsMargins(10, 7, 10, 7)
        feedback_layout.setSpacing(5)
        readout = QHBoxLayout()
        self.status = label()
        self.status.setFont(ui_font(10, QFont.Weight.DemiBold))
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        readout.addWidget(self.status, 1)
        self.name_summary = label()
        self.name_summary.setObjectName("nameSummary")
        readout.addWidget(self.name_summary)
        feedback_layout.addLayout(readout)
        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName("扫描进度")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        progress_size = self.progress_bar.sizePolicy()
        progress_size.setRetainSizeWhenHidden(True)
        self.progress_bar.setSizePolicy(progress_size)
        feedback_layout.addWidget(self.progress_bar)
        workspace.addWidget(feedback)

        mac_width = QFontMetrics(QFont("Consolas", 10)).horizontalAdvance("FF:FF:FF:FF:FF:FF") + 24
        self.results = DeviceTable("扫描结果", "MAC 地址", max(154, mac_width))
        self.results.setAccessibleDescription("勾选要添加的设备。")
        self.results.itemChanged.connect(self._sync_selection)
        self.result_pages = QStackedWidget()
        self.result_pages.addWidget(self.results)
        self.empty_hint = label(muted=True)
        self.empty_hint.setObjectName("scanEmpty")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.result_pages.addWidget(self.empty_hint)
        workspace.addWidget(self.result_pages, 1)

        actions = QHBoxLayout()
        self.select_all = SelectAll("全选")
        self.select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all.checkStateChanged.connect(self._select_all)
        actions.addWidget(self.select_all)
        self.selection = label(muted=True)
        actions.addWidget(self.selection)
        actions.addStretch()
        close = button("关闭")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        self.add_button = button("添加所选", "primary")
        self.add_button.setAutoDefault(False)
        self.add_button.clicked.connect(self._add_selected)
        actions.addWidget(self.add_button)
        workspace.addLayout(actions)

        QWidget.setTabOrder(self.network, self.scan_button)
        QWidget.setTabOrder(self.scan_button, self.results)
        QWidget.setTabOrder(self.results, self.select_all)
        QWidget.setTabOrder(self.select_all, close)
        QWidget.setTabOrder(close, self.add_button)

        scanner.found.connect(self._found)
        scanner.renamed.connect(self._renamed)
        scanner.name_unresolved.connect(self._name_unresolved)
        scanner.progress.connect(self._progress)
        scanner.finished.connect(self._finished)
        self.finished.connect(scanner.cancel)
        self._reload_networks()

    @staticmethod
    def _network_key(network: LanNetwork | None) -> tuple[str, IPv4Interface] | None:
        return (network.name, network.source) if network is not None else None

    def _reload_networks(self) -> None:
        current = self._network_key(self.network.currentData())
        networks = local_networks()
        with QSignalBlocker(self.network):
            self.network.clear()
            preferred = 0
            for index, network in enumerate(networks):
                caption = f"{network.scope} · {network.name}"
                self.network.addItem(caption, network)
                self.network.setItemData(index, escape(caption), Qt.ItemDataRole.ToolTipRole)
                if self._network_key(network) == current:
                    preferred = index
            if networks:
                self.network.setCurrentIndex(preferred)
        self.network.setEnabled(bool(networks))
        self._begin()

    @Slot()
    def _begin(self) -> None:
        network: LanNetwork | None = self.network.currentData()
        network_key = self._network_key(network)
        if network_key is not None and network_key == self._active_network:
            self._rescan_checked.update((host.ip, host.mac) for host in self._selected())
        else:
            self._rescan_checked.clear()
        self._active_network = network_key
        self._rows.clear()
        self._pending_names.clear()
        self.results.setRowCount(0)
        self.result_pages.setCurrentWidget(self.results)
        self._named = 0
        self._save_failed = False
        self.status.setToolTip("")
        self._sync_names()
        self._sync_selection()
        self.network.setToolTip(escape(self.network.currentText()))
        if network is None:
            self._scanner.cancel()
            self.scan_button.setText("重试")
            self._show_status("没有可用的 IPv4 网段")
            self._show_empty("连接到局域网后重试。")
            return
        self.scan_button.setText("停止")
        self._scanner.start(network, self._existing)

    @Slot()
    def _toggle_scan(self) -> None:
        if self._scanner.scanning:
            self._scanner.cancel()
            self.scan_button.setText("重新扫描")
            self._mark_pending_stopped()
            if not self._save_failed:
                self._show_status(f"已停止 · {self.results.rowCount()} 台")
            if not self.results.rowCount():
                self._show_empty("可重新扫描以查找设备。")
        else:
            self._reload_networks()

    @Slot(int, int)
    def _progress(self, completed: int, total: int) -> None:
        self._total = total
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(completed)
        if self._save_failed:
            return
        if completed < total:
            self.status.setText(f"正在扫描 · {completed} / {total}")
            set_label_tone(self.status, "info")
            self.progress_bar.show()
        elif self._scanner.scanning:
            self._show_status(f"发现 {self.results.rowCount()} 台 · 正在查询主机名")

    @Slot(int, str)
    def _finished(self, failed: int, detail: str) -> None:
        self._rescan_checked.clear()
        self.scan_button.setText("重新扫描")
        if self._save_failed:
            return
        count = self.results.rowCount()
        if failed and failed == self._total:
            text = "扫描失败，请检查网络"
        elif failed:
            text = f"发现 {count} 台 · 部分地址扫描失败"
        elif count:
            text = f"发现 {count} 台"
        else:
            text = "未发现可添加的设备"
        self._show_status(text, detail, error=bool(failed))
        if not count:
            self._show_empty("可切换网段后重新扫描。")

    def _show_status(self, text: str, detail: str = "", *, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setToolTip(escape(detail or text))
        set_label_tone(self.status, "error" if error else "info")
        self.progress_bar.hide()

    def _show_empty(self, text: str) -> None:
        self.empty_hint.setText(text)
        self.result_pages.setCurrentWidget(self.empty_hint)

    @Slot(object)
    def _found(self, host: Host) -> None:
        row = self.results.rowCount()
        self._rows[host.ip] = row
        self._pending_names.add(host.ip)
        identity = (host.ip, host.mac)
        checked = _CHECKED if identity in self._rescan_checked else _UNCHECKED
        self._rescan_checked.discard(identity)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        with QSignalBlocker(self.results):
            self.results.insertRow(row)
            for column, text in enumerate(("", "查询中", host.ip, host.mac)):
                item = QTableWidgetItem(text)
                item.setFlags(flags)
                if column == 0:
                    item.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(checked)
                    item.setData(_HOST, host)
                    item.setData(Qt.ItemDataRole.AccessibleTextRole, f"勾选 {host.ip}")
                elif column == 1:
                    item.setForeground(QBrush(QColor(MUTED)))
                else:
                    item.setFont(self.results.address_font)
                self.results.setItem(row, column, item)
        self._sync_names()
        self._sync_selection()

    @Slot(object)
    def _renamed(self, host: Host) -> None:
        row = self._rows.get(host.ip)
        if row is not None:
            self._pending_names.discard(host.ip)
            with QSignalBlocker(self.results):
                check = self.results.item(row, 0)
                if check.data(_HOST).name == host.ip:
                    self._named += 1
                check.setData(_HOST, host)
                check.setData(Qt.ItemDataRole.AccessibleTextRole, f"勾选 {host.name}，{host.ip}")
                name = self.results.item(row, 1)
                name.setText(host.name)
                name.setForeground(QBrush())
                name.setFont(ui_font(10, QFont.Weight.DemiBold))
                name.setToolTip(escape(host.name))
            self._sync_names()
            if check.checkState() == _CHECKED:
                self._sync_selection()

    @Slot(str)
    def _name_unresolved(self, ip: str) -> None:
        if ip not in self._pending_names:
            return
        self._pending_names.remove(ip)
        row = self._rows[ip]
        with QSignalBlocker(self.results):
            name = self.results.item(row, 1)
            name.setText("未识别")
            name.setToolTip("添加后可在电脑列表中编辑主机名。")
        if self.results.item(row, 0).checkState() == _CHECKED:
            self._sync_selection()

    def _sync_names(self) -> None:
        total = self.results.rowCount()
        self.name_summary.setText(f"已识别主机名 {self._named} / {total}" if total else "")

    def _mark_pending_stopped(self) -> None:
        with QSignalBlocker(self.results):
            for ip in self._pending_names:
                name = self.results.item(self._rows[ip], 1)
                name.setText("—")
                name.setToolTip("主机名查询已停止。")
        self._pending_names.clear()
        self._sync_selection()

    def _selected(self) -> tuple[Host, ...]:
        return tuple(
            self.results.item(row, 0).data(_HOST)
            for row in range(self.results.rowCount())
            if self.results.item(row, 0).checkState() == _CHECKED
        )

    @Slot()
    def _sync_selection(self) -> None:
        total = self.results.rowCount()
        selected = self._selected()
        count = len(selected)
        waiting = any(host.ip in self._pending_names for host in selected)
        over_capacity = count > self._capacity
        with QSignalBlocker(self.select_all):
            self.select_all.setCheckState(
                _UNCHECKED if not count else _CHECKED if count == total else _PARTIAL
            )
        self.select_all.setEnabled(bool(total))
        self.add_button.setEnabled(bool(count) and not over_capacity and not waiting)
        hint = ""
        suffix = ""
        if over_capacity:
            suffix = f" · 可添加 {self._capacity} 台"
        elif waiting:
            suffix = " · 等待主机名"
            hint = "等待勾选设备的主机名，或点击「停止」后按 IP 添加。"
        self.selection.setText(f"已勾选 {count} 台{suffix}")
        self.selection.setToolTip(hint)
        self.add_button.setToolTip(hint)
        set_label_tone(self.selection, "error" if over_capacity else "info")

    @Slot(Qt.CheckState)
    def _select_all(self, state: Qt.CheckState) -> None:
        if state == _UNCHECKED:
            self._rescan_checked.clear()
        with QSignalBlocker(self.results):
            for row in range(self.results.rowCount()):
                self.results.item(row, 0).setCheckState(state)
        self._sync_selection()

    @Slot()
    def _add_selected(self) -> None:
        selected = self._selected()
        if not 0 < len(selected) <= self._capacity or any(
            host.ip in self._pending_names for host in selected
        ):
            return
        try:
            self._save(selected)
        except (StoreError, HostError) as error:
            self._save_failed = True
            text = "保存失败，请检查写入权限" if isinstance(error, StoreError) else str(error)
            self._show_status(text, str(error), error=True)
        else:
            self.accept()
