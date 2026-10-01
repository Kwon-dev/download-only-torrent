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
from download_only_torrent.desktop_experience import install_desktop_experience
from download_only_torrent.engine import TorrentEngine
from download_only_torrent.network_ui import install_network_ui
from download_only_torrent.runtime_fix import refresh_discovery
from download_only_torrent.sorting_ui import install_sorting_ui
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


def build_main_window(app: QApplication, icon=None) -> MainWindow:
    """Create the engine and the fully extended main window (not shown)."""

    config = AppConfig.load()
    apply_theme(app, config.theme)
    # The engine builds every session setting (listen port and address, queue
    # limits, peer strategy, client identity) before restoring downloads.
    engine = TorrentEngine(config)
    # Save resume data so the next launch skips re-hashing every download.
    # Windows logoff/shutdown asks for commitData and may never reach
    # aboutToQuit, so save there as well.
    app.aboutToQuit.connect(engine.save_all_resume_data)
    app.commitDataRequest.connect(
        lambda _manager: engine.save_all_resume_data(timeout=5.0)
    )

    # Re-announce once more after libtorrent has had time to create its listen
    # socket on the selected port.
    QTimer.singleShot(1000, lambda: refresh_discovery(engine))

    window = MainWindow(engine, config)
    if icon is not None:
        window.setWindowIcon(icon)
        try:
            window.tray.setIcon(icon)
        except Exception:
            pass

    # Install extensions before controls so Ctrl+O points at the multi-file
    # torrent picker rather than the original single-file action.
    install_network_ui(window)
    install_desktop_experience(window)
    install_debug_ui(window)
    install_controls_ui(window)
    install_sorting_ui(window)
    return window


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

    window = build_main_window(app, icon)

    # Keep this object referenced by the window for the application's lifetime.
    window._single_instance_server = create_single_instance_server(window)

    window.show()
    schedule_initial_open(window, open_request)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
