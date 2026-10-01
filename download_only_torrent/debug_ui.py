from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta

import libtorrent as lt
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QAction, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from . import ui
from .utils import format_bytes, format_rate


TEXT = {
    "en": {
        "pause": "Pause",
        "resume": "Resume",
        "remove": "Remove",
        "properties": "Properties",
        "properties_title": "Torrent properties / diagnostics",
        "diagnostics_title": "Session diagnostics (all torrents)",
        "refresh": "Refresh",
        "copy": "Copy",
        "auto_refresh": "Auto refresh",
    },
    "ko": {
        "pause": "일시정지",
        "resume": "재개",
        "remove": "제거",
        "properties": "속성",
        "properties_title": "토렌트 속성 / 진단 정보",
        "diagnostics_title": "전체 진단 정보 (모든 토렌트)",
        "refresh": "새로고침",
        "copy": "복사",
        "auto_refresh": "자동 새로고침",
    },
}

ui.TEXT["en"]["diagnostics"] = "Diagnostics"
ui.TEXT["ko"]["diagnostics"] = "진단"

_LOG_LIMIT = 3000
_TORRENT_LOG_LINES = 150
_SESSION_LOG_LINES = 300
_PEER_LIST_LIMIT = 200

# Alerts that are only counted. They arrive in bulk (one per peer connection or
# per tracker endpoint) and would push every useful line out of the log.
_COUNTED_ONLY = {
    "peer_connect",
    "incoming_connection",
    "peer_snubbed",
    "peer_unsnubbed",
    "invalid_request",
    "lsd_peer",
    "tracker_announce",
    "tracker_reply",
    "tracker_error",
    "tracker_warning",
    "scrape_reply",
    "scrape_failed",
    "dht_reply",
    "block_timeout",
    "unwanted_block",
}

# libtorrent's peer_source_flags_t::incoming has no Python attribute.
_SOURCE_INCOMING = 0x20


def _t(lang: str, key: str) -> str:
    return TEXT.get(lang, TEXT["en"]).get(key, key)


def _safe(getter, default="-"):
    try:
        value = getter()
        return default if value is None else value
    except Exception:
        return default


def _status_value(status, name: str, default="-"):
    try:
        value = getattr(status, name)
        return default if value is None else value
    except Exception:
        return default


def _fmt_duration(value) -> str:
    try:
        if hasattr(value, "total_seconds"):
            seconds = int(value.total_seconds())
        else:
            seconds = int(value)
        return str(timedelta(seconds=max(0, seconds)))
    except Exception:
        return str(value)


def _alert_mask() -> int:
    mask = 0
    for name in (
        "error",
        "peer",
        "connect",
        "performance_warning",
        "port_mapping",
        "status",
        "storage",
        "tracker",
        "ip_block",
    ):
        value = getattr(lt.alert_category, name, None)
        if value is not None:
            mask |= int(value)
    return mask


def _torrent_key(handle) -> str | None:
    if handle is None:
        return None
    key = None
    try:
        key = str(handle.info_hashes().v1)
    except Exception:
        try:
            key = str(handle.info_hash())
        except Exception:
            return None
    # Alerts for a torrent that was just removed carry an invalid handle.
    return None if not key or not key.strip("0") else key


_NETDB_ERRORS = {
    1: "host not found",
    2: "host not found (try again)",
    3: "DNS server failure",
    4: "no address for host",
}


def _error_text(value: int, category: str) -> str:
    if category == "asio.netdb" and int(value) in _NETDB_ERRORS:
        return _NETDB_ERRORS[int(value)]
    getter = getattr(lt, f"{category}_category", None)
    if getter is not None:
        try:
            code = lt.error_code()
            code.assign(int(value), getter())
            return code.message()
        except Exception:
            pass
    return f"{category}:{value}"


def _has_flag(flags, flag) -> bool:
    try:
        return bool(flags & flag)
    except Exception:
        try:
            return bool(int(flags) & int(flag))
        except Exception:
            return False


