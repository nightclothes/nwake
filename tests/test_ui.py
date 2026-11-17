import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QSystemTrayIcon

from nwake.app import Tray
from nwake.dialogs import HostDialog
from nwake.hosts import Host, HostStore
from nwake.monitor import Monitor
from nwake.network import ProbeResult, Reachability
from nwake.theme import STYLESHEET, app_icon
from nwake.window import DeviceWindow

DESK = Host("书房电脑", "192.0.2.21", "02:01:02:03:04:05")
NAS = Host("家庭服务器", "192.0.2.22", "02:01:02:03:04:06")


class DeviceWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        font = QFont("Segoe UI", 10)
        font.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
        cls.app.setFont(font)
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLESHEET)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = HostStore(Path(self.directory.name) / "hosts.json")

    def launch(self, hosts=(), *, wake=None, probe=None):
        args = {key: func for key, func in (("wake", wake), ("probe", probe)) if func is not None}
        self.monitor = Monitor(hosts, **args)
        self.window = DeviceWindow(app_icon(), self.store, self.monitor)
        self.window.show()
        self.addCleanup(self.finish)
        self.app.processEvents()

    def finish(self):
        self.monitor.stop()
        self.window.exiting = True
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def wait_until(self, predicate):
        deadline = monotonic() + 3
        while not predicate() and monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "Qt state did not settle")

    def with_modal(self, action, interact):
        result = []

        def handle():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsNotNone(dialog)
                interact(dialog)
            except BaseException as error:
                result.append(error)
                if dialog is not None:
                    dialog.done(0)
            else:
                result.append(None)

        QTimer.singleShot(0, handle)
        action.click()
        self.assertEqual(len(result), 1, "the expected modal did not open")
        if result[0]:
            raise result[0]

    def click_button(self, dialog, text):
        widget = next(
            button for button in dialog.findChildren(QPushButton) if button.text() == text
        )
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)

    def accept_action(self, dialog, action):
        self.assertIsInstance(dialog, QDialog)
        default = next(button for button in dialog.findChildren(QPushButton) if button.isDefault())
        self.assertEqual(default.text(), "取消")
        self.click_button(dialog, action)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_add_validate_edit_reload_and_remove(self):
        self.launch(probe=lambda _: ProbeResult(Reachability.NO_REPLY))
        self.assertFalse(self.window.wake_button.isEnabled())
        self.assertIs(self.window.pages.currentWidget(), self.window.empty)

        def add(dialog):
            self.assertIsInstance(dialog, HostDialog)
            dialog.fields["name"].setText(DESK.name)
            dialog.fields["ip"].setText("invalid")
            dialog.fields["mac"].setText(DESK.mac)
            self.click_button(dialog, "保存电脑")
            self.assertIn("IPv4", dialog.error.text())
            self.assertIs(dialog.focusWidget(), dialog.fields["ip"])
            self.assertEqual(dialog.fields["ip"].selectedText(), "invalid")
            dialog.fields["ip"].setText(DESK.ip)
            self.click_button(dialog, "保存电脑")
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

        self.with_modal(self.window.add_button, add)
        self.assertEqual(self.store.load(), (DESK,))
        self.assertEqual(self.window.table.item(0, 2).text(), DESK.ip)
        self.assertTrue(self.window.edit_button.isEnabled())

        def edit(dialog):
            self.assertEqual(dialog.fields["name"].text(), DESK.name)
            dialog.fields["name"].setText("工作站")
            self.click_button(dialog, "保存电脑")
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

        self.with_modal(self.window.edit_button, edit)
        self.assertEqual(HostStore(self.store.path).load()[0].name, "工作站")
        self.with_modal(
            self.window.remove_button, lambda dialog: self.accept_action(dialog, "移除电脑")
        )
        self.assertEqual(self.store.load(), ())
        self.assertIs(self.window.pages.currentWidget(), self.window.empty)

    def test_batch_confirmation_partial_failure_and_no_false_online(self):
        sent = []

        def wake(host):
            sent.append(host)
            if host == NAS:
                raise OSError("simulated no route")

        self.launch((DESK, NAS), wake=wake, probe=lambda _: ProbeResult(Reachability.NO_REPLY))
        self.monitor.start()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "无响应")
        self.window.table.setCurrentCell(0, 0)
        self.window.table.setFocus()
        QTest.keyClick(self.window.table, Qt.Key.Key_Space)
        self.assertEqual(self.window.selection_summary.text(), "已勾选 1 台")
        self.assertEqual(self.window.select_all.checkState(), Qt.CheckState.PartiallyChecked)
        QTest.mouseClick(self.window.select_all, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.selection_summary.text(), "已勾选 2 台")
        self.with_modal(
            self.window.wake_button, lambda dialog: QTest.keyClick(dialog, Qt.Key.Key_Escape)
        )
        self.assertEqual(sent, [])
        self.with_modal(
            self.window.wake_button, lambda dialog: self.accept_action(dialog, "发送唤醒包")
        )
        self.wait_until(lambda: self.window.detail_button.isVisible())
        self.assertEqual(sent, [DESK, NAS])
        self.assertEqual(self.window.counter.text(), "0 / 2")
        self.assertEqual(self.window.table.item(0, 3).text(), "等待上线")
        self.assertEqual(self.window.table.item(1, 3).text(), "无响应")
        self.assertIn("失败 1 台", self.window.feedback.text())

    def test_probe_for_replaced_ip_cannot_mark_edited_host_online(self):
        release = Event()
        started = Event()

        def probe(ip):
            if ip == DESK.ip:
                started.set()
                release.wait(1.5)
                return ProbeResult(Reachability.ONLINE)
            return ProbeResult(Reachability.NO_REPLY)

        self.launch((DESK,), probe=probe)
        self.monitor.start()
        try:
            self.assertTrue(started.wait(1))
            moved = Host(DESK.name, "192.0.2.31", DESK.mac)
            self.monitor.set_hosts((moved,))
            self.assertEqual(self.window.table.item(0, 3).text(), "待检测")
        finally:
            release.set()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "无响应")
        self.assertEqual(self.window.counter.text(), "0 / 1")

    def test_single_wake_does_not_send_to_active_unchecked_host(self):
        sent = []
        replied = Event()

        def probe(ip):
            state = (
                Reachability.ONLINE if ip == DESK.ip and replied.is_set() else Reachability.NO_REPLY
            )
            return ProbeResult(state)

        self.launch((DESK, NAS), wake=sent.append, probe=probe)
        self.monitor.start()
        self.wait_until(lambda: not self.monitor.scanning)
        self.window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.window.table.setCurrentCell(1, 1)
        self.window.wake_button.click()
        self.wait_until(lambda: not self.monitor.sending and not self.monitor.scanning)
        self.assertEqual(sent, [DESK])
        self.assertEqual(self.window.table.item(0, 3).text(), "等待上线")
        replied.set()
        self.window.refresh_button.click()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "在线")
        self.assertEqual(self.window.counter.text(), "1 / 2")

    def test_real_notification_area_lifecycle(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.skipTest("Windows Explorer notification area unavailable")
        self.launch()
        tray = Tray(self.app, self.window, app_icon())
        self.assertTrue(tray.icon.isVisible())
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertTrue(tray.icon.isVisible())
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(self.window.isVisible())
        QTimer.singleShot(0, tray.menu.actions()[-1].trigger)
        self.app.exec()
        self.assertTrue(self.window.exiting)
        self.assertFalse(tray.icon.isVisible())

    def test_small_window_keeps_scrolling_and_actions(self):
        hosts = tuple(
            Host(
                f"设备 {index} · " + "长名称" * 12,
                f"192.0.2.{index}",
                f"02:00:00:00:00:{index:02x}",
            )
            for index in range(1, 13)
        )
        self.launch(hosts, probe=lambda _: ProbeResult(Reachability.ONLINE))
        self.window.resize(self.window.minimumSize())
        self.monitor.start()
        self.wait_until(lambda: not self.monitor.scanning)
        self.assertGreater(self.window.table.verticalScrollBar().maximum(), 0)
        self.assertFalse(self.window.table.horizontalScrollBar().isVisible())
        self.assertLessEqual(self.window.wake_button.geometry().right(), self.window.width())
        self.assertTrue(self.window.wake_button.isVisible())
