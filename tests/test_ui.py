import unittest
from dataclasses import replace
from ipaddress import IPv4Interface
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtNetwork import QHostInfo
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton, QSystemTrayIcon

from nwake.app import Tray
from nwake.dialogs import HostDialog
from nwake.discovery import LanNetwork
from nwake.discovery_dialog import DiscoveryDialog
from nwake.hosts import Host, HostStore, StoreError
from nwake.monitor import Monitor
from nwake.network import ProbeResult, Reachability
from nwake.theme import STYLESHEET, NwakeStyle, app_icon, ui_font
from nwake.window import DeviceWindow

DESK = Host("书房电脑", "192.0.2.21", "02:01:02:03:04:05")
NAS = Host("家庭服务器", "192.0.2.22", "02:01:02:03:04:06")


class DeviceWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.app.setFont(ui_font())
        cls.app.setStyle(NwakeStyle())
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
        self.window.scanner.stop()
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

    def test_checkbox_cell_and_row_actions_follow_the_two_selections(self):
        self.launch((DESK, NAS))
        grid = self.window.table
        grid.setCurrentCell(0, 1)
        self.assertTrue(self.window.edit_button.isEnabled())
        grid.clearSelection()
        self.assertFalse(self.window.edit_button.isEnabled())
        self.assertFalse(self.window.remove_button.isEnabled())

        check = grid.item(1, 0)
        bounds = grid.visualItemRect(check)
        edge = QPoint(bounds.right() - 2, bounds.center().y())
        QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=edge)
        self.assertEqual(check.checkState(), Qt.CheckState.Checked)
        self.assertEqual(self.window.selection_summary.text(), "已勾选 1 台")
        self.assertTrue(self.window.wake_button.isEnabled())
        indicator = QPoint(bounds.left() + 16, bounds.center().y())
        QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=indicator)
        self.assertEqual(check.checkState(), Qt.CheckState.Unchecked)

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

    def test_select_all_removal_requires_confirmation_and_saves_once(self):
        self.store.save((DESK, NAS))
        self.launch((DESK, NAS))
        self.window.table.clearSelection()
        QTest.mouseClick(self.window.select_all, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.selection_summary.text(), "已勾选 2 台")
        self.assertFalse(self.window.edit_button.isEnabled())
        self.assertTrue(self.window.remove_button.isEnabled())
        self.assertEqual(self.window.remove_button.text(), "移除所选")

        def cancel(dialog):
            self.assertEqual(dialog.windowTitle(), "批量移除电脑")
            self.assertEqual(
                dialog.findChild(QPlainTextEdit).toPlainText(),
                f"{DESK.name} · {DESK.ip}\n{NAS.name} · {NAS.ip}",
            )
            QTest.keyClick(dialog, Qt.Key.Key_Return)
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

        with patch.object(self.store, "save", wraps=self.store.save) as save:
            self.with_modal(self.window.remove_button, cancel)
            save.assert_not_called()
            self.assertEqual(self.store.load(), (DESK, NAS))
            self.assertEqual(self.window.select_all.checkState(), Qt.CheckState.Checked)
            self.with_modal(
                self.window.remove_button, lambda dialog: self.accept_action(dialog, "移除 2 台")
            )
            save.assert_called_once_with(())

        self.assertEqual(self.store.load(), ())
        self.assertIs(self.window.pages.currentWidget(), self.window.empty)
        self.assertIn("已移除 2 台", self.window.feedback.text())

    def test_batch_removal_preserves_unchecked_host_and_recovers_from_save_error(self):
        spare = Host("备用电脑", "192.0.2.23", "02:01:02:03:04:07")
        hosts = (DESK, NAS, spare)
        self.store.save(hosts)
        self.launch(hosts)
        self.window.table.setCurrentCell(2, 1)
        for row in (0, 1):
            self.window.table.item(row, 0).setCheckState(Qt.CheckState.Checked)

        def confirm(dialog):
            self.accept_action(dialog, "移除 2 台")

        with patch.object(self.store, "save", side_effect=StoreError("simulated write failure")):
            self.with_modal(self.window.remove_button, confirm)
        self.assertEqual(self.store.load(), hosts)
        self.assertEqual(self.window.table.rowCount(), 3)
        self.assertEqual(self.window.selection_summary.text(), "已勾选 2 台")
        self.assertIn("移除失败", self.window.feedback.text())

        self.with_modal(self.window.remove_button, confirm)
        self.assertEqual(self.store.load(), (spare,))
        self.assertEqual(self.window.table.item(0, 2).text(), spare.ip)

    def test_opening_and_removing_hosts_keeps_refresh_manual(self):
        probed = []

        def probe(ip):
            probed.append(ip)
            return ProbeResult(Reachability.ONLINE)

        self.store.save((DESK, NAS))
        self.launch((DESK, NAS), probe=probe)
        with patch("nwake.app.QSystemTrayIcon"):
            tray = Tray(self.app, self.window, app_icon())
            self.window.hide()
            tray.open_window()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.monitor.scanning)
        self.assertEqual(probed, [])
        self.assertEqual(self.window.table.item(0, 3).text(), "待检测")

        self.window.refresh_button.click()
        self.wait_until(lambda: not self.monitor.scanning)
        self.assertEqual(self.window.counter.text(), "2 / 2")

        for remaining in ((NAS,), ()):
            self.window.table.setCurrentCell(0, 1)
            self.with_modal(
                self.window.remove_button, lambda dialog: self.accept_action(dialog, "移除电脑")
            )
            self.assertEqual(self.store.load(), remaining)
            self.assertFalse(self.monitor.scanning)

        self.assertCountEqual(probed, [DESK.ip, NAS.ip])

    def test_scan_add_selected_hosts_atomically_and_preserve_selection_on_error(self):
        self.store.save((DESK,))
        self.launch((DESK,), probe=lambda _: ProbeResult(Reachability.ONLINE))
        subnet = LanNetwork("测试网段", IPv4Interface("192.0.2.17/29"))
        found = (
            Host("lab-pc", "192.0.2.18", "02:12:00:00:00:18", 29),
            Host("OFFICE-PC", "192.0.2.19", "02:12:00:00:00:19", 29),
            Host("192.0.2.20", "192.0.2.20", "02:12:00:00:00:20", 29),
        )
        replies = {host.ip: host.mac for host in found} | {NAS.ip: DESK.mac}
        requests = []
        netbios_requests = []
        release = Event()

        def arp(ip, source):
            requests.append((ip, source))
            return replies.get(ip)

        ids = count(10_000)

        def lookup(ip, receiver, _slot):
            lookup_id = next(ids)
            info = QHostInfo(lookup_id)
            if ip == found[0].ip:
                info.setHostName("lab-pc.")
            elif ip == found[1].ip:
                info.setError(QHostInfo.HostInfoError.HostNotFound)
            else:
                info.setHostName(ip)
            QTimer.singleShot(0, lambda: receiver._record_name(info))
            return lookup_id

        def netbios(ip, source):
            netbios_requests.append((ip, source))
            if ip == found[1].ip and release.wait(4):
                return found[1].name
            raise TimeoutError

        self.window.scanner._arp = arp
        self.window.scanner._lookup = lookup
        self.window.scanner._netbios = netbios

        def import_results(dialog):
            self.assertIsInstance(dialog, DiscoveryDialog)
            grid = dialog.results
            try:
                self.wait_until(lambda: "正在查询主机名" in dialog.status.text())
                self.assertEqual(dialog.scan_button.text(), "停止")
                rows = {grid.item(row, 2).text(): row for row in range(grid.rowCount())}
                grid.item(rows[found[1].ip], 0).setCheckState(Qt.CheckState.Checked)
                self.assertFalse(dialog.add_button.isEnabled())
                self.assertIn("等待主机名", dialog.selection.text())
            finally:
                release.set()
            self.wait_until(lambda: not self.window.scanner.scanning)
            self.assertTrue(dialog.add_button.isEnabled())
            self.assertEqual(set(rows), {host.ip for host in found})
            self.assertNotIn((DESK.ip, "192.0.2.17"), requests)
            self.assertTrue(all(source == "192.0.2.17" for _, source in requests))
            self.assertCountEqual(netbios_requests, [(host.ip, "192.0.2.17") for host in found[1:]])
            self.assertEqual(grid.item(rows[found[0].ip], 1).text(), "lab-pc")
            self.assertEqual(grid.item(rows[found[1].ip], 1).text(), "OFFICE-PC")
            self.assertEqual(grid.item(rows[found[2].ip], 1).text(), "未识别")
            self.assertEqual(dialog.name_summary.text(), "已识别主机名 2 / 3")
            self.assertEqual(self.store.load(), (DESK,))

            first = rows[found[0].ip]
            grid.setCurrentCell(first, 1)
            QTest.keyClick(grid, Qt.Key.Key_Space)
            self.assertTrue(dialog.add_button.isEnabled())
            self.assertEqual(dialog.selection.text(), "已勾选 2 台")
            with patch.object(
                self.store, "save", side_effect=StoreError("simulated write failure")
            ):
                self.click_button(dialog, "添加所选")
            self.assertEqual(self.store.load(), (DESK,))
            self.assertEqual(dialog.selection.text(), "已勾选 2 台")
            self.assertIn("保存失败", dialog.status.text())
            self.click_button(dialog, "添加所选")
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

        with patch("nwake.discovery_dialog.local_networks", return_value=(subnet,)):
            self.with_modal(self.window.scan_button, import_results)
        self.assertEqual(set(self.store.load()), {DESK, *found[:2]})
        self.assertEqual(self.window.table.rowCount(), 3)

    def test_rescan_preserves_checked_devices_with_the_same_ip_and_mac(self):
        self.launch()
        network = LanNetwork("测试网段", IPv4Interface("192.0.2.17/29"))
        updated = replace(network, own_ips=frozenset({network.source.ip}))
        other = LanNetwork("另一个网段", IPv4Interface("192.0.2.5/30"))
        first, second = "192.0.2.18", "192.0.2.19"
        replies = {first: "02:12:00:00:00:18", second: "02:12:00:00:00:19"}
        scanner = self.window.scanner
        scanner._arp = lambda ip, _: replies.get(ip)
        scanner._lookup = lambda *_: -1
        scanner._netbios = lambda *_: None

        def rescan(dialog):
            self.wait_until(lambda: not scanner.scanning)
            dialog.select_all.click()
            self.assertEqual(dialog.selection.text(), "已勾选 2 台")
            replies[second] = "02:12:00:00:00:20"
            dialog.scan_button.click()
            self.wait_until(lambda: not scanner.scanning)
            grid = dialog.results
            self.assertEqual(grid.rowCount(), 2)
            checked = {
                grid.item(row, 2).text()
                for row in range(grid.rowCount())
                if grid.item(row, 0).checkState() == Qt.CheckState.Checked
            }
            self.assertEqual(checked, {first})
            dialog.reject()

        with patch(
            "nwake.discovery_dialog.local_networks", side_effect=((network,), (other, updated))
        ):
            self.with_modal(self.window.scan_button, rescan)

    def test_switching_discovery_network_discards_in_flight_results(self):
        self.launch()
        first = LanNetwork("旧网段", IPv4Interface("192.0.2.5/30"))
        second = LanNetwork("新网段", IPv4Interface("192.0.2.9/30"))
        started = Event()
        release = Event()

        def arp(ip, _source):
            if ip == "192.0.2.6":
                started.set()
                release.wait(1.5)
                return "02:12:00:00:00:06"
            return "02:12:00:00:00:10"

        self.window.scanner._arp = arp
        self.window.scanner._lookup = lambda *_: -1
        self.window.scanner._netbios = lambda *_: None

        def switch(dialog):
            try:
                self.assertTrue(started.wait(1))
                dialog.network.setCurrentIndex(1)
                self.wait_until(lambda: not self.window.scanner.scanning)
            finally:
                release.set()
            self.wait_until(lambda: not self.window.scanner._pool.activeThreadCount())
            self.app.processEvents()
            self.assertEqual(dialog.results.rowCount(), 1)
            self.assertEqual(dialog.results.item(0, 2).text(), "192.0.2.10")
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

        with patch("nwake.discovery_dialog.local_networks", return_value=(first, second)):
            self.with_modal(self.window.scan_button, switch)
        self.assertEqual(self.store.load(), ())

    def test_stopping_discovery_discards_in_flight_names(self):
        self.launch()
        network = LanNetwork("测试网段", IPv4Interface("192.0.2.17/29"))
        timed_out, pending = "192.0.2.18", "192.0.2.19"
        replies = {timed_out: "02:12:00:00:00:18", pending: "02:12:00:00:00:19"}
        started = Event()
        release = Event()

        def netbios(ip, _source):
            if ip == timed_out:
                raise TimeoutError
            started.set()
            release.wait(7)
            return "OLD-PC"

        scanner = self.window.scanner
        scanner._arp = lambda ip, _: replies.get(ip)
        scanner._lookup = lambda *_: -1
        scanner._netbios = netbios

        def stop(dialog):
            try:
                grid = dialog.results
                self.wait_until(lambda: started.is_set() and grid.rowCount() == 2)
                names = {grid.item(row, 2).text(): grid.item(row, 1) for row in range(2)}
                self.wait_until(lambda: names[timed_out].text() == "未识别")
                self.assertTrue(scanner.scanning)
                self.assertEqual(names[pending].text(), "查询中")
                grid.item(names[pending].row(), 0).setCheckState(Qt.CheckState.Checked)
                self.assertFalse(dialog.add_button.isEnabled())
                dialog.scan_button.click()
                self.assertFalse(scanner.scanning)
                self.assertIn("已停止", dialog.status.text())
                self.assertEqual(names[timed_out].text(), "未识别")
                self.assertEqual(names[pending].toolTip(), "主机名查询已停止。")
                self.assertTrue(dialog.add_button.isEnabled())
            finally:
                release.set()
            self.wait_until(lambda: not scanner._netbios_pool.activeThreadCount())
            self.app.processEvents()
            self.assertEqual(names[pending].text(), "—")
            dialog.add_button.click()

        with patch("nwake.discovery_dialog.local_networks", return_value=(network,)):
            self.with_modal(self.window.scan_button, stop)
        self.assertEqual(self.store.load(), (Host(pending, pending, replies[pending], 29),))

    def test_batch_confirmation_partial_failure_and_no_false_online(self):
        sent = []

        def wake(host):
            sent.append(host)
            if host == NAS:
                raise OSError("simulated no route")

        self.launch((DESK, NAS), wake=wake, probe=lambda _: ProbeResult(Reachability.NO_REPLY))
        self.window.refresh_button.click()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "无响应")
        self.window.table.setCurrentCell(0, 1)
        self.window.table.setFocus()
        QTest.keyClick(self.window.table, Qt.Key.Key_Space)
        self.assertEqual(self.window.selection_summary.text(), "已勾选 1 台")
        QTest.keyClick(self.window.table, Qt.Key.Key_Tab)
        self.assertIs(self.window.focusWidget(), self.window.select_all)
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
        probed = []

        def probe(ip):
            probed.append(ip)
            if ip == DESK.ip:
                started.set()
                release.wait(1.5)
                return ProbeResult(Reachability.ONLINE)
            return ProbeResult(Reachability.NO_REPLY)

        self.launch((DESK,), probe=probe)
        self.window.refresh_button.click()
        try:
            self.assertTrue(started.wait(1))
            moved = Host(DESK.name, "192.0.2.31", DESK.mac)
            self.monitor.set_hosts((moved,))
            self.assertEqual(self.window.table.item(0, 3).text(), "待检测")
        finally:
            release.set()
        self.wait_until(lambda: not self.monitor.scanning)
        self.assertEqual(probed, [DESK.ip])
        self.assertEqual(self.window.table.item(0, 3).text(), "待检测")
        self.window.refresh_button.click()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "无响应")
        self.assertEqual(self.window.counter.text(), "0 / 1")

    def test_single_wake_does_not_send_to_active_unchecked_host(self):
        sent = []
        probed = []
        replied = Event()

        def probe(ip):
            probed.append(ip)
            state = (
                Reachability.ONLINE if ip == DESK.ip and replied.is_set() else Reachability.NO_REPLY
            )
            return ProbeResult(state)

        self.launch((DESK, NAS), wake=sent.append, probe=probe)
        self.window.refresh_button.click()
        self.wait_until(lambda: not self.monitor.scanning)
        self.window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.window.table.setCurrentCell(1, 1)
        self.window.wake_button.click()
        self.wait_until(lambda: not self.monitor.sending and not self.monitor.scanning)
        self.assertEqual(sent, [DESK])
        self.assertCountEqual(probed, [DESK.ip, NAS.ip])
        self.assertEqual(self.window.table.item(0, 3).text(), "等待上线")
        replied.set()
        self.window.refresh_button.click()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "在线")
        self.assertEqual(self.window.counter.text(), "1 / 2")

    def test_wake_requires_a_refresh_started_after_sending(self):
        started = Event()
        release = Event()

        def probe(_ip):
            started.set()
            release.wait(4)
            return ProbeResult(Reachability.ONLINE)

        self.launch((DESK,), wake=lambda _: None, probe=probe)
        self.window.refresh_button.click()
        try:
            self.wait_until(started.is_set)
            self.window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
            self.window.wake_button.click()
            self.wait_until(lambda: not self.monitor.sending)
            self.assertEqual(self.window.table.item(0, 3).text(), "等待上线")
        finally:
            release.set()

        self.wait_until(lambda: not self.monitor.scanning)
        self.assertEqual(self.window.table.item(0, 3).text(), "等待上线")
        self.window.refresh_button.click()
        self.wait_until(lambda: self.window.table.item(0, 3).text() == "在线")

    def test_tray_quit_closes_a_scan_dialog(self):
        self.launch()
        with (
            patch("nwake.app.QSystemTrayIcon"),
            patch.object(QApplication, "quit") as quit_app,
            patch("nwake.discovery_dialog.local_networks", return_value=()),
        ):
            tray = Tray(self.app, self.window, app_icon())
            self.with_modal(self.window.scan_button, lambda _: tray.quit())
            self.wait_until(lambda: quit_app.called)
            self.assertTrue(self.window.exiting)

    def test_tray_quit_respects_unsaved_edits(self):
        self.launch()
        with (
            patch("nwake.app.QSystemTrayIcon"),
            patch.object(QApplication, "quit") as quit_app,
            patch("nwake.dialogs.message", side_effect=(False, True)) as discard,
        ):
            tray = Tray(self.app, self.window, app_icon())

            def quit_from_editor(dialog):
                dialog.fields["name"].setText("尚未保存")
                tray.quit()
                self.assertTrue(dialog.isVisible())
                self.assertFalse(quit_app.called)
                tray.quit()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

            self.with_modal(self.window.add_button, quit_from_editor)
            self.wait_until(lambda: quit_app.called)
            self.assertEqual(discard.call_count, 2)

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
        self.window.refresh_button.click()
        self.wait_until(lambda: not self.monitor.scanning)
        self.assertGreater(self.window.table.verticalScrollBar().maximum(), 0)
        self.assertFalse(self.window.table.horizontalScrollBar().isVisible())
        self.assertLessEqual(self.window.wake_button.geometry().right(), self.window.width())
        self.assertTrue(self.window.wake_button.isVisible())