def _peer_flag(peer, name: str) -> bool:
    flag = getattr(lt.peer_info, name, None)
    return flag is not None and _has_flag(getattr(peer, "flags", 0), flag)


def _format_endpoint(endpoint) -> str:
    try:
        host, port = endpoint[0], endpoint[1]
    except Exception:
        return str(endpoint)
    host = str(host)
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _peer_client(peer) -> str:
    client = getattr(peer, "client", "")
    if isinstance(client, bytes):
        client = client.decode("utf-8", errors="replace")
    client = str(client).strip() or "?"
    return client[:22]


def _peer_flags(peer) -> str:
    letters = (
        ("seed", "S"),
        ("remote_choked", "C"),
        ("interesting", "I"),
        ("remote_interested", "i"),
        ("outgoing_connection", "O"),
        ("snubbed", "s"),
        ("connecting", "c"),
        ("handshake", "h"),
    )
    text = "".join(
        letter if _peer_flag(peer, name) else "." for name, letter in letters
    )
    if _peer_flag(peer, "rc4_encrypted") or _peer_flag(peer, "plaintext_encrypted"):
        text += "E"
    else:
        text += "."
    return text


def _peer_sources(peer) -> str:
    source = getattr(peer, "source", 0)
    names = []
    for name, letter in (("tracker", "T"), ("dht", "D"), ("pex", "P"), ("lsd", "L")):
        flag = getattr(lt.peer_info, name, None)
        if flag is not None and _has_flag(source, flag):
            names.append(letter)
    if _has_flag(source, _SOURCE_INCOMING):
        names.append("in")
    return ",".join(names) or "-"


_PEER_LEGEND = (
    "flags: S=seed C=choking us I=we want their pieces i=they want ours "
    "O=we dialed s=snubbed c=connecting h=handshake E=encrypted | "
    "src: T=tracker D=DHT P=PEX L=LSD in=incoming"
)


def _peer_summary(peers: list) -> dict[str, int]:
    summary = Counter()
    for peer in peers:
        if _peer_flag(peer, "connecting") or _peer_flag(peer, "handshake"):
            summary["handshaking"] += 1
            continue
        summary["connected"] += 1
        seed = _peer_flag(peer, "seed")
        choking_us = _peer_flag(peer, "remote_choked")
        if seed:
            summary["seeds"] += 1
            if choking_us:
                summary["seeds_choking"] += 1
        if not choking_us:
            summary["unchoked_us"] += 1
        if int(getattr(peer, "payload_down_speed", 0)) > 0:
            summary["sending"] += 1
        if _peer_flag(peer, "interesting"):
            summary["interesting"] += 1
        if _peer_flag(peer, "outgoing_connection"):
            summary["outgoing"] += 1
        else:
            summary["incoming"] += 1
    return summary


def _format_peer_summary(summary: dict[str, int]) -> str:
    return (
        f"connected {summary['connected']} (+{summary['handshaking']} handshaking) | "
        f"seeds {summary['seeds']} (choking us {summary['seeds_choking']}) | "
        f"unchoked us {summary['unchoked_us']} | "
        f"sending now {summary['sending']} | "
        f"we're interested in {summary['interesting']} | "
        f"dialed out {summary['outgoing']} / incoming {summary['incoming']}"
    )


def _peer_lines(peers: list) -> list[str]:
    def sort_key(peer):
        return (
            -int(getattr(peer, "payload_down_speed", 0)),
            not _peer_flag(peer, "seed"),
            -int(getattr(peer, "total_download", 0)),
        )

    lines = [
        f"{'address':<46} {'client':<22} {'flags':<9} {'src':<8} "
        f"{'have':>6} {'down':>12} {'received':>11}"
    ]
    ordered = sorted(peers, key=sort_key)
    for peer in ordered[:_PEER_LIST_LIMIT]:
        progress = float(getattr(peer, "progress", 0.0)) * 100.0
        lines.append(
            f"{_format_endpoint(getattr(peer, 'ip', '?')):<46} "
            f"{_peer_client(peer):<22} "
            f"{_peer_flags(peer):<9} "
            f"{_peer_sources(peer):<8} "
            f"{progress:>5.1f}% "
            f"{format_rate(int(getattr(peer, 'payload_down_speed', 0))):>12} "
            f"{format_bytes(int(getattr(peer, 'total_download', 0))):>11}"
        )
    if len(ordered) > _PEER_LIST_LIMIT:
        lines.append(f"... {len(ordered) - _PEER_LIST_LIMIT} more")
    return lines


