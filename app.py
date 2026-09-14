from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from download_only_torrent import __version__
from download_only_torrent.app_icon import make_app_icon
from download_only_torrent.config import AppConfig
from download_only_torrent.debug_ui import install_debug_ui
from download_only_torrent.engine import TorrentEngine
from download_only_torrent.ui import MainWindow, apply_theme


def main() -> int:
    if "--version" in sys.argv:
        print(__version__)
        return 0

    app = QApplication(sys.argv)
    app.setOrganizationName("Kwon-dev")
    app.setApplicationName("Download Only Torrent")
    app.setQuitOnLastWindowClosed(True)

    icon = make_app_icon()
    app.setWindowIcon(icon)

    config = AppConfig.load()
    apply_theme(app, config.theme)
    engine = TorrentEngine(config)
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
