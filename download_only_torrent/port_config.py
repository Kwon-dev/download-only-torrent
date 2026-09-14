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


def listen_interfaces(port: int) -> str:
    port = max(1, min(65535, int(port)))
    return f"0.0.0.0:{port},[::]:{port}"


def install_engine_listen_port(engine_class) -> None:
    """Inject the persisted port into session settings before lt.session exists.

    This prevents libtorrent from briefly trying its own default 6881 port before
    the runtime networking configuration is applied.
    """

    if getattr(engine_class, "_listen_port_patched", False):
        return
    original = engine_class._session_settings

    def patched(self):
        settings = original(self)
        port = ensure_listen_port()
        settings["listen_interfaces"] = listen_interfaces(port)
        settings["listen_system_port_fallback"] = False
        return settings

    engine_class._session_settings = patched
    engine_class._listen_port_patched = True