def _tracker_lines(handle) -> list[str]:
    trackers = _safe(lambda: handle.trackers(), [])
    if not trackers:
        return ["(none)"]

    lines = []
    for index, tracker in enumerate(trackers, 1):
        if not isinstance(tracker, dict):
            lines.append(f"{index}. {getattr(tracker, 'url', tracker)}")
            continue

        url = tracker.get("url", "?")
        endpoints = tracker.get("endpoints") or []
        results = []
        for endpoint in endpoints:
            for info in endpoint.get("info_hashes") or []:
                if info.get("start_sent") or info.get("fails"):
                    results.append((endpoint.get("local_address"), info))

        working = [
            (address, info)
            for address, info in results
            if not info.get("fails")
            and int((info.get("last_error") or {}).get("value", 0)) == 0
        ]
        if working:
            address, info = working[0]
            seeds = info.get("scrape_complete", -1)
            leechers = info.get("scrape_incomplete", -1)
            status = (
                f"OK via {_format_endpoint(address)} | "
                f"seeds {seeds} leechers {leechers} | "
                f"working endpoints {len(working)}/{len(endpoints)}"
            )
        elif results:
            _, info = results[0]
            error = info.get("last_error") or {}
            message = info.get("message") or _error_text(
                error.get("value", 0), error.get("category", "system")
            )
            status = f"FAIL x{info.get('fails', 0)} | {message}"
        else:
            status = "not contacted yet"
        lines.append(f"{index}. [tier {tracker.get('tier', '?')}] {url}")
        lines.append(f"     {status}")
    return lines


class DiagnosticsLog:
    """Alerts captured from the shared libtorrent session.

    Bulky per-peer and per-tracker-endpoint alerts are only counted; tracker
    state is read from torrent_handle.trackers() instead.
    """

    def __init__(self):
        self.started = datetime.now()
        self.entries: deque[tuple[str, str | None, str, str]] = deque(
            maxlen=_LOG_LIMIT
        )
        self.disconnects: dict[str | None, Counter] = {}
        self.events: dict[str | None, Counter] = {}
        self.port_mappings: dict[str, str] = {}

    def add(self, alert) -> None:
        try:
            what = alert.what()
        except Exception:
            what = type(alert).__name__.replace("_alert", "")
        key = _torrent_key(getattr(alert, "handle", None))

        if what == "peer_disconnected":
            self.disconnects.setdefault(key, Counter())[
                self._disconnect_reason(alert)
            ] += 1
            return

        if what in _COUNTED_ONLY:
            self.events.setdefault(key, Counter())[what] += 1
            return

        try:
            message = alert.message()
        except Exception:
            message = str(alert)

        if what in ("portmap", "portmap_error"):
            label = f"{_safe(lambda: alert.map_type)} #{_safe(lambda: alert.mapping)}"
            self.port_mappings[label] = message

        name = str(_safe(lambda: alert.torrent_name, "") or "")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.entries.append((stamp, key, name, f"[{what}] {message}"))

    @staticmethod
    def _disconnect_reason(alert) -> str:
        reason = _safe(lambda: alert.error.message(), "?")
        operation = _safe(lambda: lt.operation_name(alert.op), "")
        return f"{reason} [{operation}]" if operation else str(reason)

    def lines(self, key: str | None, limit: int) -> list[str]:
        if key is None:
            selected = list(self.entries)
        else:
            selected = [entry for entry in self.entries if entry[1] == key]
        return [f"{stamp} {text}" for stamp, _, _, text in selected[-limit:]]

    def total(self, table: dict[str | None, Counter]) -> Counter:
        result = Counter()
        for counts in table.values():
            result.update(counts)
        return result


