from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from download_only_torrent import __version__
from download_only_torrent.config import AppConfig
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

    config = AppConfig.load()
    apply_theme(app, config.theme)
    engine = TorrentEngine(config)
    window = MainWindow(engine, config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
