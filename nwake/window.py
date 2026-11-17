"""The device list opened from the Windows notification area."""

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMainWindow,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nwake.dialogs import HostDialog, button, label, message
from nwake.hosts import MAX_HOSTS, Host, HostStore, StoreError
from nwake.monitor import Monitor
from nwake.theme import STATUS

_CHECKED = Qt.CheckState.Checked
_PARTIAL = Qt.CheckState.PartiallyChecked
_UNCHECKED = Qt.CheckState.Unchecked


class _SelectAll(QCheckBox):
    def nextCheckState(self) -> None:
        self.setCheckState(_UNCHECKED if self.checkState() == _CHECKED else _CHECKED)


class DeviceWindow(QMainWindow):
    exit_requested = Signal()

    def __init__(self, icon: QIcon, store: HostStore, monitor: Monitor, load_error: str = ""):
        super().__init__()
        self.setWindowTitle("Nwake · 局域网开机")
        self.setWindowIcon(icon)
        self.setMinimumSize(470, 400)
        self.resize(550, 466)
        self.store = store
        self.monitor = monitor
        monitor.setParent(self)
        self.load_error = load_error
        self.can_hide: Callable[[], bool] = lambda: False
        self.exiting = False
        self._shown_hosts: tuple[Host, ...] = ()
        self._details: tuple[str, str] | None = None
        self._preferred_host: Host | None = None

        root = QWidget(objectName="main")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 13)
        layout.setSpacing(12)

        masthead = QFrame(objectName="masthead")
        head = QHBoxLayout(masthead)
        head.setContentsMargins(14, 9, 17, 9)
        logo = label()
        logo.setPixmap(icon.pixmap(42, 42))
        head.addWidget(logo)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(0)
        title = label("Nwake")
        title.setProperty("header", True)
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
        title_stack.addWidget(title)
        subtitle = label("局域网开机")
        subtitle.setObjectName("headerSub")
        title_stack.addWidget(subtitle)
        head.addLayout(title_stack)
        head.addStretch()
        summary = QVBoxLayout()
        summary.setSpacing(0)
        self.counter = label("0 / 0")
        self.counter.setObjectName("counter")
        self.counter.setFont(QFont("Consolas", 17, QFont.Weight.Bold))
        self.counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        summary.addWidget(self.counter)
        summary_label = label("电脑在线 / 总数")
        summary_label.setObjectName("headerSub")
        summary_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        summary.addWidget(summary_label)
        head.addLayout(summary)
        layout.addWidget(masthead)

        list_actions = QHBoxLayout()
        list_title = label("电脑列表")
        list_title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.DemiBold))
        list_actions.addWidget(list_title)
        list_actions.addStretch()
        self.refresh_button = button("刷新")
        self.refresh_button.clicked.connect(monitor.refresh)
        list_actions.addWidget(self.refresh_button)
        self.add_button = button("添加电脑")
        self.add_button.clicked.connect(lambda: self.edit_host(None))
        list_actions.addWidget(self.add_button)
        layout.addLayout(list_actions)

        self.pages = QStackedWidget()
        self.empty = QFrame(objectName="empty")
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(14, 16, 14, 16)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, muted in (
            ("电脑列表不可用" if load_error else "还没有电脑", False),
            (
                "请在详情中查看文件位置，修复后重新打开。"
                if load_error
                else "点击「添加电脑」，填入目标的 IPv4 和网卡 MAC 地址。",
                True,
            ),
        ):
            caption = label(text, muted=muted)
            caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            caption.setWordWrap(True)
            if not muted:
                caption.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.DemiBold))
            empty_layout.addWidget(caption)
        self.pages.addWidget(self.empty)

        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName("电脑列表")
        self.table.setAccessibleDescription("勾选复选框可唤醒一台或多台电脑。选中行可编辑或移除。")
        self.table.setHorizontalHeaderLabels(("", "主机名", "IPv4 地址", "状态"))
        self.table.setColumnWidth(0, 39)
        self.table.setColumnWidth(2, 135)
        self.table.setColumnWidth(3, 107)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.itemChanged.connect(self._item_changed)
        self.table.currentCellChanged.connect(self._sync_actions)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.pages.addWidget(self.table)
        layout.addWidget(self.pages, 1)

        row_actions = QHBoxLayout()
        self.select_all = _SelectAll("全选")
        self.select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all.checkStateChanged.connect(self._select_all)
        row_actions.addWidget(self.select_all)
        self.selection_summary = label("已勾选 0 台", muted=True)
        row_actions.addWidget(self.selection_summary)
        row_actions.addStretch()
        self.edit_button = button("编辑")
        self.edit_button.clicked.connect(self._edit_active)
        row_actions.addWidget(self.edit_button)
        self.remove_button = button("移除")
        self.remove_button.clicked.connect(self._remove_active)
        row_actions.addWidget(self.remove_button)
        layout.addLayout(row_actions)

        separator = QFrame(frameShape=QFrame.Shape.HLine)
        layout.addWidget(separator)

        footer = QHBoxLayout()
        info = QVBoxLayout()
        info.setSpacing(1)
        self.freshness = label("自动检测 · 每 5 秒", muted=True)
        info.addWidget(self.freshness)
        self.feedback = label("无响应不代表电脑已关机。")
        self.feedback.setObjectName("feedback")
        info.addWidget(self.feedback)
        footer.addLayout(info)
        footer.addStretch()
        self.detail_button = button("详情")
        self.detail_button.clicked.connect(self._show_details)
        detail_size = self.detail_button.sizePolicy()
        detail_size.setRetainSizeWhenHidden(True)
        self.detail_button.setSizePolicy(detail_size)
        self.detail_button.hide()
        footer.addWidget(self.detail_button)
        self.wake_button = button("唤醒所选", "primary")
        self.wake_button.setFixedWidth(102)
        self.wake_button.clicked.connect(self._wake_selected)
        footer.addWidget(self.wake_button)
        layout.addLayout(footer)

        QWidget.setTabOrder(self.refresh_button, self.add_button)
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
        index = self.table.currentRow()
        if 0 <= index < len(self._shown_hosts) and self.table.selectedItems():
            return self._shown_hosts[index]
        return None

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
                        item.setToolTip(escape(f"{host.name} · {host.mac}"))
                    elif column == 2:
                        item.setFont(QFont("Consolas", 10))
                    elif column == 3:
                        item.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
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
                text, color = STATUS[key]
                status = self.table.item(index, 3)
                if status.text() != text:
                    status.setText(text)
                    status.setForeground(QBrush(QColor(color)))
                status.setToolTip(escape(detail))
                online += key == "online"
        self.counter.setText(f"{online} / {len(self._shown_hosts)}")
        self.counter.setAccessibleName(f"{online} 台在线，共 {len(self._shown_hosts)} 台电脑")
        last_scan = self.monitor.last_scan
        if self._shown_hosts and self.monitor.scanning:
            self.freshness.setText("正在检测电脑状态…")
        elif self._shown_hosts and last_scan is not None:
            self.freshness.setText(f"最近检测 {last_scan:%H:%M:%S} · 自动刷新")
        else:
            self.freshness.setText("自动检测 · 每 5 秒")
        self._sync_actions()

    @Slot()
    def _sync_actions(self) -> None:
        total = len(self._shown_hosts)
        count = len(self._selected())
        with QSignalBlocker(self.select_all):
            self.select_all.setCheckState(
                _UNCHECKED if not count else _CHECKED if count == total else _PARTIAL
            )
        self.select_all.setEnabled(bool(total))
        self.selection_summary.setText(f"已勾选 {count} 台")
        editable = not self.load_error and not self.monitor.sending
        self.add_button.setEnabled(editable and total < MAX_HOSTS)
        self.add_button.setToolTip("最多管理 64 台电脑。" if total == MAX_HOSTS else "")
        self.edit_button.setEnabled(editable and self._active() is not None)
        self.remove_button.setEnabled(self.edit_button.isEnabled())
        self.refresh_button.setEnabled(bool(total) and not self.monitor.scanning)
        self.wake_button.setEnabled(bool(count) and not self.monitor.sending)
        self.wake_button.setText("正在发送…" if self.monitor.sending else "唤醒所选")

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

    def edit_host(self, original: Host | None) -> None:
        def save(host: Host) -> None:
            hosts = self.monitor.hosts
            new = (
                tuple(host if existing == original else existing for existing in hosts)
                if original
                else (*hosts, host)
            )
            self.store.save(new)
            self._preferred_host = host
            self.monitor.set_hosts(new)
            self._notice("已保存电脑。", "success")

        dialog = HostDialog(self, save, original)
        if dialog.exec():
            self.table.setFocus()
        dialog.deleteLater()

    @Slot()
    def _remove_active(self) -> None:
        host = self._active()
        if not host or not message(
            self,
            "移除电脑",
            f"从列表移除「{host.name}」？这不会改变该电脑的电源状态。",
            action="移除电脑",
            danger=True,
        ):
            return
        new = tuple(existing for existing in self.monitor.hosts if existing != host)
        try:
            self.store.save(new)
        except StoreError as error:
            self._notice("移除失败，请检查写入权限。", "error", str(error))
        else:
            self.monitor.set_hosts(new)
            self._notice("已移除电脑。", "success")
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
    def _wake_finished(self, outcome: list[tuple[Host, str, float]]) -> None:
        failures = [(host, error) for host, error, _ in outcome if error]
        successes = len(outcome) - len(failures)
        if failures:
            detail = "\n".join(f"{host.name} ({host.ip})：{error}" for host, error in failures)
            self._notice(f"已发送 {successes} 台，失败 {len(failures)} 台。", "error", detail)
        else:
            self._notice(f"唤醒包已发送：{successes} 台。", "success")

    def _notice(self, text: str, tone: str = "info", detail: str = "") -> None:
        self.feedback.setText(text)
        self.feedback.setProperty("tone", tone)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)
        self._details = (text, detail) if detail else None
        self.detail_button.setVisible(bool(detail))

    @Slot()
    def _show_details(self) -> None:
        if self._details:
            text, detail = self._details
            message(self, "操作详情", text, detail=detail)