def _counter_lines(counts: Counter, limit: int = 15) -> list[str]:
    if not counts:
        return ["(none yet)"]
    return [f"{count:>6}  {name}" for name, count in counts.most_common(limit)]


def _log(window) -> DiagnosticsLog:
    log = getattr(window, "_diagnostics_log", None)
    if log is None:
        log = DiagnosticsLog()
        window._diagnostics_log = log
    return log


def torrent_diagnostics(window, task_id: str) -> str:
    engine = window.engine
    task = engine.tasks.get(task_id)
    if task is None:
        return "Torrent task no longer exists."

    handle = task.handle
    status = _safe(lambda: handle.status(), None)
    if status is None:
        return "Unable to read torrent status."

    log = _log(window)
    key = _torrent_key(handle)
    lines: list[str] = []
    add = lines.append

    add("[Task]")
    add(f"name: {task.name}")
    add(f"task_id: {task.task_id}")
    add(f"info_hash: {key or '-'}")
    add(f"save_path: {task.save_path}")
    add(f"source_torrent: {task.source_torrent_path or '-'}")
    add(f"magnet: {task.magnet_uri or '-'}")
    add(f"selected_files: {', '.join(map(str, task.selected_files))}")
    add(f"app_paused: {task.paused}")
    add("")

    add("[Torrent status]")
    for name in (
        "state",
        "paused",
        "auto_managed",
        "has_metadata",
        "is_seeding",
        "is_finished",
        "moving_storage",
        "announcing_to_trackers",
        "announcing_to_lsd",
        "announcing_to_dht",
        "num_peers",
        "num_seeds",
        "connect_candidates",
        "num_complete",
        "num_incomplete",
        "download_rate",
        "download_payload_rate",
        "upload_rate",
        "upload_payload_rate",
        "total_download",
        "total_payload_download",
        "total_upload",
        "total_payload_upload",
        "total_wanted",
        "total_wanted_done",
        "progress",
        "current_tracker",
    ):
        add(f"{name}: {_status_value(status, name)}")
    add(f"max_connections: {_safe(lambda: handle.max_connections())}")

    next_announce = _status_value(status, "next_announce", None)
    if next_announce is not None:
        add(f"next_announce: {_fmt_duration(next_announce)}")

    errc = _status_value(status, "errc", None)
    if errc not in (None, "-") and _safe(lambda: errc.value(), 0):
        add(f"error: {_safe(lambda: errc.message(), errc)}")
    add("")

    peers = list(_safe(lambda: handle.get_peer_info(), []))
    add("[Peers]")
    add(_format_peer_summary(_peer_summary(peers)))
    add(_PEER_LEGEND)
    lines.extend(_peer_lines(peers))
    add("")

    add(f"[Peer disconnect reasons since {log.started:%H:%M:%S}]")
    lines.extend(_counter_lines(log.disconnects.get(key, Counter())))
    add("")

    add("[Peer / tracker event counts]")
    lines.extend(_counter_lines(log.events.get(key, Counter())))
    add("")

    add("[Trackers]")
    lines.extend(_tracker_lines(handle))
    add("")

    add("[Recent alerts for this torrent]")
    lines.extend(log.lines(key, _TORRENT_LOG_LINES) or ["(none yet)"])
    add("")

    add("[Files]")
    for file in task.files:
        mark = "*" if file.index in task.selected_files else " "
        add(f"{mark} [{file.index}] {file.path} ({file.size} bytes)")

    return "\n".join(lines)


