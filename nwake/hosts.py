"""Validated host records and per-user JSON storage."""

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

MAX_HOSTS = 64
LIMITED_BROADCAST = "255.255.255.255"
_MAC = re.compile(
    r"(?:[0-9a-f]{12}|[0-9a-f]{2}(?P<s>[:-])(?:[0-9a-f]{2}(?P=s)){4}[0-9a-f]{2})", re.I
)


class HostError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


class StoreError(Exception):
    """The configuration could not be read or safely saved."""


def normalize_mac(mac: str) -> str:
    raw = mac.strip()
    if not _MAC.fullmatch(raw):
        raise HostError("mac", "请输入 12 位十六进制的网卡 MAC 地址。")
    data = bytes.fromhex(raw.replace(":", "").replace("-", ""))
    if not any(data) or data[0] & 1:
        raise HostError("mac", "请输入网卡自身的 MAC 地址，不能使用全零或组播地址。")
    return data.hex(":").upper()


@dataclass(frozen=True, slots=True)
class Host:
    name: str
    ip: str
    mac: str
    prefix: int | None = None

    def __post_init__(self):
        name = self.name.strip()
        if not name or len(name) > 64 or any(not char.isprintable() for char in name):
            raise HostError("name", "请输入 1–64 个可见字符作为主机名。")
        try:
            ip = IPv4Address(self.ip.strip())
        except ValueError as error:
            raise HostError("ip", "请输入有效的 IPv4 地址，例如 192.168.1.20。") from error
        if ip.is_unspecified or ip.is_loopback or ip.is_multicast or ip.is_reserved:
            raise HostError("ip", "请输入目标电脑的局域网 IPv4 地址。")
        mac = normalize_mac(self.mac)
        if self.prefix is not None:
            if type(self.prefix) is not int or not 1 <= self.prefix <= 30:
                raise HostError("prefix", "请输入 1–30 的子网前缀长度，例如 24。")
            subnet = IPv4Network((ip, self.prefix), strict=False)
            if ip in (subnet.network_address, subnet.broadcast_address):
                raise HostError("prefix", "此 IPv4 在该子网中是网络或广播地址，请检查前缀。")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "ip", str(ip))
        object.__setattr__(self, "mac", mac)

    @property
    def broadcast(self) -> str:
        if self.prefix is None:
            return LIMITED_BROADCAST
        return str(IPv4Network((self.ip, self.prefix), strict=False).broadcast_address)


def validate_inventory(hosts: tuple[Host, ...]) -> None:
    if len(hosts) > MAX_HOSTS:
        raise HostError("name", f"最多管理 {MAX_HOSTS} 台电脑，请先移除不用的记录。")
    ips, macs = set(), set()
    for host in hosts:
        if host.ip in ips:
            raise HostError("ip", "该 IPv4 地址已在电脑列表中。")
        if host.mac in macs:
            raise HostError("mac", "该 MAC 地址已在电脑列表中。")
        ips.add(host.ip)
        macs.add(host.mac)


def data_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / "AppData" / "Local") / "Nwake"


class HostStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> tuple[Host, ...]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or type(data.get("version")) is not int
                or data["version"] != 1
                or not isinstance(data.get("hosts"), list)
            ):
                raise ValueError("无法识别文件格式或版本。")
            hosts = tuple(Host(**row) for row in data["hosts"])
            validate_inventory(hosts)
            return hosts
        except FileNotFoundError:
            return ()
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise StoreError(f"无法读取电脑列表：{error}") from error

    def save(self, hosts: tuple[Host, ...]) -> None:
        validate_inventory(hosts)
        temporary = None
        try:
            data = {"version": 1, "hosts": [asdict(host) for host in hosts]}
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, encoding="utf-8", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError as error:
            raise StoreError(f"无法保存电脑列表：{error}") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
