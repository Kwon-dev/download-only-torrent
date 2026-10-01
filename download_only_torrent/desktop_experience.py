from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import QEvent, QObject, QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
)

from .network_ui import _show_one_torrent_dialog
from .peer_strategy import (
    LARGE_PEER_POOL_KEY as _LARGE_PEER_POOL_KEY,
    SEEDER_PREFERENCE_KEY as _SEEDER_PREFERENCE_KEY,
    as_bool as _as_bool,
    setting_bool as _setting_bool,
)
from .ui import SettingsDialog, TEXT
from .utils import format_rate


_CLOSE_TO_TRAY_KEY = "general/close_to_tray"
_LEGACY_MINIMIZE_TO_TRAY_KEY = "general/minimize_to_tray"
_SEEDER_RECONNECT_INTERVAL_SECONDS = 60.0
_SEEDER_MEMORY_SECONDS = 15 * 60.0
_SEEDER_MEMORY_MAX = 200


def _close_to_tray_enabled(config=None) -> bool:
    settings = QSettings()
    if settings.contains(_CLOSE_TO_TRAY_KEY):
        enabled = _as_bool(settings.value(_CLOSE_TO_TRAY_KEY, True))
    else:
        legacy = bool(getattr(config, "minimize_to_tray", True))
        enabled = _as_bool(settings.value(_LEGACY_MINIMIZE_TO_TRAY_KEY, legacy))
        settings.setValue(_CLOSE_TO_TRAY_KEY, enabled)

    # The old setting must stay disabled because MainWindow.changeEvent() uses it
    # to hide the window on minimize. It is retained only as a migration source.
    if config is not None:
        config.minimize_to_tray = False
    settings.setValue(_LEGACY_MINIMIZE_TO_TRAY_KEY, False)
    settings.sync()
    return enabled


def _install_close_to_tray_settings() -> None:
    if getattr(SettingsDialog, "_close_to_tray_extended", False):
        return

    TEXT["en"]["minimize_tray"] = "Close to system tray"
    TEXT["ko"]["minimize_tray"] = "닫기 시 시스템 트레이로 이동"

    original_init = SettingsDialog.__init__
    original_apply = SettingsDialog.apply

    def extended_init(self, config, parent=None):
        original_init(self, config, parent)
        self.minimize_tray.setChecked(_close_to_tray_enabled(config))

    def extended_apply(self):
        close_to_tray = self.minimize_tray.isChecked()

        # Let the original settings code run without re-enabling the legacy
        # minimize-to-tray behavior.
        self.minimize_tray.setChecked(False)
        original_apply(self)
        self.config.minimize_to_tray = False

        settings = QSettings()
        settings.setValue(_CLOSE_TO_TRAY_KEY, close_to_tray)
        settings.setValue(_LEGACY_MINIMIZE_TO_TRAY_KEY, False)
        settings.sync()
        self.minimize_tray.setChecked(close_to_tray)

    SettingsDialog.__init__ = extended_init
    SettingsDialog.apply = extended_apply
    SettingsDialog._close_to_tray_extended = True


def _dropped_torrent_paths(event) -> list[str]:
    mime = event.mimeData()
    if mime is None or not mime.hasUrls():
        return []

    result: list[str] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        try:
            candidate = Path(path)
        except Exception:
            continue
        if candidate.suffix.lower() == ".torrent" and candidate.is_file():
            result.append(str(candidate))
    return result


class _DesktopEventFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()

        if event_type == QEvent.Type.DragEnter:
            if _dropped_torrent_paths(event):
                event.acceptProposedAction()
                return True

        if event_type == QEvent.Type.Drop:
            paths = _dropped_torrent_paths(event)
            if paths:
                event.acceptProposedAction()
                for path in paths:
                    _show_one_torrent_dialog(self.window, path)
                return True

        if (
            watched is self.window
            and event_type == QEvent.Type.Close
            and not getattr(self.window, "_desktop_allow_quit", False)
            and _close_to_tray_enabled(self.window.config)
        ):
            event.ignore()
            self.window.hide()
            self.window.tray.show()
            return True

        return super().eventFilter(watched, event)


