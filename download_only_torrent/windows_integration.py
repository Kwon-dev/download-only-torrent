from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QDialog, QMessageBox


SERVER_NAME = "KwonDev.DownloadOnlyTorrent.SingleInstance"
PROG_ID = "KwonDev.DownloadOnlyTorrent.torrent"


def _app_command() -> tuple[str, str]:
    if getattr(sys, "frozen", False):
        exe = str(Path(sys.executable).resolve())
        return exe, f'"{exe}" "%1"'
    app_py = str((Path(__file__).resolve().parents[1] / "app.py").resolve())
    exe = str(Path(sys.executable).resolve())
    return exe, f'"{exe}" "{app_py}" "%1"'


def register_windows_associations() -> None:
    """Register .torrent and magnet handlers for the current user.

    Windows UserChoice may still override these registrations if the user has
    explicitly selected another default application. No administrator rights are
    required because everything is written under HKCU.
    """
    if os.name != "nt":
        return

    try:
        import winreg

        exe, command = _app_command()
        classes = r"Software\Classes"

        def set_default(path: str, value: str) -> None:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)

        # Dedicated ProgID for .torrent files.
        prog = classes + "\\" + PROG_ID
        set_default(prog, "BitTorrent torrent file")
        set_default(prog + r"\DefaultIcon", f'"{exe}",0')
        set_default(prog + r"\shell\open\command", command)

        # Register as the preferred per-user handler and as an Open With option.
        set_default(classes + r"\.torrent", PROG_ID)
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            classes + r"\.torrent\OpenWithProgids",
        ) as key:
            winreg.SetValueEx(key, PROG_ID, 0, winreg.REG_NONE, b"")

        # magnet: URL protocol handler.
        magnet = classes + r"\magnet"
        set_default(magnet, "URL:Magnet Protocol")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, magnet) as key:
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        set_default(magnet + r"\DefaultIcon", f'"{exe}",0')
        set_default(magnet + r"\shell\open\command", command)

        # Also advertise the executable in the standard Applications registry.
        app_key = classes + r"\Applications\DownloadOnlyTorrent.exe"
        set_default(app_key + r"\shell\open\command", command)
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            app_key + r"\SupportedTypes",
        ) as key:
            winreg.SetValueEx(key, ".torrent", 0, winreg.REG_SZ, "")
    except OSError:
        # Association registration should never prevent the app from starting.
        pass


def _is_open_request(value: str) -> bool:
    text = value.strip().strip('"')
    if text.lower().startswith("magnet:?"):
        return True
    try:
        return Path(text).suffix.lower() == ".torrent"
    except Exception:
        return False


def first_open_request(argv: list[str]) -> str | None:
    for value in argv[1:]:
        if _is_open_request(value):
            return value.strip().strip('"')
    return None


def forward_to_existing_instance(request: str | None) -> bool:
    """Forward a shell-open request to the already-running instance.

    Returns True when another instance accepted the message and this process can
    exit. Normal launches without an open request are intentionally not forwarded.
    """
    if not request:
        return False
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(250):
        return False
    payload = json.dumps({"open": request}, ensure_ascii=False).encode("utf-8") + b"\n"
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def create_single_instance_server(window) -> QLocalServer:
    server = QLocalServer(window)
    # Remove only a stale endpoint. A live primary instance would already have
    # accepted forward_to_existing_instance() before we get here.
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def accept_connections() -> None:
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket is None:
                continue

            def read_message(sock=socket) -> None:
                data = bytes(sock.readAll()).decode("utf-8", errors="replace")
                for line in data.splitlines():
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    request = str(message.get("open", ""))
                    if request:
                        handle_open_request(window, request)
                sock.disconnectFromServer()

            if socket.bytesAvailable():
                read_message()
            else:
                socket.readyRead.connect(read_message)

    server.newConnection.connect(accept_connections)
    return server


def handle_open_request(window, request: str) -> None:
    request = request.strip().strip('"')
    window._restore()
    if request.lower().startswith("magnet:?"):
        _open_magnet(window, request)
    elif Path(request).suffix.lower() == ".torrent":
        _open_torrent_file(window, request)


def _open_torrent_file(window, path: str) -> None:
    from .ui import FileSelectionDialog, tr

    lang = window.config.language
    try:
        title, files = window.engine.preview_torrent(path)
        dialog = FileSelectionDialog(
            title, files, window.config.download_dir, lang, window
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            window.config.download_dir = dialog.save_path
            window.config.save()
            window.engine.add_torrent_file(
                path, dialog.save_path, dialog.selected_indices()
            )
    except Exception as exc:
        QMessageBox.critical(window, tr(lang, "torrent_error"), str(exc))


def _open_magnet(window, uri: str) -> None:
    from .ui import FileSelectionDialog, MagnetMetadataDialog, tr

    lang = window.config.language
    try:
        loader = MagnetMetadataDialog(
            window.engine, uri, window.config.download_dir, lang, window
        )
        if (
            loader.exec() != QDialog.DialogCode.Accepted
            or loader.metadata is None
        ):
            return
        title, files = loader.metadata
        dialog = FileSelectionDialog(
            title, files, window.config.download_dir, lang, window
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            window.config.download_dir = dialog.save_path
            window.config.save()
            window.engine.pending_magnets[loader.token].save_path = dialog.save_path
            window.engine.start_magnet(loader.token, dialog.selected_indices())
        else:
            window.engine.cancel_pending_magnet(loader.token)
    except Exception as exc:
        QMessageBox.critical(window, tr(lang, "magnet_error"), str(exc))


def schedule_initial_open(window, request: str | None) -> None:
    if request:
        QTimer.singleShot(0, lambda: handle_open_request(window, request))
