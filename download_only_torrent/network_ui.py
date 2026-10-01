from __future__ import annotations

from types import MethodType

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from .port_config import ensure_listen_port, pick_free_port, save_listen_port
from .runtime_fix import apply_listen_port, refresh_discovery
from .ui import FileSelectionDialog, SettingsDialog, tr


TEXT = {
    "en": {
        "listen_port": "Listen port",
        "auto_port": "Auto pick",
        "port_tip": "The first launch picks an unused port automatically. You can change it here at any time.",
    },
    "ko": {
        "listen_port": "수신 포트",
        "auto_port": "빈 포트 자동 선택",
        "port_tip": "최초 실행 시 사용하지 않는 포트를 자동으로 고릅니다. 이후에는 여기서 원하는 포트로 변경할 수 있습니다.",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXT.get(lang, TEXT["en"]).get(key, key)


def install_settings_port_extension() -> None:
    if getattr(SettingsDialog, "_listen_port_extended", False):
        return

    original_init = SettingsDialog.__init__
    original_apply = SettingsDialog.apply

    def extended_init(self, config, parent=None):
        original_init(self, config, parent)
        lang = config.language

        self.listen_port = QSpinBox(self)
        self.listen_port.setRange(1, 65535)
        self.listen_port.setValue(ensure_listen_port())
        self.listen_port.setToolTip(_t(lang, "port_tip"))

        auto_button = QPushButton(_t(lang, "auto_port"), self)
        auto_button.clicked.connect(
            lambda: self.listen_port.setValue(pick_free_port())
        )

        widget = QWidget(self)
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.listen_port, 1)
        row.addWidget(auto_button)

        # Right after "max peers" on the General tab.
        self.general_form.insertRow(3, _t(lang, "listen_port"), widget)

    def extended_apply(self):
        original_apply(self)
        port = save_listen_port(self.listen_port.value())
        parent = self.parent()
        engine = getattr(parent, "engine", None)
        if engine is not None:
            apply_listen_port(engine, port)
            refresh_discovery(engine)

    SettingsDialog.__init__ = extended_init
    SettingsDialog.apply = extended_apply
    SettingsDialog._listen_port_extended = True


def _show_one_torrent_dialog(window, path: str) -> None:
    lang = window.config.language
    try:
        title, files = window.engine.preview_torrent(path)
    except Exception as exc:
        QMessageBox.critical(window, tr(lang, "torrent_error"), f"{path}\n\n{exc}")
        return

    dialog = FileSelectionDialog(
        title,
        files,
        window.config.download_dir,
        lang,
        window,
    )
    dialog.setWindowModality(Qt.WindowModality.NonModal)

    if not hasattr(window, "_multi_torrent_dialogs"):
        window._multi_torrent_dialogs = set()
    window._multi_torrent_dialogs.add(dialog)

    def start_download(dlg=dialog, torrent_path=path) -> None:
        try:
            window.config.download_dir = dlg.save_path
            window.config.save()
            window.engine.add_torrent_file(
                torrent_path,
                dlg.save_path,
                dlg.selected_indices(),
            )
        except Exception as exc:
            QMessageBox.critical(
                window,
                tr(window.config.language, "torrent_error"),
                f"{torrent_path}\n\n{exc}",
            )

    def cleanup(_result: int, dlg=dialog) -> None:
        try:
            window._multi_torrent_dialogs.discard(dlg)
        except Exception:
            pass
        dlg.deleteLater()

    dialog.accepted.connect(start_download)
    dialog.finished.connect(cleanup)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def install_multi_torrent_picker(window) -> None:
    def add_torrents(self, *_args) -> None:
        lang = self.config.language
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr(lang, "open_torrent"),
            "",
            tr(lang, "torrent_files"),
        )
        for path in paths:
            _show_one_torrent_dialog(self, path)

    window.add_torrent = MethodType(add_torrents, window)

    action = getattr(window, "actions", {}).get("add_torrent")
    if action is not None:
        try:
            action.triggered.disconnect()
        except Exception:
            pass
        action.triggered.connect(window.add_torrent)


def install_network_ui(window) -> None:
    install_settings_port_extension()
    install_multi_torrent_picker(window)
