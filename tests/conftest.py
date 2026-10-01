from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import libtorrent as lt
import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from download_only_torrent.config import AppConfig  # noqa: E402
from download_only_torrent.engine import TorrentEngine  # noqa: E402

# These tests run against the stock libtorrent wheel. They exercise the app's
# own logic; the piece-upload patch itself is verified by the Windows build.


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName("Kwon-dev-tests")
    QCoreApplication.setApplicationName("Download Only Torrent Tests")
    return app


@pytest.fixture(autouse=True)
def isolated_home(qapp, tmp_path, monkeypatch):
    """Fresh HOME (engine data dir) and QSettings store for every test."""

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    settings_dir = tmp_path / "settings"
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(settings_dir))
    settings = QSettings()
    settings.clear()
    # Deterministic networking: listen on all interfaces, no extra trackers
    # unless a test turns them on.
    settings.setValue("network/bind_default_interface", False)
    settings.setValue("network/add_extra_trackers", False)
    settings.sync()
    return home


def data_dir(home: Path) -> Path:
    return home / ".download-only-torrent"


def write_session(home: Path, entries: list[dict]) -> None:
    folder = data_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "session.json").write_text(json.dumps(entries), encoding="utf-8")


def read_session(home: Path) -> list[dict]:
    return json.loads((data_dir(home) / "session.json").read_text(encoding="utf-8"))


def make_config(download_dir: Path, **overrides) -> AppConfig:
    config = AppConfig(download_dir=str(download_dir))
    config.add_extra_trackers = False
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def make_engine(download_dir: Path, **overrides) -> TorrentEngine:
    return TorrentEngine(make_config(download_dir, **overrides))


def close_engine(engine: TorrentEngine) -> None:
    try:
        engine.session.pause()
    except Exception:
        pass
    engine.session = None
    gc.collect()


def make_torrent(
    folder: Path,
    name: str,
    size: int,
    *,
    piece_size: int = 64 * 1024,
    private: bool = False,
    trackers: tuple[str, ...] = (),
) -> tuple[Path, bytes]:
    """Write random content and return (content dir, .torrent bytes)."""

    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    with target.open("wb") as handle:
        remaining = size
        while remaining:
            chunk = min(remaining, 1024 * 1024)
            handle.write(os.urandom(chunk))
            remaining -= chunk
    storage = lt.file_storage()
    lt.add_files(storage, str(target))
    creator = lt.create_torrent(storage, piece_size)
    for tracker in trackers:
        creator.add_tracker(tracker)
    if private:
        creator.set_priv(True)
    lt.set_piece_hashes(creator, str(folder))
    return folder, lt.bencode(creator.generate())


class Seeder:
    """A local libtorrent session that uploads slowly, so downloads stay partial."""

    def __init__(self, upload_limit: int = 256 * 1024):
        self.session = lt.session(
            {
                "listen_interfaces": "127.0.0.1:0",
                "enable_dht": False,
                "enable_lsd": False,
                "enable_upnp": False,
                "enable_natpmp": False,
            }
        )
        peer_class = self.session.get_peer_class(lt.session.local_peer_class_id)
        peer_class["upload_limit"] = upload_limit
        self.session.set_peer_class(lt.session.local_peer_class_id, peer_class)

    @property
    def endpoint(self) -> tuple[str, int]:
        return ("127.0.0.1", self.session.listen_port())

    def seed(self, content_dir: Path, torrent: bytes) -> None:
        params = lt.add_torrent_params()
        params.ti = lt.torrent_info(torrent)
        params.save_path = str(content_dir)
        self.session.add_torrent(params)


@pytest.fixture
def seeder():
    instance = Seeder()
    yield instance
    instance.session.pause()


def pump(engine: TorrentEngine, seconds: float, until=None) -> bool:
    """Drive engine.poll() like the UI timer does, until a condition holds."""

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        engine.poll()
        if until is not None and until():
            return True
        time.sleep(0.05)
    return until is None


def spin_qt(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
