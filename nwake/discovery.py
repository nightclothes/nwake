"""Discover IPv4 neighbors on one local network, with cancellable background work."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from ipaddress import IPv4Address, IPv4Interface, IPv4Network

from PySide6.QtCore import SLOT, QObject, Qt, QThreadPool, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QHostInfo, QNetworkInterface

from nwake.hosts import Host, HostError, normalize_mac
from nwake.network import preferred_interface_index, resolve_mac

_ARP_WORKERS = 32
_NAME_WORKERS = 8


@dataclass(frozen=True, slots=True)
class LanNetwork:
    name: str
    source: IPv4Interface
    own_ips: frozenset[IPv4Address] = frozenset()
    own_macs: frozenset[str] = frozenset()

    @property
    def scope(self) -> IPv4Network:
        if self.source.network.prefixlen < 22:
            return IPv4Network((self.source.ip, 24), strict=False)
        return self.source.network

    def targets(self, existing: tuple[Host, ...]) -> tuple[str, ...]:
        excluded = self.own_ips | {
            self.source.ip,
            self.source.network.network_address,
            self.source.network.broadcast_address,
        }
        excluded |= {IPv4Address(host.ip) for host in existing}
        return tuple(str(ip) for ip in self.scope if ip not in excluded)


def local_networks() -> tuple[LanNetwork, ...]:
    interfaces = QNetworkInterface.allInterfaces()
    v4 = QAbstractSocket.NetworkLayerProtocol.IPv4Protocol
    addresses = [
        (iface, entry.ip().toString(), entry.prefixLength())
        for iface in interfaces
        for entry in iface.addressEntries()
        if entry.ip().protocol() == v4
    ]
    own_ips = frozenset(IPv4Address(ip) for _, ip, _ in addresses)
    macs = set()
    for iface in interfaces:
        try:
            macs.add(normalize_mac(iface.hardwareAddress()))
        except HostError:
            pass
    own_macs = frozenset(macs)
    try:
        preferred = preferred_interface_index()
    except OSError:
        preferred = None

    flags = QNetworkInterface.InterfaceFlag
    required = flags.IsUp | flags.IsRunning | flags.CanBroadcast
    excluded = flags.IsLoopBack | flags.IsPointToPoint
    addresses.sort(key=lambda row: (row[0].index() != preferred, row[0].index(), row[1]))
    networks = {}
    for iface, address, prefix in addresses:
        state = iface.flags()
        if state & required != required or state & excluded or not 1 <= prefix <= 30:
            continue
        source = IPv4Interface((address, prefix))
        if source.ip in (source.network.network_address, source.network.broadcast_address):
            continue
        if source.ip.is_unspecified or source.ip.is_multicast or source.ip.is_reserved:
            continue
        name = iface.humanReadableName() or iface.name()
        network = LanNetwork(name, source, own_ips, own_macs)
        networks.setdefault((iface.index(), network.scope), network)
    return tuple(networks.values())


class LanScanner(QObject):
    found = Signal(object)
    renamed = Signal(object)
    progress = Signal(int, int)
    finished = Signal(int, str)
    _reply = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        arp: Callable[[str, str], str | None] = resolve_mac,
        lookup: Callable[..., int] = QHostInfo.lookupHost,
    ):
        super().__init__(parent)
        self._arp = arp
        self._lookup = lookup
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(_ARP_WORKERS)
        self._reply.connect(self._record, Qt.ConnectionType.QueuedConnection)
        self._revision = 0
        self._completed = 0
        self._total = 0
        self._failed = 0
        self._error = ""
        self._macs: set[str] = set()
        self._names: deque[Host] = deque()
        self._lookups: dict[int, Host] = {}

    @property
    def scanning(self) -> bool:
        return self._completed < self._total

    def start(self, network: LanNetwork, existing: tuple[Host, ...]) -> None:
        self.cancel()
        targets = network.targets(existing)
        self._macs = set(network.own_macs) | {host.mac for host in existing}
        self._completed = self._failed = 0
        self._error = ""
        self._total = len(targets)
        self.progress.emit(0, self._total)
        if not targets:
            self.finished.emit(0, "")
            return
        source = str(network.source.ip)
        prefix = network.source.network.prefixlen
        for target in targets:
            self._pool.start(partial(self._probe, self._revision, target, source, prefix))

    def _probe(self, revision: int, ip: str, source: str, prefix: int) -> None:
        host = None
        error = ""
        try:
            if mac := self._arp(ip, source):
                host = Host(ip, ip, mac, prefix)
        except HostError:
            pass  # Ignore addresses without a valid usable 48-bit MAC.
        except OSError as exc:
            error = str(exc) or "ARP 查询失败。"
        self._reply.emit((revision, host, error))

    @Slot(object)
    def _record(self, result: tuple[int, Host | None, str]) -> None:
        revision, host, error = result
        if revision != self._revision:
            return
        self._completed += 1
        if error:
            self._failed += 1
            self._error = self._error or error
        if host is not None and host.mac not in self._macs:
            self._macs.add(host.mac)
            self.found.emit(host)
            self._names.append(host)
            self._start_names()
        self.progress.emit(self._completed, self._total)
        if not self.scanning:
            self.finished.emit(self._failed, self._error)

    def _start_names(self) -> None:
        while self._names and len(self._lookups) < _NAME_WORKERS:
            host = self._names.popleft()
            lookup_id = self._lookup(host.ip, self, SLOT("_record_name(QHostInfo)"))
            if lookup_id >= 0:
                self._lookups[lookup_id] = host

    @Slot(QHostInfo)
    def _record_name(self, info: QHostInfo) -> None:
        host = self._lookups.pop(info.lookupId(), None)
        if host is None:
            return
        if info.error() == QHostInfo.HostInfoError.NoError:
            name = info.hostName().rstrip(".")
            if name and name != host.ip:
                try:
                    renamed = replace(host, name=name)
                except HostError:
                    pass
                else:
                    self.renamed.emit(renamed)
        self._start_names()

    def cancel(self) -> None:
        self._revision += 1
        self._total = self._completed = 0
        self._pool.clear()
        lookup_ids = tuple(self._lookups)
        self._lookups.clear()
        self._names.clear()
        for lookup_id in lookup_ids:
            QHostInfo.abortHostLookup(lookup_id)

    def stop(self) -> None:
        self.cancel()
        self._pool.waitForDone()
