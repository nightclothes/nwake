"""The device list opened from the Windows notification area."""

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nwake.device_table import DeviceTable, StatusPill
from nwake.dialogs import HostDialog, SelectAll, button, label, message, set_label_tone
from nwake.discovery import LanScanner
from nwake.discovery_dialog import DiscoveryDialog
from nwake.hosts import MAX_HOSTS, Host, HostStore, StoreError
from nwake.monitor import Monitor
from nwake.theme import STATUS, ui_font

_CHECKED = Qt.CheckState.Checked
_PARTIAL = Qt.CheckState.PartiallyChecked
_UNCHECKED = Qt.CheckState.Unchecked


class DeviceWindow(QMainWindow):
    exit_requested = Signal()

    def __init__(self, icon: QIcon, store: HostStore, monitor: Monitor, load_error: str = ""):
        super().__init__()
        self.setWindowTitle("Nwake · 局域网开机")
        self.setWindowIcon(icon)
        self.setMinimumSize(470, 404)
        self.resize(570, 498)
        self.store = store
        self.monitor = monitor
        monitor.setParent(self)
        self.scanner = LanScanner(self)
        self.load_error = load_error
        self.can_hide: Callable[[], bool] = lambda: False
        self.exiting = False
        self._shown_hosts: tuple[Host, ...] = ()
        self._details: tuple[str, str] | None = None
        self._preferred_host: Host | None = None

        root = QWidget(objectName="main")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        masthead = QFrame(objectName="masthead")
        head = QHBoxLayout(masthead)
        head.setContentsMargins(14, 10, 17, 10)
        head.setSpacing(10)
        logo = label()
        logo.setPixmap(icon.pixmap(40, 40))
        head.addWidget(logo)
        title = label("Nwake")
        title.setProperty("header", True)
        title.setFont(ui_font(19, QFont.Weight.DemiBold))
        head.addWidget(title)
        head.addStretch()
        summary = QVBoxLayout()
        summary.setSpacing(0)
        self.counter = label("0 / 0")
        self.counter.setObjectName("counter")
        self.counter.setFont(QFont("Consolas", 17, QFont.Weight.Bold))
        self.counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        summary.addWidget(self.counter)
        summary_label = label("在线 / 总数")
        summary_label.setObjectName("headerSub")
        summary_label.setFont(ui_font(9))
        summary_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        summary.addWidget(summary_label)
        head.addLayout(summary)
        layout.addWidget(masthead)

        panel = QFrame(objectName="panel")
        workspace = QVBoxLayout(panel)
        workspace.setContentsMargins(12, 11, 12, 8)
        workspace.setSpacing(9)
        layout.addWidget(panel, 1)

        list_actions = QHBoxLayout()
        list_actions.setSpacing(8)
        list_title = label("电脑列表")
        list_title.setFont(ui_font(12, QFont.Weight.DemiBold))
        list_actions.addWidget(list_title)
        list_actions.addStretch()
        self.refresh_button = button("刷新", "quiet")
        self.refresh_button.setToolTip("刷新电脑在线状态")
        self.refresh_button.clicked.connect(monitor.refresh)
        list_actions.addWidget(self.refresh_button)
        self.scan_button = button("扫描局域网", "accent")
        self.scan_button.clicked.connect(self._open_discovery)
        list_actions.addWidget(self.scan_button)
        self.add_button = button("添加电脑")
        self.add_button.clicked.connect(lambda: self.edit_host(None))
        list_actions.addWidget(self.add_button)
        workspace.addLayout(list_actions)

        self.pages = QStackedWidget()
        self.empty = QFrame()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(14, 16, 14, 16)
        empty_layout.setSpacing(7)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption = label("电脑列表不可用" if load_error else "暂无电脑")
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        caption.setFont(ui_font(13, QFont.Weight.DemiBold))
        empty_layout.addWidget(caption)
        guidance = label(
            "请查看详情，修复后重新打开。"
            if load_error
            else "扫描局域网查找设备，或填写 IP 和 MAC 手动添加。",
            muted=True,
        )
        guidance.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        guidance.setWordWrap(True)
        empty_layout.addWidget(guidance)
        self.pages.addWidget(self.empty)

        self.table = DeviceTable("电脑列表", "状态", 113)
        self.table.setAccessibleDescription("勾选复选框可唤醒或移除电脑。编辑作用于高亮行。")
        self.table.setItemDelegateForColumn(3, StatusPill(self.table))
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemSelectionChanged.connect(self._sync_actions)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.pages.addWidget(self.table)
        workspace.addWidget(self.pages, 1)

        self.row_actions = QWidget()
        row_actions = QHBoxLayout(self.row_actions)
        row_actions.setContentsMargins(2, 0, 2, 0)
        self.select_all = SelectAll("全选")
        self.select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all.checkStateChanged.connect(self._select_all)
        row_actions.addWidget(self.select_all)
        self.selection_summary = label("已勾选 0 台", muted=True)
        row_actions.addWidget(self.selection_summary)
        row_actions.addStretch()
        self.edit_button = button("编辑", "quiet")
        self.edit_button.clicked.connect(self._edit_active)
        row_actions.addWidget(self.edit_button)
        self.remove_button = button("移除所选", "quiet")
        self.remove_button.setMinimumWidth(self.remove_button.sizeHint().width())
        self.remove_button.clicked.connect(self._remove_hosts)
        row_actions.addWidget(self.remove_button)
        workspace.addWidget(self.row_actions)

        self.footer = QFrame(objectName="panel")
        footer = QHBoxLayout(self.footer)
        footer.setContentsMargins(12, 7, 10, 7)
        info = QVBoxLayout()
        info.setSpacing(1)
        self.freshness = label(muted=True)
        info.addWidget(self.freshness)
        self.feedback = label()
        self.feedback.setObjectName("feedback")
        info.addWidget(self.feedback)
        footer.addLayout(info, 1)
        self.detail_button = button("详情", "quiet")
        self.detail_button.clicked.connect(self._show_details)
        detail_size = self.detail_button.sizePolicy()
        detail_size.setRetainSizeWhenHidden(True)
        self.detail_button.setSizePolicy(detail_size)
        self.detail_button.hide()
        footer.addWidget(self.detail_button)
        self.wake_button = button("唤醒所选", "primary")
        self.wake_button.setFixedWidth(max(112, self.wake_button.sizeHint().width()))
        self.wake_button.clicked.connect(self._wake_selected)
        footer.addWidget(self.wake_button)
        layout.addWidget(self.footer)

        QWidget.setTabOrder(self.refresh_button, self.scan_button)
        QWidget.setTabOrder(self.scan_button, self.add_button)
        QWidget.setTabOrder(self.add_button, self.table)
        QWidget.setTabOrder(self.table, self.select_all)
        QWidget.setTabOrder(self.select_all, self.edit_button)
        QWidget.setTabOrder(self.edit_button, self.remove_button)
        QWidget.setTabOrder(self.remove_button, self.detail_button)
        QWidget.setTabOrder(self.detail_button, self.wake_button)
        self.monitor.changed.connect(self._render)
        self.monitor.wake_finished.connect(self._wake_finished)
        if load_error:
            self._notice("无法读取电脑列表。", "error", f"{load_error}\n\n文件：{store.path}")
        self._render()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.exiting and self.can_hide():
            self.hide()
            event.ignore()
        else:
            event.accept()
            if not self.exiting:
                self.exit_requested.emit()

    def _active(self) -> Host | None:
        rows = self.table.selectionModel().selectedRows()
        return self._shown_hosts[rows[0].row()] if rows else None

    def _selected(self) -> tuple[Host, ...]:
        return tuple(
            host
            for index, host in enumerate(self._shown_hosts)
            if self.table.item(index, 0).checkState() == _CHECKED
        )

    def _rebuild_table(self) -> None:
        checked = set(self._selected())
        active = self._preferred_host or self._active()
        self._preferred_host = None
        with QSignalBlocker(self.table):
            self.table.clearContents()
            self.table.clearSelection()
            self._shown_hosts = self.monitor.hosts
            self.table.setRowCount(len(self._shown_hosts))
            base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            for row, host in enumerate(self._shown_hosts):
                for column, text in enumerate(("", host.name, host.ip, "")):
                    item = QTableWidgetItem(text)
                    item.setFlags(base_flags)
                    if column == 0:
                        item.setFlags(base_flags | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(_CHECKED if host in checked else _UNCHECKED)
                        item.setData(Qt.ItemDataRole.AccessibleTextRole, f"勾选 {host.name}")
                    elif column == 1:
                        item.setFont(ui_font(10, QFont.Weight.DemiBold))
                        item.setToolTip(escape(f"{host.name} · {host.mac}"))
                    elif column == 2:
                        item.setFont(self.table.address_font)
                    elif column == 3:
                        item.setFont(ui_font(9, QFont.Weight.DemiBold))
                    self.table.setItem(row, column, item)
            if active in self._shown_hosts:
                index = self._shown_hosts.index(active)
                self.table.setCurrentCell(index, 1)
                self.table.scrollToItem(self.table.item(index, 1))

    @Slot()
    def _render(self) -> None:
        if self._shown_hosts != self.monitor.hosts:
            self._rebuild_table()
        self.pages.setCurrentWidget(self.table if self._shown_hosts else self.empty)
        online = 0
        with QSignalBlocker(self.table):
            for index, host in enumerate(self._shown_hosts):
                key, detail = self.monitor.readout(host)
                status = self.table.item(index, 3)
                if status.data(Qt.ItemDataRole.UserRole) != key:
                    status.setText(STATUS[key][0])
                    status.setData(Qt.ItemDataRole.UserRole, key)
                status.setToolTip(escape(detail))
                online += key == "online"
        self.counter.setText(f"{online} / {len(self._shown_hosts)}")
        self.counter.setAccessibleName(f"{online} 台在线，共 {len(self._shown_hosts)} 台电脑")
        last_scan = self.monitor.last_scan
        if self._shown_hosts and self.monitor.scanning:
            self.freshness.setText("检测中…")
        elif self._shown_hosts and last_scan is not None:
            self.freshness.setText(f"最近检测 {last_scan:%H:%M:%S}")
        elif self._shown_hosts:
            self.freshness.setText("点击「刷新」检测在线状态")
        else:
            self.freshness.clear()
        self._sync_actions()

    @Slot()
    def _sync_actions(self) -> None:
        total = len(self._shown_hosts)
        count = len(self._selected())
        self.row_actions.setVisible(bool(total))
        self.footer.setVisible(bool(total or self.feedback.text()))
        self.wake_button.setVisible(bool(total))
        with QSignalBlocker(self.select_all):
            self.select_all.setCheckState(
                _UNCHECKED if not count else _CHECKED if count == total else _PARTIAL
            )
        self.select_all.setEnabled(bool(total))
        self.selection_summary.setText(f"已勾选 {count} 台")
        editable = not self.load_error and not self.monitor.sending
        self.add_button.setEnabled(editable and total < MAX_HOSTS)
        self.add_button.setToolTip("最多管理 64 台电脑。" if total == MAX_HOSTS else "")
        self.scan_button.setEnabled(self.add_button.isEnabled())
        self.scan_button.setToolTip(self.add_button.toolTip())
        has_active_row = self._active() is not None
        self.edit_button.setEnabled(editable and has_active_row)
        self.remove_button.setEnabled(editable and (count > 0 or has_active_row))
        self.remove_button.setText("移除所选" if count else "移除")
        self.remove_button.setToolTip("从列表移除勾选的电脑" if count else "从列表移除当前行")
        self.refresh_button.setEnabled(bool(total) and not self.monitor.scanning)
        self.wake_button.setEnabled(bool(count) and not self.monitor.sending)
        self.wake_button.setText("正在发送…" if self.monitor.sending else "唤醒所选")
        self.wake_button.setToolTip("勾选要唤醒的电脑。" if not count else "")

    @Slot(QTableWidgetItem)
    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._sync_actions()

    @Slot(Qt.CheckState)
    def _select_all(self, state: Qt.CheckState) -> None:
        with QSignalBlocker(self.table):
            for index in range(len(self._shown_hosts)):
                self.table.item(index, 0).setCheckState(state)
        self._sync_actions()

    @Slot(int, int)
    def _open_row(self, row: int, column: int) -> None:
        if column > 0 and self.edit_button.isEnabled():
            self.edit_host(self._shown_hosts[row])

    @Slot()
    def _edit_active(self) -> None:
        if host := self._active():
            self.edit_host(host)

    def _save_inventory(self, hosts: tuple[Host, ...], preferred: Host | None = None) -> None:
        self.store.save(hosts)
        if hosts != self.monitor.hosts:
            self._preferred_host = preferred
            self.monitor.set_hosts(hosts)

    @Slot()
    def _open_discovery(self) -> None:
        def save(hosts: tuple[Host, ...]) -> None:
            self._save_inventory((*self.monitor.hosts, *hosts), hosts[0])
            self._notice(f"已添加 {len(hosts)} 台。", "success")

        dialog = DiscoveryDialog(self, self.scanner, self.monitor.hosts, save)
        if dialog.exec():
            self.table.setFocus()
        dialog.deleteLater()

    def edit_host(self, original: Host | None) -> None:
        def save(host: Host) -> None:
            hosts = self.monitor.hosts
            new = (
                tuple(host if existing == original else existing for existing in hosts)
                if original
                else (*hosts, host)
            )
            self._save_inventory(new, host)
            self._notice("已保存电脑。", "success")

        dialog = HostDialog(self, save, original)
        if dialog.exec():
            self.table.setFocus()
        dialog.deleteLater()

    @Slot()
    def _remove_hosts(self) -> None:
        hosts = self._selected()
        if not hosts:
            active = self._active()
            if active is None:
                return
            hosts = (active,)

        count = len(hosts)
        title = action = "移除电脑"
        prompt = f"从电脑列表移除「{hosts[0].name}」？"
        detail = ""
        if count > 1:
            title = "批量移除电脑"
            prompt = f"从电脑列表移除这 {count} 台设备？"
            action = f"移除 {count} 台"
            detail = "\n".join(
                host.ip if host.name == host.ip else f"{host.name} · {host.ip}" for host in hosts
            )
        if not message(self, title, prompt, detail=detail, action=action, danger=True):
            return

        targets = set(hosts)
        new = tuple(host for host in self.monitor.hosts if host not in targets)
        try:
            self._save_inventory(new)
        except StoreError as error:
            self._notice("移除失败，请检查写入权限。", "error", str(error))
        else:
            self._notice(f"已移除 {count} 台电脑。", "success")
            if new:
                self.table.setFocus()
            else:
                self.add_button.setFocus()

    @Slot()
    def _wake_selected(self) -> None:
        hosts = self._selected()
        if not hosts or self.monitor.sending:
            return
        if len(hosts) > 1:
            examples = "、".join(host.name for host in hosts[:3])
            if len(hosts) > 3:
                examples += " 等"
            if not message(
                self,
                "批量唤醒",
                f"向勾选的 {len(hosts)} 台电脑发送唤醒包？\n{examples}",
                action="发送唤醒包",
            ):
                return
        self._notice(f"正在向 {len(hosts)} 台电脑发送唤醒包。")
        self.monitor.wake(hosts)

    @Slot(object)
    def _wake_finished(self, outcome: list[tuple[Host, str]]) -> None:
        failures = [(host, error) for host, error in outcome if error]
        successes = len(outcome) - len(failures)
        if failures:
            detail = "\n".join(f"{host.name} ({host.ip})：{error}" for host, error in failures)
            self._notice(f"已发送 {successes} 台，失败 {len(failures)} 台。", "error", detail)
        else:
            self._notice(f"唤醒包已发送：{successes} 台。", "success")

    def _notice(self, text: str, tone: str = "info", detail: str = "") -> None:
        self.feedback.setText(text)
        set_label_tone(self.feedback, tone)
        self.footer.show()
        self._details = (text, detail) if detail else None
        self.detail_button.setVisible(bool(detail))

    @Slot()
    def _show_details(self) -> None:
        if self._details:
            text, detail = self._details
            message(self, "操作详情", text, detail=detail)
