"""Shared form and confirmation dialogs for the tray window."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nwake.hosts import Host, HostError, StoreError


def label(text: str = "", *, muted: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if muted:
        widget.setProperty("muted", True)
    return widget


def button(text: str, variant: str = "neutral") -> QPushButton:
    widget = QPushButton(text)
    widget.setProperty("variant", variant)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def message(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    detail: str = "",
    action: str = "",
    danger: bool = False,
) -> bool:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(390)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 14)
    layout.setSpacing(12)
    explanation = label(text)
    explanation.setWordWrap(True)
    explanation.setMaximumWidth(430)
    layout.addWidget(explanation)
    if detail:
        details = QPlainTextEdit(detail, readOnly=True)
        details.setAccessibleName("操作详情")
        details.setMaximumHeight(135)
        layout.addWidget(details)
    actions = QHBoxLayout()
    actions.addStretch()
    cancel = button("取消" if action else "关闭")
    cancel.clicked.connect(dialog.reject)
    actions.addWidget(cancel)
    cancel.setDefault(True)
    cancel.setFocus()
    if action:
        submit = button(action, "danger" if danger else "primary")
        submit.clicked.connect(dialog.accept)
        actions.addWidget(submit)
    layout.addLayout(actions)
    return dialog.exec() == QDialog.DialogCode.Accepted


class HostDialog(QDialog):
    _fields = (
        ("name", "主机名", "例如：书房电脑", "可填系统计算机名或便于辨认的名称。"),
        ("ip", "IPv4 地址", "192.168.1.20", "用于检测电脑是否在线，建议在路由器上保留该地址。"),
        ("mac", "网卡 MAC", "02:12:34:56:78:9A", "请填写启用了 Wake-on-LAN 的网卡 MAC 地址。"),
        (
            "prefix",
            "子网前缀（可选）",
            "留空使用默认广播",
            "例如填写 24，使用 IPv4 所在子网的广播地址。",
        ),
    )

    def __init__(self, parent: QWidget, save: Callable[[Host], None], original: Host | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑电脑" if original else "添加电脑")
        self.setMinimumWidth(410)
        self._save = save
        self._original: dict[str, str] = {}
        self.fields: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        for key, title, example, hint in self._fields:
            field = QLineEdit()
            field.setObjectName(key)
            field.setMaxLength(128)
            field.setPlaceholderText(example)
            field.setAccessibleDescription(hint)
            field.setToolTip(hint)
            current = getattr(original, key) if original else None
            start = str(current) if current is not None else ""
            self._original[key] = start
            field.setText(start)
            self.fields[key] = field
            caption = label(title)
            caption.setBuddy(field)
            form.addRow(caption, field)
        layout.addLayout(form)

        self.error = label()
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)
        self.error.setMinimumHeight(self.error.fontMetrics().lineSpacing() * 2)
        layout.addWidget(self.error)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("取消")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        submit = button("保存电脑", "primary")
        submit.setDefault(True)
        submit.clicked.connect(self._submit)
        actions.addWidget(submit)
        layout.addLayout(actions)
        self.fields["name"].setFocus()

    @Slot()
    def _submit(self) -> None:
        for field in self.fields.values():
            if field.property("invalid"):
                self._set_invalid(field, False)
        values = {key: field.text().strip() for key, field in self.fields.items()}
        try:
            raw_prefix = values["prefix"]
            if raw_prefix and (not raw_prefix.isascii() or not raw_prefix.isdecimal()):
                raise HostError("prefix", "请输入 1–30 的子网前缀长度，例如 24。")
            host = Host(
                values["name"], values["ip"], values["mac"], int(raw_prefix) if raw_prefix else None
            )
            self._save(host)
        except HostError as error:
            self.error.setText(str(error))
            field = self.fields[error.field]
            self._set_invalid(field, True)
            field.setAccessibleDescription(str(error))
            field.setFocus()
            field.selectAll()
        except StoreError as error:
            self.error.setText("保存失败。请检查数据目录的写入权限后重试。")
            self.error.setToolTip(str(error))
        else:
            self.accept()

    @staticmethod
    def _set_invalid(field: QLineEdit, invalid: bool) -> None:
        field.setProperty("invalid", invalid)
        field.style().unpolish(field)
        field.style().polish(field)
        if not invalid:
            field.setAccessibleDescription(field.toolTip())

    @Slot()
    def reject(self) -> None:
        if any(field.text() != self._original[key] for key, field in self.fields.items()):
            if not message(self, "放弃修改", "还有未保存的修改。", action="放弃修改"):
                return
        super().reject()
