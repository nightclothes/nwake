"""Wake-on-LAN datagrams, ICMP probes and ARP via the Windows IP Helper API."""

import ctypes
import socket
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum, auto
from functools import cache
from struct import unpack_from
from sys import byteorder

from nwake.hosts import Host, normalize_mac

WAKE_PORT = 9
PROBE_TIMEOUT_MS = 750
_UNREACHABLE = {11002, 11003, 11004, 11005, 11010}
_INVALID_HANDLE = ctypes.c_void_p(-1).value


class Reachability(Enum):
    ONLINE = auto()
    NO_REPLY = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class ProbeResult:
    state: Reachability
    detail: str = ""


def magic_packet(mac: str) -> bytes:
    return b"\xff" * 6 + bytes.fromhex(normalize_mac(mac).replace(":", "")) * 16


def send_wake(host: Host) -> None:
    packet = magic_packet(host.mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        if sock.sendto(packet, (host.broadcast, WAKE_PORT)) != len(packet):
            raise OSError("系统未接受完整的唤醒包。")


@cache
def _arp_api():
    api = ctypes.WinDLL("iphlpapi.dll")
    uint32 = wintypes.ULONG
    api.SendARP.argtypes = [uint32, uint32, wintypes.LPVOID, ctypes.POINTER(uint32)]
    api.SendARP.restype = wintypes.DWORD
    api.GetBestInterface.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.GetBestInterface.restype = wintypes.DWORD
    return api


def preferred_interface_index() -> int | None:
    """Use the Windows routing table to choose the initial network in the scanner."""
    index = wintypes.DWORD()
    return index.value if _arp_api().GetBestInterface(0, ctypes.byref(index)) == 0 else None


def resolve_mac(ip: str, source: str) -> str | None:
    """Look up a directly reachable IPv4 neighbor on the selected local interface."""
    address = int.from_bytes(socket.inet_aton(ip), byteorder)
    source_address = int.from_bytes(socket.inet_aton(source), byteorder)
    # SendARP expects storage aligned as an array of ULONGs, with at least six bytes.
    buffer = (wintypes.ULONG * 2)()
    size = wintypes.ULONG(ctypes.sizeof(buffer))
    status = _arp_api().SendARP(address, source_address, buffer, ctypes.byref(size))
    if status in (31, 67):  # ERROR_GEN_FAILURE / ERROR_BAD_NET_NAME: no ARP response.
        return None
    if status != 0:
        raise ctypes.WinError(status)
    return bytes(buffer)[:6].hex(":").upper() if size.value == 6 else None


@cache
def _icmp_api():
    api = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)
    api.IcmpCreateFile.argtypes = []
    api.IcmpCreateFile.restype = wintypes.HANDLE
    api.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
    api.IcmpCloseHandle.restype = wintypes.BOOL
    api.IcmpSendEcho.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.WORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    api.IcmpSendEcho.restype = wintypes.DWORD
    return api


def _interpret_echo(count: int, reply: bytes, destination: int, error: int) -> ProbeResult:
    if count:
        # Address and Status are the first two uint32 fields on both Win32 and Win64.
        address, code = unpack_from("=II", reply)
        if code == 0:
            return ProbeResult(
                Reachability.ONLINE if address == destination else Reachability.NO_REPLY
            )
    else:
        code = error
    if code in _UNREACHABLE:
        return ProbeResult(Reachability.NO_REPLY)
    return ProbeResult(Reachability.ERROR, f"Windows Ping 返回错误 {code}。")


def probe_ipv4(ip: str, timeout_ms: int = PROBE_TIMEOUT_MS) -> ProbeResult:
    try:
        api = _icmp_api()
        handle = api.IcmpCreateFile()
        if handle is None or handle == _INVALID_HANDLE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            address = int.from_bytes(socket.inet_aton(ip), byteorder)
            request = b"Nwake"
            reply = ctypes.create_string_buffer(128)
            count = api.IcmpSendEcho(
                handle, address, request, len(request), None, reply, len(reply), timeout_ms
            )
            error = ctypes.get_last_error() if not count else 0
            return _interpret_echo(count, reply.raw, address, error)
        finally:
            api.IcmpCloseHandle(handle)
    except OSError as error:
        return ProbeResult(Reachability.ERROR, str(error))
