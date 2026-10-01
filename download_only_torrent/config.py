from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings


# Public trackers added to every non-private torrent. Torrents found on index
# sites often list mostly dead trackers; these keep discovery working.
DEFAULT_EXTRA_TRACKERS = "\n".join(
    (
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://open.stealth.si:80/announce",
        "udp://tracker.torrent.eu.org:451/announce",
        "udp://exodus.desync.com:6969/announce",
        "udp://open.demonii.com:1337/announce",
        "udp://explodie.org:6969/announce",
    )
)


@dataclass(slots=True)
class AppConfig:
    download_dir: str
    download_limit_kib: int = 0
    max_connections: int = 200
    enable_dht: bool = True
    enable_pex: bool = True
    enable_lsd: bool = True
    enable_tcp: bool = True
    enable_utp: bool = True
    delete_torrent_source: bool = True
    auto_remove_completed: bool = True
    minimize_to_tray: bool = True
    notify_on_complete: bool = True
    start_with_windows: bool = False
    theme: str = "dark"
    language: str = "en"
    language_user_selected: bool = False
    add_extra_trackers: bool = True
    extra_trackers: str = DEFAULT_EXTRA_TRACKERS

    def extra_tracker_urls(self) -> list[str]:
        if not self.add_extra_trackers:
            return []
        urls: list[str] = []
        for line in self.extra_trackers.splitlines():
            url = line.strip()
            lowered = url.lower()
            if url and lowered.startswith(("udp://", "http://", "https://", "wss://")):
                if url not in urls:
                    urls.append(url)
        return urls

    @classmethod
    def load(cls) -> "AppConfig":
        settings = QSettings()
        default_download = str(Path.home() / "Downloads")
        language_user_selected = _as_bool(
            settings.value("general/language_user_selected", False)
        )
        if language_user_selected:
            language = str(settings.value("general/language", "en"))
        else:
            language = "ko" if QLocale.system().name().lower().startswith("ko") else "en"

        return cls(
            download_dir=str(settings.value("general/download_dir", default_download)),
            download_limit_kib=int(settings.value("network/download_limit_kib", 0)),
            max_connections=int(settings.value("network/max_connections", 200)),
            enable_dht=_as_bool(settings.value("network/dht", True)),
            enable_pex=_as_bool(settings.value("network/pex", True)),
            enable_lsd=_as_bool(settings.value("network/lsd", True)),
            enable_tcp=_as_bool(settings.value("network/tcp", True)),
            enable_utp=_as_bool(settings.value("network/utp", True)),
            delete_torrent_source=_as_bool(
                settings.value("download/delete_torrent_source", True)
            ),
            auto_remove_completed=_as_bool(
                settings.value("download/auto_remove_completed", True)
            ),
            minimize_to_tray=_as_bool(
                settings.value("general/minimize_to_tray", True)
            ),
            notify_on_complete=_as_bool(
                settings.value("general/notify_on_complete", True)
            ),
            start_with_windows=_as_bool(
                settings.value("general/start_with_windows", False)
            ),
            theme=str(settings.value("general/theme", "dark")),
            language=language,
            language_user_selected=language_user_selected,
            add_extra_trackers=_as_bool(
                settings.value("network/add_extra_trackers", True)
            ),
            extra_trackers=str(
                settings.value("network/extra_trackers", DEFAULT_EXTRA_TRACKERS)
            ),
        )

    def save(self) -> None:
        settings = QSettings()
        settings.setValue("general/download_dir", self.download_dir)
        settings.setValue("network/download_limit_kib", self.download_limit_kib)
        settings.setValue("network/max_connections", self.max_connections)
        settings.setValue("network/dht", self.enable_dht)
        settings.setValue("network/pex", self.enable_pex)
        settings.setValue("network/lsd", self.enable_lsd)
        settings.setValue("network/tcp", self.enable_tcp)
        settings.setValue("network/utp", self.enable_utp)
        settings.setValue(
            "download/delete_torrent_source", self.delete_torrent_source
        )
        settings.setValue(
            "download/auto_remove_completed", self.auto_remove_completed
        )
        settings.setValue("general/minimize_to_tray", self.minimize_to_tray)
        settings.setValue("general/notify_on_complete", self.notify_on_complete)
        settings.setValue("general/start_with_windows", self.start_with_windows)
        settings.setValue("general/theme", self.theme)
        settings.setValue("general/language", self.language)
        settings.setValue(
            "general/language_user_selected", self.language_user_selected
        )
        settings.setValue("network/add_extra_trackers", self.add_extra_trackers)
        settings.setValue("network/extra_trackers", self.extra_trackers)
        settings.sync()
        _set_windows_startup(self.start_with_windows)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    return f'"{sys.executable}" "{app_path}"'


def _set_windows_startup(enabled: bool) -> None:
    if os.name != "nt":
        return
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, "DownloadOnlyTorrent", 0, winreg.REG_SZ, _startup_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, "DownloadOnlyTorrent")
                except FileNotFoundError:
                    pass
    except OSError:
        pass
