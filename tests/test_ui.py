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
        dialog.ipv6,
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
    dialog.ipv6.setChecked(False)
    dialog.max_out_request_queue.setValue(2000)
    dialog.peer_connect_timeout.setValue(5)
    dialog.apply()
    window.engine.apply_config(window.config)

    assert peer_strategy.large_pool_enabled() and peer_strategy.seeder_preference_enabled()
    assert port_config.bind_default_interface_enabled() is False
    assert port_config.ipv6_enabled() is False
    assert QSettings().value("network/max_out_request_queue") in (2000, "2000")
    applied = window.engine.session.get_settings()
    assert applied["max_out_request_queue"] == 2000
    assert applied["peer_connect_timeout"] == 5
    assert applied["peer_turnover_interval"] == 120


def test_peer_panel_lists_peers_of_selected_download(qapp, tmp_path, seeder):
    from download_only_torrent import peer_panel

    content, torrent = make_torrent(tmp_path / "seed", "panel.bin", 4 * 1024 * 1024)
    seeder.seed(content, torrent)
    path = tmp_path / "panel.torrent"
    path.write_bytes(torrent)

    window = app_module.build_main_window(qapp)
    window.config.language = "en"
    window.show()
    panel = window._peer_panel
    assert window.centralWidget() is window._peer_splitter
    assert window._peer_splitter.widget(0) is window.table

    # Nothing selected yet.
    panel.refresh()
    assert panel.table.rowCount() == 0

    task_id = window.engine.add_torrent_file(str(path), str(tmp_path / "dl"), [0])
    window.engine.tasks[task_id].handle.connect_peer(seeder.endpoint)

    address = f"127.0.0.1:{seeder.endpoint[1]}"
    deadline = time.monotonic() + 20
    rows = {}
    while time.monotonic() < deadline:
        spin_qt(200)
        row = window.rows.get(task_id)
        if row is not None:
            window.table.selectRow(row)
        panel.refresh()
        rows = {
            panel.table.item(r, 0).text(): [
                panel.table.item(r, c).text() for c in range(panel.table.columnCount())
            ]
            for r in range(panel.table.rowCount())
        }
        if address in rows and rows[address][2] == "Receiving":
            break

    assert address in rows, rows
    cells = rows[address]
    assert cells[1].startswith("libtorrent")
    assert cells[2] == "Receiving"
    assert cells[3].startswith("S")
    assert cells[4] == "100.0%"
    assert "seeds 1, 0 choking us" in panel.summary.text()

    # Numeric columns sort by value, not text.
    small = peer_panel._SortItem("9.0 KiB/s", 9 * 1024)
    large = peer_panel._SortItem("10.0 MiB/s", 10 * 1024 * 1024)
    assert small < large
    window.timer.stop()
    window.hide()


def test_rate_meter_and_status_bar_show_average_and_connecting(qapp, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(desktop_experience.time, "monotonic", lambda: clock[0])
    meter = desktop_experience.RateMeter()
    meter.sample(0, active=True)
    clock[0] += 10
    meter.sample(1000, active=True)  # 1000 B/s for 10 s
    clock[0] += 10
    meter.sample(0, active=True)  # downloading, but stalled for 10 s
    clock[0] += 600
    meter.sample(0, active=False)  # idle: queue empty for 10 min
    assert meter.total_bytes == 10_000
    assert meter.active_seconds == 20
    # Idle time does not dilute the average.
    assert meter.average == 500

    monkeypatch.undo()
    window = app_module.build_main_window(qapp)
    window.config.language = "ko"
    window.timer.stop()
    spin_qt(700)
    text = window._status_summary_label.text()
    assert "평균" in text and "연결 시도" in text


def test_disconnect_causes_group_who_ended_the_connection():
    cause = debug_ui.disconnect_cause
    assert cause("system", 10054, "sock_read") == "remote"  # reset by peer
    assert cause("asio.misc", 2, "sock_read") == "remote"  # end of file
    assert cause("system", 10060, "sock_read") == "silent"
    assert cause("system", 110, "sock_read") == "silent"
    assert cause("system", 10060, "connect") == "dial"
    assert cause("libtorrent", 36, "connect") == "dial"  # our connect timeout
    assert cause("system", 10045, "sock_bind") == "dial"
    assert cause("libtorrent", 51, "bittorrent") == "handshake"
    assert cause("libtorrent", 97, "bittorrent") == "turnover"
    assert cause("libtorrent", 36, "bittorrent") == "local"

    # Every cause is always listed, turnover included, even at zero.
    from collections import Counter

    lines = debug_ui._cause_lines(Counter({"remote": 3, "dial": 1}))
    assert len(lines) == len(debug_ui.DISCONNECT_CAUSES)
    assert "75.0%" in lines[0] and "closed by the remote peer" in lines[0]
    assert lines[-1].split()[0] == "0" and "optimistic disconnect" in lines[-1]


def test_resume_saves_are_counted_not_logged():
    class _Alert:
        handle = None

        def what(self):
            return "save_resume_data"

        def message(self):
            return "resume data generated"

    log = debug_ui.DiagnosticsLog()
    log.add(_Alert())
    assert list(log.entries) == []
    assert log.total(log.events)["save_resume_data"] == 1
