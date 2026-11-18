"""Wake-on-LAN, ICMP, ARP and NetBIOS queries for local computers."""

import ctypes
import socket
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum, auto
from functools import cache
from secrets import randbits
from struct import Struct, pack, unpack_from
from sys import byteorder, platform

from nwake.hosts import Host, normalize_mac

WAKE_PORT = 9
PROBE_TIMEOUT_MS = 750
_UNREACHABLE = {11002, 11003, 11004, 11005, 11010}
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_NBNS_PORT = 137
_NBNS_TIMEOUT = 0.75
_NBNS_HEADER = Struct("!6H")
_NBNS_RECORD = Struct("!HHIH")
_NBNS_NAME = Struct("!15sBH")
_NBSTAT = 0x0021
_IN = 0x0001
# RFC 1002 first-level encoding of the wildcard '*' followed by 15 null bytes.
_NBNS_WILDCARD = b"\x20CK" + b"A" * 30 + b"\x00"


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


def resolve_netbios_name(ip: str, source: str) -> str | None:
    """Ask one ARP-discovered neighbor for its NetBIOS computer name."""
    query_id = randbits(16)
    query = _NBNS_HEADER.pack(query_id, 0, 1, 0, 0, 0)
    query += _NBNS_WILDCARD + pack("!HH", _NBSTAT, _IN)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(_NBNS_TIMEOUT)
        sock.bind((source, 0))
        sock.connect((ip, _NBNS_PORT))
        sock.send(query)
        return _netbios_computer_name(sock.recv(8192), query_id)


def _netbios_computer_name(reply: bytes, query_id: int) -> str | None:
    # RFC 1002 §4.2.18 gives one answer with the queried name and no questions.
    record_offset = _NBNS_HEADER.size + len(_NBNS_WILDCARD)
    data_offset = record_offset + _NBNS_RECORD.size
    if len(reply) <= data_offset:
        return None
    reply_id, flags, questions, answers, _, _ = _NBNS_HEADER.unpack_from(reply)
    # Check the response bit, opcode, truncation bit and response code.
    if reply_id != query_id or flags & 0xFA0F != 0x8000 or (questions, answers) != (0, 1):
        return None
    if reply[_NBNS_HEADER.size : record_offset] != _NBNS_WILDCARD:
        return None
    kind, record_class, _, length = _NBNS_RECORD.unpack_from(reply, record_offset)
    if (kind, record_class) != (_NBSTAT, _IN) or data_offset + length > len(reply):
        return None
    names_start = data_offset + 1
    names_end = names_start + reply[data_offset] * _NBNS_NAME.size
    if names_end > data_offset + length:
        return None
    for offset in range(names_start, names_end, _NBNS_NAME.size):
        raw_name, suffix, name_flags = _NBNS_NAME.unpack_from(reply, offset)
        # The unique active <00> entry is the workstation's computer name.
        if suffix != 0 or name_flags & 0x9C00 != 0x0400:
            continue
        try:
            name = raw_name.rstrip(b" \x00").decode("oem" if platform == "win32" else "ascii")
        except UnicodeDecodeError:
            continue
        if name and name.isprintable():
            return name
    return None


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
