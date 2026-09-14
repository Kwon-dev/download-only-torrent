from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from download_only_torrent import __version__
from download_only_torrent.app_icon import make_app_icon
from download_only_torrent.config import AppConfig
from download_only_torrent.controls_ui import install_controls_ui
from download_only_torrent.debug_ui import install_debug_ui
from download_only_torrent.engine import TorrentEngine
from download_only_torrent.runtime_fix import (
    apply_runtime_network_fix,
    refresh_discovery,
)
from download_only_torrent.ui import MainWindow, apply_theme
from download_only_torrent.windows_integration import (
    create_single_instance_server,
    first_open_request,
    forward_to_existing_instance,
    register_windows_associations,
    schedule_initial_open,
)


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

    open_request = first_open_request(sys.argv)
    if forward_to_existing_instance(open_request):
        return 0

    # Keep the per-user shell registration pointed at the exact EXE currently
    # being run. This is useful for portable/run-numbered CI builds too.
    register_windows_associations()

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
    install_controls_ui(window)

    # Keep this object referenced by the window for the application's lifetime.
    window._single_instance_server = create_single_instance_server(window)

    window.show()
    schedule_initial_open(window, open_request)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
