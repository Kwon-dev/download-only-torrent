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
    # Only the local seeder may connect; the test must stay off the public DHT.
    assert engine.session.get_settings()["enable_dht"] is False
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


def _form_widgets(form) -> list:
    widgets = []
    for row in range(form.rowCount()):
        for role in (
            ui.QFormLayout.ItemRole.LabelRole,
            ui.QFormLayout.ItemRole.FieldRole,
            ui.QFormLayout.ItemRole.SpanningRole,
        ):
            item = form.itemAt(row, role)
            if item is not None and item.widget() is not None:
                widgets.append(item.widget())
    return widgets


def test_settings_dialog_splits_general_and_advanced(qapp):
    from PySide6.QtCore import QSettings

    from download_only_torrent import peer_strategy, port_config

    window = app_module.build_main_window(qapp)
    window.timer.stop()
    dialog = ui.SettingsDialog(window.config, window)
    assert dialog.tabs.count() == 2

    general = _form_widgets(dialog.general_form)
    advanced = _form_widgets(dialog.advanced_form)
    for widget in (dialog.download_dir.parent(), dialog.max_connections, dialog.theme):
        assert widget in general
    assert dialog.listen_port.parent() in general
    for widget in (
        dialog.large_peer_pool,
        dialog.seeder_preference,
        dialog.bind_default_interface,
        dialog.dht,
        dialog.utp,
        dialog.max_out_request_queue,
        dialog.peer_connect_timeout,
        dialog.add_extra_trackers,
        dialog.extra_trackers,
    ):
        assert widget in advanced
        assert widget not in general

    dialog.large_peer_pool.setChecked(True)
    dialog.seeder_preference.setChecked(True)
    dialog.bind_default_interface.setChecked(False)
    dialog.max_out_request_queue.setValue(2000)
    dialog.peer_connect_timeout.setValue(5)
    dialog.apply()
    window.engine.apply_config(window.config)

    assert peer_strategy.large_pool_enabled() and peer_strategy.seeder_preference_enabled()
    assert port_config.bind_default_interface_enabled() is False
    assert QSettings().value("network/max_out_request_queue") in (2000, "2000")
    applied = window.engine.session.get_settings()
    assert applied["max_out_request_queue"] == 2000
    assert applied["peer_connect_timeout"] == 5
    assert applied["peer_turnover"] == 15