def _install_drag_and_drop(window) -> None:
    window.setAcceptDrops(True)
    targets = [window]
    try:
        viewport = window.table.viewport()
        viewport.setAcceptDrops(True)
        targets.append(viewport)
    except Exception:
        pass

    event_filter = _DesktopEventFilter(window)
    for target in targets:
        target.installEventFilter(event_filter)
    window._desktop_event_filter = event_filter


def _peer_has_flag(peer, name: str) -> bool:
    peer_type = getattr(lt, "peer_info", None)
    flag = getattr(peer_type, name, None) if peer_type is not None else None
    flags = getattr(peer, "flags", None)
    if flag is None or flags is None:
        return False
    try:
        return bool(flags & flag)
    except Exception:
        try:
            return bool(int(flags) & int(flag))
        except Exception:
            return False


def _peer_endpoint(peer):
    for name in ("ip", "remote_endpoint"):
        value = getattr(peer, name, None)
        if value is None:
            continue
        try:
            value = value() if callable(value) else value
        except Exception:
            continue
        if value:
            return value
    return None


def _install_seeder_preference(window) -> None:
    """Reconnect seeders that dropped while the optional preference is enabled.

    Freeing slots for seeders is left to libtorrent's peer turnover (see
    peer_strategy.turnover_profile), which disconnects a few of the least useful peers at a
    time and only when replacement candidates exist. This timer only adds
    connections: it remembers seeders we dialed ourselves (their port is their
    listen port, so they can be dialed again) and reconnects them while the
    torrent has free slots. It never clears the peer list, so it does not undo
    the large peer pool's discovery work.
    """

    # task_id -> {endpoint key: (endpoint, last seen as connected seed)}
    known_seeds: dict[str, dict[str, tuple[object, float]]] = {}
    last_reconnect: dict[str, float] = {}

    def apply_preference() -> None:
        if not _setting_bool(_SEEDER_PREFERENCE_KEY):
            known_seeds.clear()
            last_reconnect.clear()
            return

        now = time.monotonic()
        for task_id, task in list(window.engine.tasks.items()):
            if bool(getattr(task, "paused", False)):
                continue

            try:
                state = window.engine._state_name(task.handle.status())
                if "CHECKING" in state or state == "DOWNLOADING METADATA":
                    continue

                peers = list(task.handle.get_peer_info())
                connected = set()
                memory = known_seeds.setdefault(task_id, {})
                for peer in peers:
                    endpoint = _peer_endpoint(peer)
                    if endpoint is None:
                        continue
                    key = repr(endpoint)
                    connected.add(key)
                    if _peer_has_flag(peer, "seed") and _peer_has_flag(
                        peer, "outgoing_connection"
                    ):
                        memory[key] = (endpoint, now)

                for key, (_, seen) in list(memory.items()):
                    if now - seen > _SEEDER_MEMORY_SECONDS:
                        memory.pop(key, None)
                if len(memory) > _SEEDER_MEMORY_MAX:
                    newest = sorted(
                        memory.items(), key=lambda item: item[1][1], reverse=True
                    )
                    memory.clear()
                    memory.update(newest[:_SEEDER_MEMORY_MAX])

                if (
                    now - last_reconnect.get(task_id, 0.0)
                    < _SEEDER_RECONNECT_INTERVAL_SECONDS
                ):
                    continue
                last_reconnect[task_id] = now

                try:
                    free_slots = int(task.handle.max_connections()) - len(peers)
                except Exception:
                    free_slots = 0
                if free_slots <= 0:
                    continue

                missing = [
                    endpoint
                    for key, (endpoint, _) in memory.items()
                    if key not in connected
                ]
                for endpoint in missing[:free_slots]:
                    try:
                        task.handle.connect_peer(endpoint)
                    except Exception:
                        pass
            except Exception:
                continue

        for task_id in list(known_seeds):
            if task_id not in window.engine.tasks:
                known_seeds.pop(task_id, None)
                last_reconnect.pop(task_id, None)

    timer = QTimer(window)
    timer.setInterval(5000)
    timer.timeout.connect(apply_preference)
    timer.start()
    window._seeder_preference_timer = timer
    window._seeder_preference_known_seeds = known_seeds


