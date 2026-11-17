"""Bounded network jobs and reachability state, owned by the Qt main thread."""

from collections.abc import Callable
from datetime import datetime
from threading import Event
from time import monotonic

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot

from nwake.hosts import Host
from nwake.network import ProbeResult, Reachability, probe_ipv4, send_wake

REFRESH_MS = 5_000
WAIT_SECONDS = 45


class _Task(QRunnable):
    def __init__(self, work: Callable[[], object], completed: Signal):
        super().__init__()
        self.work = work
        self.completed = completed

    def run(self) -> None:
        self.completed.emit(self.work())


class Monitor(QObject):
    changed = Signal()
    wake_finished = Signal(object)
    _probe_done = Signal(object)
    _wake_done = Signal(object)

    def __init__(
        self,
        hosts: tuple[Host, ...],
        probe: Callable[[str], ProbeResult] = probe_ipv4,
        wake: Callable[[Host], None] = send_wake,
    ):
        super().__init__()
        self.hosts = hosts
        self._probe = probe
        self._wake = wake
        self._probes: dict[Host, ProbeResult] = {}
        self._waiting: dict[Host, float] = {}
        self._revision = 0
        self._remaining = 0
        self.sending = False
        self.last_scan: datetime | None = None
        self._stopping = Event()

        self._scan_pool = QThreadPool(self)
        self._scan_pool.setMaxThreadCount(8)
        self._wake_pool = QThreadPool(self)
        self._wake_pool.setMaxThreadCount(1)
        self._probe_done.connect(self._record_probe, Qt.ConnectionType.QueuedConnection)
        self._wake_done.connect(self._record_wake, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self, interval=REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

    @property
    def scanning(self) -> bool:
        return self._remaining > 0

    def start(self) -> None:
        self._timer.start()
        self.refresh()

    def set_hosts(self, hosts: tuple[Host, ...]) -> None:
        if hosts == self.hosts:
            return
        self.hosts = hosts
        self._revision += 1
        self._probes = {host: self._probes[host] for host in hosts if host in self._probes}
        self._waiting = {host: self._waiting[host] for host in hosts if host in self._waiting}
        self.refresh()
        self.changed.emit()

    def readout(self, host: Host) -> tuple[str, str]:
        probe = self._probes.get(host)
        if probe and probe.state is Reachability.ONLINE:
            return "online", "在线"
        if probe and probe.state is Reachability.ERROR:
            return "error", probe.detail
        if self._waiting.get(host, 0) > monotonic():
            return "waiting", "唤醒包已发送，正在等待电脑回应。"
        if probe:
            return "quiet", "未收到 Ping 回复；电脑可能已关机、休眠或禁止 Ping。"
        return "checking", "正在等待首次检测。"

    @Slot()
    def refresh(self) -> None:
        if self._stopping.is_set() or self.scanning or not self.hosts:
            return
        self._remaining = len(self.hosts)
        revision = self._revision
        for host in self.hosts:
            task = _Task(lambda host=host: self._scan_one(revision, host), self._probe_done)
            self._scan_pool.start(task)
        self.changed.emit()

    def _scan_one(self, revision: int, host: Host) -> tuple[int, Host, ProbeResult]:
        try:
            result = self._probe(host.ip)
        except OSError as error:
            result = ProbeResult(Reachability.ERROR, str(error))
        return revision, host, result

    @Slot(object)
    def _record_probe(self, item: tuple[int, Host, ProbeResult]) -> None:
        if self._stopping.is_set():
            return
        revision, host, result = item
        self._remaining -= 1
        if revision == self._revision:
            self._probes[host] = result
            if result.state is Reachability.ONLINE:
                self._waiting.pop(host, None)
            if not self.scanning:
                self.last_scan = datetime.now()
        elif not self.scanning:
            self.refresh()
        self.changed.emit()

    def wake(self, hosts: tuple[Host, ...]) -> None:
        if self._stopping.is_set() or self.sending or not hosts:
            return
        self.sending = True
        self._wake_pool.start(_Task(lambda: self._send_batch(hosts), self._wake_done))
        self.changed.emit()

    def _send_batch(self, hosts: tuple[Host, ...]) -> list[tuple[Host, str, float]]:
        outcome = []
        for host in hosts:
            if self._stopping.is_set():
                break
            try:
                self._wake(host)
                outcome.append((host, "", monotonic() + WAIT_SECONDS))
            except OSError as error:
                outcome.append((host, str(error) or "系统未接受唤醒包。", 0))
        return outcome

    @Slot(object)
    def _record_wake(self, outcome: list[tuple[Host, str, float]]) -> None:
        if self._stopping.is_set():
            return
        self.sending = False
        for host, error, until in outcome:
            if host in self.hosts and not error:
                self._waiting[host] = until
        self.wake_finished.emit(outcome)
        self.refresh()
        self.changed.emit()

    @Slot()
    def stop(self) -> None:
        self._stopping.set()
        self._timer.stop()
        self._scan_pool.clear()
        self._wake_pool.clear()
        self._scan_pool.waitForDone()
        self._wake_pool.waitForDone()
