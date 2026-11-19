"""Windows app entry point and notification-area lifecycle."""

import sys

from PySide6.QtCore import QEvent, QLockFile, QObject, QPoint, QTimer, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from nwake import __version__
from nwake.dialogs import message
from nwake.hosts import HostStore, StoreError, data_directory
from nwake.monitor import Monitor
from nwake.theme import STYLESHEET, NwakeStyle, app_icon, ui_font
from nwake.window import DeviceWindow


class Tray(QObject):
    def __init__(self, app: QApplication, window: DeviceWindow, icon: QIcon):
        super().__init__(window)
        self._quitting = False
        self.icon = QSystemTrayIcon(icon, self)
        self.menu = QMenu(window)
        open_action = self.menu.addAction("打开电脑列表")
        open_action.triggered.connect(self.open_window)
        self.menu.setDefaultAction(open_action)
        self.menu.addSeparator()
        self.menu.addAction("退出 Nwake", self.quit)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.icon.show()
        window.can_hide = QSystemTrayIcon.isSystemTrayAvailable
        window.exit_requested.connect(self.quit)
        window.monitor.changed.connect(self._sync_tooltip)
        app.aboutToQuit.connect(self.shutdown)
        self._sync_tooltip()

    @property
    def window(self) -> DeviceWindow:
        return self.parent()

    @Slot()
    def _sync_tooltip(self) -> None:
        monitor = self.window.monitor
        if self.window.load_error:
            summary = "电脑列表不可用"
        elif not monitor.hosts:
            summary = "尚未添加电脑"
        else:
            online = sum(monitor.readout(host)[0] == "online" for host in monitor.hosts)
            summary = f"{online} / {len(monitor.hosts)} 台在线"
        self.icon.setToolTip(f"Nwake · {summary}")

    @Slot(QSystemTrayIcon.ActivationReason)
    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_window()

    @Slot()
    def open_window(self) -> None:
        modal = QApplication.activeModalWidget()
        if modal is not None:
            modal.raise_()
            modal.activateWindow()
            return
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    @Slot()
    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._continue_quit()

    def _continue_quit(self) -> None:
        modal = QApplication.activeModalWidget()
        if modal is not None:
            self.open_window()
            if modal.close():
                # Let the closed dialog's event loop unwind before closing its parent.
                QTimer.singleShot(0, self, self._continue_quit)
            else:
                self._quitting = False
            return
        self.window.exiting = True
        QApplication.quit()

    @Slot()
    def shutdown(self) -> None:
        self.icon.hide()
        self.window.monitor.stop()
        self.window.scanner.stop()


def main() -> int:
    if sys.platform != "win32":
        print("Nwake 仅支持 Windows。", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("Nwake")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(ui_font())
    app.setStyle(NwakeStyle())
    app.setStyleSheet(STYLESHEET)
    icon = app_icon()
    app.setWindowIcon(icon)

    directory = data_directory()
    lock = QLockFile(str(directory / "nwake.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if lock.error() == QLockFile.LockError.LockFailedError:
            message(None, "Nwake 已在运行", "请从 Windows 通知区域的 Nwake 图标打开电脑列表。")
        else:
            message(
                None,
                "无法启动 Nwake",
                "无法锁定配置文件所在目录。请把程序放在可写目录。",
                detail=str(directory),
            )
        return 1

    window = None
    try:
        store = HostStore(directory / "hosts.json")
        load_error = ""
        try:
            hosts = store.load()
        except StoreError as error:
            hosts = ()
            load_error = str(error)
        monitor = Monitor(hosts)
        window = DeviceWindow(icon, store, monitor, load_error)
        tray = Tray(app, window, icon)
        tray_screen = app.screenAt(tray.icon.geometry().center()) or app.primaryScreen()
        work_area = tray_screen.availableGeometry()
        window.move(
            QPoint(
                work_area.right() - window.width() - 18, work_area.bottom() - window.height() - 35
            )
        )
        tray.open_window()
        return app.exec()
    finally:
        if window is not None:
            # Dispose of native widgets while QApplication and the tray still exist.
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        lock.unlock()