# After this long without an incoming connection or a router mapping, the
# listen port is most likely not reachable from the internet.
_PORT_VERDICT_SECONDS = 180.0


def _port_status(window, language: str) -> str:
    """Short reachability summary: incoming peers prove the port is open."""

    log = getattr(window, "_diagnostics_log", None)
    try:
        port = int(window.engine.session.listen_port())
    except Exception:
        port = 0
    incoming = log.incoming_connections() if log is not None else 0
    mapped = bool(getattr(log, "port_mapped", False))
    started = getattr(log, "started", None)
    elapsed = (datetime.now() - started).total_seconds() if started else 0.0

    if incoming:
        return (
            f"포트 {port} 열림 (수신 {incoming})"
            if language == "ko"
            else f"Port {port} open ({incoming} incoming)"
        )
    if mapped:
        return (
            f"포트 {port} UPnP 연결됨, 수신 대기"
            if language == "ko"
            else f"Port {port} mapped by UPnP, no incoming yet"
        )
    if elapsed >= _PORT_VERDICT_SECONDS:
        return (
            f"포트 {port} 닫힘? (수신 0, 포트포워딩 확인)"
            if language == "ko"
            else f"Port {port} closed? (0 incoming, check forwarding)"
        )
    return f"포트 {port} 확인 중" if language == "ko" else f"Port {port} checking"


class RateMeter:
    """Average download payload rate since the app started.

    Integrates the sampled total rate, so torrents that finish and leave the
    session still count toward the average.
    """

    def __init__(self):
        self.started = time.monotonic()
        self.total_bytes = 0.0
        self._last_sample: float | None = None

    def sample(self, rate: int) -> None:
        now = time.monotonic()
        if self._last_sample is not None:
            self.total_bytes += max(0, rate) * (now - self._last_sample)
        self._last_sample = now

    @property
    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    @property
    def average(self) -> float:
        elapsed = self.elapsed
        return self.total_bytes / elapsed if elapsed > 0 else 0.0