def session_diagnostics(window) -> str:
    engine = window.engine
    session = engine.session
    log = _log(window)
    lines: list[str] = []
    add = lines.append

    add("[Session]")
    add(f"captured since: {log.started:%Y-%m-%d %H:%M:%S}")
    add(f"is_listening: {_safe(lambda: session.is_listening())}")
    add(f"listen_port: {_safe(lambda: session.listen_port())}")
    settings = _safe(lambda: session.get_settings(), {})
    if isinstance(settings, dict):
        for name in (
            "listen_interfaces",
            "download_rate_limit",
            "upload_rate_limit",
            "connections_limit",
            "connection_speed",
            "num_want",
            "max_pex_peers",
            "peer_turnover",
            "peer_turnover_cutoff",
            "peer_turnover_interval",
            "unchoke_slots_limit",
            "allowed_fast_set_size",
            "enable_dht",
            "enable_lsd",
            "enable_upnp",
            "enable_natpmp",
            "enable_incoming_tcp",
            "enable_outgoing_tcp",
            "enable_incoming_utp",
            "enable_outgoing_utp",
            "peer_fingerprint",
            "user_agent",
        ):
            if name in settings:
                add(f"{name}: {settings[name]}")
    session_status = _safe(lambda: session.status(), None)
    if session_status is not None:
        for name in ("dht_nodes", "dht_node_cache", "num_peers"):
            if hasattr(session_status, name):
                add(f"session_{name}: {getattr(session_status, name)}")
    add("")

    add("[Port mapping (UPnP / NAT-PMP)]")
    if log.port_mappings:
        for label, message in sorted(log.port_mappings.items()):
            add(f"{label}: {message}")
    else:
        add("(no port mapping result yet)")
    events = log.total(log.events)
    add(f"incoming peer connections accepted: {events.get('incoming_connection', 0)}")
    add("")

    rows = []
    all_peers: list = []
    total_rate = 0
    for task in list(engine.tasks.values()):
        handle = task.handle
        status = _safe(lambda: handle.status(), None)
        if status is None:
            continue
        peers = list(_safe(lambda: handle.get_peer_info(), []))
        all_peers.extend(peers)
        summary = _peer_summary(peers)
        rate = int(_status_value(status, "download_payload_rate", 0) or 0)
        total_rate += rate
        state = "PAUSED" if task.paused else engine._state_name(status)
        rows.append(
            f"{task.name[:34]:<34} {state[:12]:<12} {format_rate(rate):>12} "
            f"{summary['connected']:>5} {summary['seeds']:>5} "
            f"{summary['seeds_choking']:>7} {summary['sending']:>7} "
            f"{_status_value(status, 'connect_candidates', 0):>6} "
            f"{float(_status_value(status, 'progress', 0) or 0) * 100:>6.1f}%"
        )

    add("[Totals]")
    add(f"torrents: {len(engine.tasks)} (+{len(engine.pending_magnets)} waiting for metadata)")
    add(f"download (payload): {format_rate(total_rate)}")
    add(_format_peer_summary(_peer_summary(all_peers)))
    add("")

    add("[Torrents]")
    add(
        f"{'name':<34} {'state':<12} {'down':>12} {'peers':>5} {'seeds':>5} "
        f"{'s-choke':>7} {'sending':>7} {'cands':>6} {'done':>7}"
    )
    lines.extend(rows or ["(none)"])
    add("")

    add("[Peer disconnect reasons, all torrents]")
    lines.extend(_counter_lines(log.total(log.disconnects)))
    add("")

    add("[Peer / tracker event counts, all torrents]")
    lines.extend(_counter_lines(events))
    add("")

    names = {}
    for task in engine.tasks.values():
        key = _torrent_key(task.handle)
        if key:
            names[key] = task.name[:24]
    add("[Recent alerts, all torrents]")
    recent = []
    for stamp, key, name, text in list(log.entries)[-_SESSION_LOG_LINES:]:
        label = names.get(key) or name[:24] or "session"
        recent.append(f"{stamp} <{label}> {text}")
    lines.extend(recent or ["(none yet)"])

    return "\n".join(lines)


