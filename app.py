from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from download_only_torrent import __version__
from download_only_torrent.app_icon import make_app_icon
from download_only_torrent.config import AppConfig
from download_only_torrent.debug_ui import install_debug_ui
from download_only_torrent.engine import TorrentEngine
from download_only_torrent.runtime_fix import (
    apply_runtime_network_fix,
    refresh_discovery,
)
from download_only_torrent.ui import MainWindow, apply_theme


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "KwonDev.DownloadOnlyTorrent"
        )
    except Exception:
        pass


def main() -> int:
    if "--version" in sys.argv:
        print(__version__)
        return 0

    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setOrganizationName("Kwon-dev")
    app.setApplicationName("Download Only Torrent")
    app.setQuitOnLastWindowClosed(True)

    icon = make_app_icon()
    app.setWindowIcon(icon)

    config = AppConfig.load()
    apply_theme(app, config.theme)
    engine = TorrentEngine(config)
    apply_runtime_network_fix(engine)

    # Re-announce once more after libtorrent has had time to create its new
    # OS-selected listen socket.
    QTimer.singleShot(1000, lambda: refresh_discovery(engine))

    window = MainWindow(engine, config)
    window.setWindowIcon(icon)
    try:
        window.tray.setIcon(icon)
    except Exception:
        pass
    install_debug_ui(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