def _install_status_bar(window) -> None:
    status = window.statusBar()
    status.setSizeGripEnabled(False)
    label = QLabel(window)
    status.addWidget(label, 1)
    meter = RateMeter()
    window._rate_meter = meter

    def update_status() -> None:
        active = 0
        checking_or_waiting = 0
        paused = 0
        peers = 0
        seeders = 0
        half_open = 0
        total_rate = 0

        tasks = list(window.engine.tasks.values())
        for task in tasks:
            try:
                torrent_status = task.handle.status()
            except Exception:
                continue

            total_rate += int(
                getattr(torrent_status, "download_payload_rate", 0)
            )
            peers += int(getattr(torrent_status, "num_peers", 0))
            seeders += max(0, int(getattr(torrent_status, "num_seeds", 0)))
            # num_connections includes connections still being set up.
            half_open += max(
                0,
                int(getattr(torrent_status, "num_connections", 0))
                - int(getattr(torrent_status, "num_peers", 0)),
            )

            if bool(getattr(task, "paused", False)):
                paused += 1
                continue

            state = window.engine._state_name(torrent_status)
            if state == "DOWNLOADING":
                active += 1
            elif "CHECKING" in state or state == "DOWNLOADING METADATA":
                checking_or_waiting += 1

        pending = len(window.engine.pending_magnets)
        checking_or_waiting += pending
        total = len(tasks) + pending
        meter.sample(total_rate)
        average = format_rate(int(meter.average))

        if window.config.language == "ko":
            text = (
                f"활성 다운로드 {active}/{total}   |   "
                f"합계 다운로드 {format_rate(total_rate)} (평균 {average})   |   "
                f"피어 {peers} (시더 {seeders}, 연결 시도 {half_open})   |   "
                f"검사/대기 {checking_or_waiting}"
            )
            if paused:
                text += f"   |   일시정지 {paused}"
            if _setting_bool(_LARGE_PEER_POOL_KEY):
                text += "   |   대형 피어 풀"
            if _setting_bool(_SEEDER_PREFERENCE_KEY):
                text += "   |   시더 우선"
            text += "   |   " + _port_status(window, "ko")
        else:
            text = (
                f"Active downloads {active}/{total}   |   "
                f"Total down {format_rate(total_rate)} (avg {average})   |   "
                f"Peers {peers} (seeds {seeders}, connecting {half_open})   |   "
                f"Checking/waiting {checking_or_waiting}"
            )
            if paused:
                text += f"   |   Paused {paused}"
            if _setting_bool(_LARGE_PEER_POOL_KEY):
                text += "   |   Large peer pool"
            if _setting_bool(_SEEDER_PREFERENCE_KEY):
                text += "   |   Seeder preference"
            text += "   |   " + _port_status(window, "en")

        label.setText(text)

    timer = QTimer(window)
    timer.setInterval(500)
    timer.timeout.connect(update_status)
    timer.start()
    update_status()

    window._status_summary_label = label
    window._status_summary_timer = timer


def _install_tray_quit(window) -> None:
    try:
        window.tray_quit.triggered.disconnect()
    except Exception:
        pass

    def quit_from_tray() -> None:
        window._desktop_allow_quit = True
        window.tray.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    window.tray_quit.triggered.connect(quit_from_tray)


def _warn_unrestored(window) -> None:
    entries = list(getattr(window.engine, "unrestored", []))
    if not entries:
        return
    sources = "\n".join(f"- {entry.get('source', '?')}" for entry in entries[:20])
    if len(entries) > 20:
        sources += f"\n... (+{len(entries) - 20})"
    if window.config.language == "ko":
        title = "일부 다운로드를 복원하지 못함"
        text = (
            f"저장된 다운로드 {len(entries)}개를 복원하지 못했습니다. "
            "원본 .torrent 파일이 없어진 경우가 대부분입니다.\n\n"
            f"{sources}\n\n"
            "항목을 유지하면, 같은 경로에 파일을 되돌려 놓고 앱을 다시 "
            "시작했을 때 복원됩니다."
        )
        keep_text, drop_text = "유지", "목록에서 삭제"
    else:
        title = "Some downloads could not be restored"
        text = (
            f"{len(entries)} saved download(s) could not be restored, usually "
            "because the original .torrent file is gone.\n\n"
            f"{sources}\n\n"
            "If you keep them, putting the file back at the same path and "
            "restarting the app restores them."
        )
        keep_text, drop_text = "Keep", "Remove from list"

    box = QMessageBox(window)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton(keep_text, QMessageBox.ButtonRole.AcceptRole)
    drop = box.addButton(drop_text, QMessageBox.ButtonRole.DestructiveRole)
    box.exec()
    if box.clickedButton() is drop:
        window.engine.unrestored.clear()
        window.engine._persist_tasks()


def install_desktop_experience(window) -> None:
    """Install drag/drop, tray behavior, peer options, and a live status bar."""

    _install_close_to_tray_settings()
    _close_to_tray_enabled(window.config)
    _install_drag_and_drop(window)
    _install_seeder_preference(window)
    _install_status_bar(window)
    _install_tray_quit(window)
    QTimer.singleShot(0, lambda: _warn_unrestored(window))
