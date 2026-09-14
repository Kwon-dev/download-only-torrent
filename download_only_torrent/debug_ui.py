from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


TEXT = {
    "en": {
        "pause": "Pause",
        "resume": "Resume",
        "remove": "Remove",
        "properties": "Properties",
        "properties_title": "Torrent properties / diagnostics",
        "refresh": "Refresh",
        "copy": "Copy",
    },
    "ko": {
        "pause": "일시정지",
        "resume": "재개",
        "remove": "제거",
        "properties": "속성",
        "properties_title": "토렌트 속성 / 진단 정보",
        "refresh": "새로고침",
        "copy": "복사",
    },
}


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


def torrent_diagnostics(window, task_id: str) -> str:
    engine = window.engine
    task = engine.tasks.get(task_id)
    if task is None:
        return "Torrent task no longer exists."

    handle = task.handle
    status = _safe(lambda: handle.status(), None)
    if status is None:
        return "Unable to read torrent status."

    lines: list[str] = []
    add = lines.append

    add("[Task]")
    add(f"name: {task.name}")
    add(f"task_id: {task.task_id}")
    add(f"save_path: {task.save_path}")
    add(f"source_torrent: {task.source_torrent_path or '-'}")
    add(f"magnet: {task.magnet_uri or '-'}")
    add(f"selected_files: {', '.join(map(str, task.selected_files))}")
    add(f"app_paused: {task.paused}")
    add("")

    add("[Torrent status]")
    for key in (
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
        add(f"{key}: {_status_value(status, key)}")

    next_announce = _status_value(status, "next_announce", None)
    if next_announce is not None:
        add(f"next_announce: {_fmt_duration(next_announce)}")

    errc = _status_value(status, "errc", None)
    if errc not in (None, "-", 0, "Success"):
        add(f"error_code: {errc}")
    add("")

    add("[Session]")
    add(f"is_listening: {_safe(lambda: engine.session.is_listening())}")
    add(f"listen_port: {_safe(lambda: engine.session.listen_port())}")
    settings = _safe(lambda: engine.session.get_settings(), {})
    if isinstance(settings, dict):
        for key in (
            "listen_interfaces",
            "enable_dht",
            "enable_lsd",
            "enable_incoming_tcp",
            "enable_outgoing_tcp",
            "enable_incoming_utp",
            "enable_outgoing_utp",
            "connections_limit",
            "unchoke_slots_limit",
            "choking_algorithm",
        ):
            if key in settings:
                add(f"{key}: {settings[key]}")

    session_status = _safe(lambda: engine.session.status(), None)
    if session_status is not None:
        for key in ("dht_nodes", "dht_node_cache", "num_peers"):
            if hasattr(session_status, key):
                add(f"session_{key}: {getattr(session_status, key)}")
    add("")

    add("[Trackers]")
    trackers = _safe(lambda: handle.trackers(), [])
    if trackers:
        for index, tracker in enumerate(trackers, 1):
            url = getattr(tracker, "url", str(tracker))
            add(f"{index}. {url}")
    else:
        add("(none)")
    add("")

    add("[Recent libtorrent alerts]")
    alerts = getattr(window, "_torrent_debug_alerts", [])
    if alerts:
        for item in alerts[-80:]:
            add(item)
    else:
        add("(no alerts captured yet)")
    add("")

    add("[Files]")
    for file in task.files:
        mark = "*" if file.index in task.selected_files else " "
        add(f"{mark} [{file.index}] {file.path} ({file.size} bytes)")

    return "\n".join(lines)


class PropertiesDialog(QDialog):
    def __init__(self, window, task_id: str):
        super().__init__(window)
        self.window = window
        self.task_id = task_id
        lang = window.config.language
        self.setWindowTitle(_t(lang, "properties_title"))
        self.resize(820, 680)

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
        refresh.clicked.connect(self.refresh)
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.text.toPlainText()
            )
        )
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        self.text.setPlainText(torrent_diagnostics(self.window, self.task_id))


def install_debug_ui(window) -> None:
    """Install compact context menu and continuously capture libtorrent alerts."""

    window._torrent_debug_alerts = []

    def collect_alerts() -> None:
        try:
            alerts = window.engine.session.pop_alerts()
        except Exception:
            return
        for alert in alerts:
            try:
                message = alert.message()
            except Exception:
                message = str(alert)
            stamp = datetime.now().strftime("%H:%M:%S")
            window._torrent_debug_alerts.append(f"{stamp} {message}")
        if len(window._torrent_debug_alerts) > 200:
            del window._torrent_debug_alerts[:-200]

    window._torrent_alert_timer = QTimer(window)
    window._torrent_alert_timer.setInterval(500)
    window._torrent_alert_timer.timeout.connect(collect_alerts)
    window._torrent_alert_timer.start()

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
