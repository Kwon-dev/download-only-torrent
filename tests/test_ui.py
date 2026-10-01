from __future__ import annotations

import time

import libtorrent as lt

import app as app_module
from download_only_torrent import debug_ui, desktop_experience, ui

from conftest import make_torrent, spin_qt


class _FakePeer:
    def __init__(self, ip, flags):
        self.ip = ip
        self.flags = flags


class _FakeHandle:
    def __init__(self, peers):
        self.peers = peers
        self.dialed = []

    def status(self):
        return type("S", (), {"state": type("E", (), {"name": "downloading"})()})()

    def get_peer_info(self):
        return list(self.peers)

    def max_connections(self):
        return 10

    def connect_peer(self, endpoint):
        self.dialed.append(endpoint)


def test_state_labels_are_translated():
    assert ui.state_label("ko", "CHECKING FILES") == "파일 검사 중"
    assert ui.state_label("ko", "QUEUED FOR CHECK") == "검사 대기"
    assert ui.state_label("en", "DOWNLOADING METADATA") == "Fetching metadata"
    assert ui.state_label("en", "SOMETHING NEW") == "Something New"


def test_main_window_diagnostics_and_status_bar(qapp, tmp_path, seeder):
    content, torrent = make_torrent(tmp_path / "seed", "payload.bin", 4 * 1024 * 1024)
    seeder.seed(content, torrent)
    path = tmp_path / "payload.torrent"
    path.write_bytes(torrent)

    window = app_module.build_main_window(qapp)
    engine = window.engine
    task_id = engine.add_torrent_file(str(path), str(tmp_path / "dl"), [0])
    handle = engine.tasks[task_id].handle
    handle.connect_peer(seeder.endpoint)

    # Wait for the real condition (seed connected and unchoking us) rather
    # than a fixed delay; slower CI runners take longer to get there.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        spin_qt(100)
        peers = handle.get_peer_info()
        if any(
            p.flags & lt.peer_info.seed and not p.flags & lt.peer_info.remote_choked
            for p in peers
        ):
            break

    text = debug_ui.torrent_diagnostics(window, task_id)
    peers_section = text[text.index("[Peers]") : text.index("[Peer disconnect")]
    assert f"127.0.0.1:{seeder.endpoint[1]}" in peers_section, peers_section
    assert "seeds 1 (choking us 0)" in peers_section, peers_section
    assert "saved_torrent_copy:" in text

    session_text = debug_ui.session_diagnostics(window)
    assert "allowed_fast_set_size: 0" in session_text
    assert "payload.bin" in session_text

    status = window._status_summary_label.text()
    assert "Port" in status or "포트" in status
    assert window.actions["diagnostics"].shortcut().toString() == "Ctrl+D"

    # Properties/diagnostics dialogs build and refresh.
    debug_ui.PropertiesDialog(window, task_id).refresh()
    debug_ui.SessionDiagnosticsDialog(window).refresh()
    window.timer.stop()


def test_seeder_preference_redials_dropped_outgoing_seeds(qapp, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMainWindow

    QSettings().setValue("network/seeder_preference", True)
    seed_out = lt.peer_info.seed | lt.peer_info.outgoing_connection
    handle = _FakeHandle(
        [
            _FakePeer(("1.1.1.1", 6881), seed_out),
            _FakePeer(("2.2.2.2", 5000), lt.peer_info.seed),  # incoming: port unknown
        ]
    )
    task = type("T", (), {"handle": handle, "paused": False})()
    engine = type(
        "E", (), {"tasks": {"t1": task}, "_state_name": staticmethod(lambda s: "DOWNLOADING")}
    )()
    window = QMainWindow()
    window.engine = engine

    desktop_experience._install_seeder_preference(window)
    window._seeder_preference_timer.timeout.emit()
    assert list(window._seeder_preference_known_seeds["t1"]) == ["('1.1.1.1', 6881)"]
    assert handle.dialed == []

    handle.peers = handle.peers[1:]
    clock = desktop_experience.time.monotonic
    monkeypatch.setattr(desktop_experience.time, "monotonic", lambda: clock() + 61)
    window._seeder_preference_timer.timeout.emit()
    assert handle.dialed == [("1.1.1.1", 6881)]
