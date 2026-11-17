"""Scan a local network and add a checked batch of devices."""

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QSignalBlocker, Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nwake.dialogs import SelectAll, button, label
from nwake.discovery import LanNetwork, LanScanner, local_networks
from nwake.hosts import MAX_HOSTS, Host, HostError, StoreError

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked
_PARTIAL = Qt.CheckState.PartiallyChecked
_HOST = Qt.ItemDataRole.UserRole


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
        self.setMinimumSize(490, 335)
        self.resize(590, 410)
        self._scanner = scanner
        self._existing = existing
        self._save = save
        self._capacity = MAX_HOSTS - len(existing)
        self._rows: dict[str, int] = {}
        self._total = 0
        self._save_failed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        scope = QHBoxLayout()
        self.network = QComboBox()
        self.network.setAccessibleName("扫描网段")
        self.network.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.network.setMinimumContentsLength(24)
        self.network.setMaxVisibleItems(8)
        self.network.currentIndexChanged.connect(self._begin)
        scope.addWidget(self.network, 1)
        self.scan_button = button("重新扫描")
        self.scan_button.setFixedWidth(self.scan_button.sizeHint().width())
        self.scan_button.setAutoDefault(False)
        self.scan_button.clicked.connect(self._toggle_scan)
        scope.addWidget(self.scan_button)
        layout.addLayout(scope)

        self.feedback = QStackedWidget()
        self.status = label(muted=True)
        self.status.setMinimumHeight(23)
        self.feedback.addWidget(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName("扫描进度")
        self.progress_bar.setFormat("扫描中 %v / %m")
        self.progress_bar.setMinimumHeight(23)
        self.feedback.addWidget(self.progress_bar)
        layout.addWidget(self.feedback)

        self.results = QTableWidget(0, 4)
        self.results.setAccessibleName("扫描结果")
        self.results.setAccessibleDescription("勾选要添加的设备。")
        self.results.setHorizontalHeaderLabels(("", "主机名", "IPv4 地址", "MAC 地址"))
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setTabKeyNavigation(False)
        self.results.setColumnWidth(0, 39)
        self.results.setColumnWidth(2, 130)
        self.results.setColumnWidth(3, 158)
        header = self.results.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.results.verticalHeader().hide()
        self.results.verticalHeader().setDefaultSectionSize(34)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.results.setShowGrid(False)
        self.results.setWordWrap(False)
        self.results.setAlternatingRowColors(True)
        self.results.itemChanged.connect(self._sync_selection)
        layout.addWidget(self.results, 1)

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
        layout.addLayout(actions)

        scanner.found.connect(self._found)
        scanner.renamed.connect(self._renamed)
        scanner.progress.connect(self._progress)
        scanner.finished.connect(self._finished)
        self.finished.connect(scanner.cancel)
        self._reload_networks()

    def _reload_networks(self) -> None:
        current = self.network.currentData()
        networks = local_networks()
        with QSignalBlocker(self.network):
            self.network.clear()
            preferred = 0
            for index, network in enumerate(networks):
                caption = f"{network.scope} · {network.name}"
                self.network.addItem(caption, network)
                self.network.setItemData(index, escape(caption), Qt.ItemDataRole.ToolTipRole)
                if network == current:
                    preferred = index
            if networks:
                self.network.setCurrentIndex(preferred)
        self.network.setEnabled(bool(networks))
        self._begin()

    @Slot()
    def _begin(self) -> None:
        self._rows.clear()
        self.results.setRowCount(0)
        self._save_failed = False
        self.status.setToolTip("")
        self._sync_selection()
        network: LanNetwork | None = self.network.currentData()
        self.network.setToolTip(escape(self.network.currentText()))
        if network is None:
            self._scanner.cancel()
            self.scan_button.setText("重试")
            self._show_status("没有可用的 IPv4 网段")
            return
        self.scan_button.setText("停止")
        self._scanner.start(network, self._existing)

    @Slot()
    def _toggle_scan(self) -> None:
        if self._scanner.scanning:
            self._scanner.cancel()
            self.scan_button.setText("重新扫描")
            if not self._save_failed:
                self._show_status(f"已停止 · {self.results.rowCount()} 台")
        else:
            self._reload_networks()

    @Slot(int, int)
    def _progress(self, completed: int, total: int) -> None:
        self._total = total
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(completed)
        if completed < total and not self._save_failed:
            self.feedback.setCurrentWidget(self.progress_bar)

    @Slot(int, str)
    def _finished(self, failed: int, detail: str) -> None:
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
        self._show_status(text, detail)

    def _show_status(self, text: str, detail: str = "") -> None:
        self.status.setText(text)
        self.status.setToolTip(escape(detail))
        self.feedback.setCurrentWidget(self.status)

    @Slot(object)
    def _found(self, host: Host) -> None:
        row = self.results.rowCount()
        self._rows[host.ip] = row
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        with QSignalBlocker(self.results):
            self.results.insertRow(row)
            for column, text in enumerate(("", "—", host.ip, host.mac)):
                item = QTableWidgetItem(text)
                item.setFlags(flags)
                if column == 0:
                    item.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(_UNCHECKED)
                    item.setData(_HOST, host)
                    item.setData(Qt.ItemDataRole.AccessibleTextRole, f"勾选 {host.ip}")
                elif column >= 2:
                    item.setFont(QFont("Consolas", 10))
                self.results.setItem(row, column, item)
        self._sync_selection()

    @Slot(object)
    def _renamed(self, host: Host) -> None:
        row = self._rows.get(host.ip)
        if row is not None:
            with QSignalBlocker(self.results):
                self.results.item(row, 0).setData(_HOST, host)
                self.results.item(row, 1).setText(host.name)
                self.results.item(row, 1).setToolTip(escape(host.name))

    def _selected(self) -> tuple[Host, ...]:
        return tuple(
            self.results.item(row, 0).data(_HOST)
            for row in range(self.results.rowCount())
            if self.results.item(row, 0).checkState() == _CHECKED
        )

    @Slot()
    def _sync_selection(self) -> None:
        total = self.results.rowCount()
        count = len(self._selected())
        with QSignalBlocker(self.select_all):
            self.select_all.setCheckState(
                _UNCHECKED if not count else _CHECKED if count == total else _PARTIAL
            )
        self.select_all.setEnabled(bool(total))
        self.add_button.setEnabled(0 < count <= self._capacity)
        suffix = f" · 可添加 {self._capacity} 台" if count > self._capacity else ""
        self.selection.setText(f"已勾选 {count} 台{suffix}")

    @Slot(Qt.CheckState)
    def _select_all(self, state: Qt.CheckState) -> None:
        with QSignalBlocker(self.results):
            for row in range(self.results.rowCount()):
                self.results.item(row, 0).setCheckState(state)
        self._sync_selection()

    @Slot()
    def _add_selected(self) -> None:
        selected = self._selected()
        if not 0 < len(selected) <= self._capacity:
            return
        try:
            self._save(selected)
        except (StoreError, HostError) as error:
            self._save_failed = True
            text = "保存失败，请检查写入权限" if isinstance(error, StoreError) else str(error)
            self._show_status(text, str(error))
        else:
            self.accept()
