import ctypes
import json
import socket
import sys
import unittest
from ctypes import wintypes
from ipaddress import IPv4Address, IPv4Interface
from pathlib import Path
from struct import pack
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from nwake.discovery import LanNetwork
from nwake.hosts import Host, HostError, HostStore, StoreError, data_directory
from nwake.network import Reachability, _interpret_echo, probe_ipv4, resolve_mac, send_wake


class InventoryTest(unittest.TestCase):
    def test_discovery_bounds_broad_subnets_and_excludes_local_and_saved_ipv4(self):
        network = LanNetwork(
            "LAN", IPv4Interface("10.2.67.10/16"), frozenset({IPv4Address("10.2.67.11")})
        )
        saved = Host("工作站", "10.2.67.12", "02123456789a")
        targets = network.targets((saved,))
        self.assertEqual(str(network.scope), "10.2.67.0/24")
        self.assertEqual(len(targets), 253)
        self.assertEqual((targets[0], targets[-1]), ("10.2.67.0", "10.2.67.255"))
        self.assertFalse({"10.2.67.10", "10.2.67.11", saved.ip}.intersection(targets))
        small = LanNetwork("LAN", IPv4Interface("192.0.2.5/30"))
        self.assertEqual(small.targets(()), ("192.0.2.6",))

    def test_packaged_host_inventory_is_saved_beside_the_executable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            executable_dir = root / "portable"
            executable_dir.mkdir()
            host = Host("工作站", "192.168.1.20", "02:12:34:56:78:9A")
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(executable_dir / "Nwake.exe")),
                patch.object(sys, "_MEIPASS", str(root / "unpacked"), create=True),
                patch.dict("os.environ", {"LOCALAPPDATA": str(root / "appdata")}),
            ):
                store = HostStore(data_directory() / "hosts.json")
                self.assertEqual(store.load(), ())
                store.save((host,))
            self.assertEqual(HostStore(executable_dir / "hosts.json").load(), (host,))

    def test_normalization_and_directed_broadcast(self):
        host = Host("  工作站 ", " 192.168.1.20 ", "02-12-34-56-78-9a", 25)
        self.assertEqual(
            (host.name, host.ip, host.mac), ("工作站", "192.168.1.20", "02:12:34:56:78:9A")
        )
        self.assertEqual(host.broadcast, "192.168.1.127")

    def test_rejects_non_host_addresses(self):
        for data, field in (
            (("工作站", "127.0.0.1", "02123456789a"), "ip"),
            (("工作站", "192.168.1.20", "ff:ff:ff:ff:ff:ff"), "mac"),
            (("工作站", "192.168.1.20", "00:00:00:00:00:00"), "mac"),
            (("工作站", "192.168.1.20", "02:12-34:56:78:9a"), "mac"),
            (("工作站", "192.168.1.127", "02123456789a", 25), "prefix"),
            (("工作站", "192.168.1.20", "02123456789a", True), "prefix"),
        ):
            with self.subTest(data=data), self.assertRaises(HostError) as context:
                Host(*data)
            self.assertEqual(context.exception.field, field)

    def test_failed_save_and_bad_config_preserve_data(self):
        saved = Host("家庭服务器", "192.168.1.20", "02123456789a")
        other = Host("备份电脑", "192.168.1.22", "02123456789b")
        duplicate = Host("重复", saved.ip, other.mac)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "hosts.json"
            store = HostStore(path)
            self.assertEqual(store.load(), ())
            store.save((saved,))
            with self.assertRaises(HostError):
                store.save((saved, duplicate))
            with patch.object(Path, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(StoreError):
                    store.save((other,))
            self.assertEqual(store.load(), (saved,))
            self.assertEqual(list(path.parent.iterdir()), [path])
            bad = json.dumps({"version": 42, "hosts": []})
            path.write_text(bad, encoding="utf-8")
            with self.assertRaises(StoreError):
                store.load()
            self.assertEqual(path.read_text(encoding="utf-8"), bad)


class NetworkTest(unittest.TestCase):
    def test_arp_uses_the_selected_source_and_returns_exact_mac(self):
        def send_arp(destination, source, buffer, size_pointer):
            self.assertEqual(destination.to_bytes(4, sys.byteorder).hex(), "c0000206")
            self.assertEqual(source.to_bytes(4, sys.byteorder).hex(), "c0000205")
            size = ctypes.cast(size_pointer, ctypes.POINTER(wintypes.ULONG)).contents
            self.assertGreaterEqual(size.value, 6)
            ctypes.memmove(buffer, bytes.fromhex("02123456789a"), 6)
            size.value = 6
            return 0

        with patch("nwake.network._arp_api", return_value=SimpleNamespace(SendARP=send_arp)):
            self.assertEqual(resolve_mac("192.0.2.6", "192.0.2.5"), "02:12:34:56:78:9A")
        with patch("nwake.network._arp_api", return_value=SimpleNamespace(SendARP=lambda *_: 67)):
            self.assertIsNone(resolve_mac("192.0.2.6", "192.0.2.5"))

    def test_wake_wire_format_and_target(self):
        for prefix, broadcast in ((None, "255.255.255.255"), (25, "192.168.1.127")):
            with self.subTest(prefix=prefix), patch("nwake.network.socket.socket") as factory:
                sock = factory.return_value.__enter__.return_value
                sock.sendto.return_value = 102
                send_wake(Host("电脑", "192.168.1.20", "02:12:34:56:78:9a", prefix))
                packet, target = sock.sendto.call_args.args
                self.assertEqual(target, (broadcast, 9))
                self.assertEqual(len(packet), 102)
                self.assertEqual(packet[:6].hex(), "ffffffffffff")
                self.assertEqual(
                    {packet[offset : offset + 6].hex() for offset in range(6, 102, 6)},
                    {"02123456789a"},
                )
                sock.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def test_reply_from_router_is_not_evidence_of_online_host(self):
        self.assertIs(_interpret_echo(1, pack("=II", 1, 11003), 2, 0).state, Reachability.NO_REPLY)
        self.assertIs(_interpret_echo(1, pack("=II", 1, 0), 2, 0).state, Reachability.NO_REPLY)
        self.assertIs(_interpret_echo(0, b"", 2, 11010).state, Reachability.NO_REPLY)
        self.assertIs(_interpret_echo(0, b"", 2, 5).state, Reachability.ERROR)

    @unittest.skipUnless(sys.platform == "win32", "Windows IP Helper API")
    def test_real_windows_ping_loopback(self):
        result = probe_ipv4("127.0.0.1")
        self.assertIs(result.state, Reachability.ONLINE, result.detail)
