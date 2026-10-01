from __future__ import annotations

import socket

from PySide6.QtCore import QSettings


DEFAULT_MIN_PORT = 49152
DEFAULT_MAX_PORT = 65535


def _set_exclusive(sock: socket.socket) -> None:
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    except OSError:
        pass


def pick_free_port() -> int:
    """Choose a currently unused TCP+UDP IPv4 port and return it.

    The TCP socket is first bound to port 0 so the OS chooses an available
    ephemeral port. The same port is then probed for UDP availability before it
    is accepted. This is intended for initial configuration and the Settings
    'auto pick' button, not as a long-lived reservation.
    """

    for _ in range(64):
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            _set_exclusive(tcp)
            _set_exclusive(udp)
            tcp.bind(("0.0.0.0", 0))
            port = int(tcp.getsockname()[1])
            if not (1 <= port <= 65535):
                continue
            udp.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
        finally:
            tcp.close()
            udp.close()

    # Extremely unlikely fallback. Pick from the dynamic/private range and let
    # libtorrent report a bind error in diagnostics if another process races us.
    return DEFAULT_MIN_PORT


def ensure_listen_port() -> int:
    settings = QSettings()
    raw = settings.value("network/listen_port", None)
    try:
        port = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        port = 0

    if not (1 <= port <= 65535):
        port = pick_free_port()
        settings.setValue("network/listen_port", port)
        settings.sync()
    return port


def save_listen_port(port: int) -> int:
    port = max(1, min(65535, int(port)))
    settings = QSettings()
    settings.setValue("network/listen_port", port)
    settings.sync()
    return port


BIND_DEFAULT_INTERFACE_KEY = "network/bind_default_interface"


def _probe_local_address(family: int, target: tuple) -> str | None:
    """Local address the OS would use to reach target.

    Connecting a UDP socket only selects a route; no packet is sent.
    """

    try:
        # Creating the socket fails outright when the family (usually IPv6)
        # is disabled on this machine.
        sock = socket.socket(family, socket.SOCK_DGRAM)
    except OSError:
        return None
    try:
        sock.connect(target)
        return str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        sock.close()


def default_route_addresses() -> tuple[str | None, str | None]:
    ipv4 = _probe_local_address(socket.AF_INET, ("1.1.1.1", 53))
    if ipv4 and (ipv4.startswith("127.") or ipv4.startswith("0.")):
        ipv4 = None
    ipv6 = None
    if socket.has_ipv6:
        ipv6 = _probe_local_address(socket.AF_INET6, ("2606:4700:4700::1111", 53))
        if ipv6 and (ipv6 == "::1" or ipv6.lower().startswith("fe80")):
            ipv6 = None
    return ipv4, ipv6


def bind_default_interface_enabled() -> bool:
    value = QSettings().value(BIND_DEFAULT_INTERFACE_KEY, True)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def set_bind_default_interface(enabled: bool) -> None:
    settings = QSettings()
    settings.setValue(BIND_DEFAULT_INTERFACE_KEY, bool(enabled))
    settings.sync()


def listen_interfaces(port: int, addresses: tuple | None = None) -> str:
    """libtorrent listen_interfaces for the given port.

    Listening on 0.0.0.0/[::] makes libtorrent open a socket, and announce to
    every tracker, on every local address: VPN and Hyper-V/WSL adapters,
    loopback and link-local IPv6 included, most of which cannot reach the
    internet. By default only the address(es) of the default route are used.
    """

    port = max(1, min(65535, int(port)))
    if bind_default_interface_enabled():
        ipv4, ipv6 = addresses if addresses is not None else default_route_addresses()
        parts = []
        if ipv4:
            parts.append(f"{ipv4}:{port}")
        if ipv6:
            parts.append(f"[{ipv6}]:{port}")
        if parts:
            return ",".join(parts)
    return f"0.0.0.0:{port},[::]:{port}"