class _DiagnosticsDialog(QDialog):
    def __init__(self, window, title: str, render):
        super().__init__(window)
        self.window = window
        self.render = render
        lang = window.config.language
        self.setWindowTitle(title)
        self.resize(1040, 720)

        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        layout.addWidget(self.text, 1)

        row = QHBoxLayout()
        refresh = QPushButton(_t(lang, "refresh"))
        copy = QPushButton(_t(lang, "copy"))
        self.auto_refresh = QCheckBox(_t(lang, "auto_refresh"))
        self.auto_refresh.setChecked(True)
        refresh.clicked.connect(self.refresh)
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.text.toPlainText()
            )
        )
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addWidget(self.auto_refresh)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._auto_refresh)
        self.timer.start()
        self.refresh()

    def _auto_refresh(self) -> None:
        # Replacing the text drops any selection, so hold still while the user
        # is selecting something to copy.
        if self.auto_refresh.isChecked() and not self.text.textCursor().hasSelection():
            self.refresh()

    def refresh(self) -> None:
        vertical = self.text.verticalScrollBar()
        horizontal = self.text.horizontalScrollBar()
        position = (vertical.value(), horizontal.value())
        self.text.setPlainText(self.render())
        vertical.setValue(position[0])
        horizontal.setValue(position[1])


class PropertiesDialog(_DiagnosticsDialog):
    def __init__(self, window, task_id: str):
        self.task_id = task_id
        super().__init__(
            window,
            _t(window.config.language, "properties_title"),
            lambda: torrent_diagnostics(window, task_id),
        )


class SessionDiagnosticsDialog(_DiagnosticsDialog):
    def __init__(self, window):
        super().__init__(
            window,
            _t(window.config.language, "diagnostics_title"),
            lambda: session_diagnostics(window),
        )


def _install_alert_capture(window) -> None:
    log = _log(window)
    try:
        window.engine.session.apply_settings(
            {"alert_mask": _alert_mask(), "alert_queue_size": 5000}
        )
    except Exception:
        pass

    def collect_alerts() -> None:
        try:
            alerts = window.engine.session.pop_alerts()
        except Exception:
            return
        for alert in alerts:
            try:
                log.add(alert)
            except Exception:
                continue

    window._torrent_alert_timer = QTimer(window)
    window._torrent_alert_timer.setInterval(500)
    window._torrent_alert_timer.timeout.connect(collect_alerts)
    window._torrent_alert_timer.start()


def _install_diagnostics_action(window) -> None:
    action = QAction(window)
    action.setShortcut(QKeySequence("Ctrl+D"))
    action.triggered.connect(lambda: SessionDiagnosticsDialog(window).exec())
    action.setText(ui.tr(window.config.language, "diagnostics"))
    window.toolbar.addAction(action)
    window.addAction(action)
    window.actions["diagnostics"] = action


def install_debug_ui(window) -> None:
    """Install compact context menu, session diagnostics and alert capture."""

    _install_alert_capture(window)
    _install_diagnostics_action(window)

    try:
        window.table.customContextMenuRequested.disconnect()
    except Exception:
        pass

    def show_menu(pos: QPoint) -> None:
        row = window.table.indexAt(pos).row()
        task_id = window._task_id_at_row(row)
        if not task_id:
            return

        window.table.selectRow(row)
        lang = window.config.language
        menu = QMenu(window)
        menu.setStyleSheet(
            "QMenu { padding: 3px; }"
            "QMenu::item { padding: 6px 16px 6px 10px; margin: 0px; }"
            "QMenu::separator { height: 1px; margin: 3px 6px; }"
            "QMenu::indicator { width: 0px; height: 0px; }"
        )

        pause_action = menu.addAction(_t(lang, "pause"))
        resume_action = menu.addAction(_t(lang, "resume"))
        remove_action = menu.addAction(_t(lang, "remove"))
        menu.addSeparator()
        properties_action = menu.addAction(_t(lang, "properties"))

        paused = window.engine.is_paused(task_id)
        pause_action.setEnabled(not paused)
        resume_action.setEnabled(paused)

        chosen = menu.exec(window.table.viewport().mapToGlobal(pos))
        if chosen is pause_action:
            window.engine.pause(task_id)
        elif chosen is resume_action:
            window.engine.resume(task_id)
        elif chosen is remove_action:
            window.engine.remove(task_id)
            window._remove_row(task_id)
        elif chosen is properties_action:
            PropertiesDialog(window, task_id).exec()

    window.table.customContextMenuRequested.connect(show_menu)
