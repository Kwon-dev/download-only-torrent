from __future__ import annotations

import time
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import QEvent, QObject, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QFormLayout, QLabel

from .network_ui import _show_one_torrent_dialog
from .ui import SettingsDialog, TEXT
from .utils import format_rate


_CLOSE_TO_TRAY_KEY = "general/close_to_tray"
_LEGACY_MINIMIZE_TO_TRAY_KEY = "general/minimize_to_tray"
_LARGE_PEER_POOL_KEY = "network/large_peer_pool"
_SEEDER_PREFERENCE_KEY = "network/seeder_preference"

_LARGE_POOL_GLOBAL_CONNECTIONS = 1000
_LARGE_POOL_TORRENT_CONNECTIONS = 500
_LARGE_POOL_CONNECTION_SPEED = 80
_LARGE_POOL_NUM_WANT = 500
_LARGE_POOL_MAX_PEX_PEERS = 200

_SEEDER_PRUNE_INTERVAL_SECONDS = 30.0
_SEEDER_PRUNE_MIN_SEEDS = 2


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _setting_bool(key: str, default: bool = False) -> bool:
    return _as_bool(QSettings().value(key, default))


def install_engine_concurrency_fix(engine_cls) -> None:
    """Apply queue fixes and optional large-peer-pool tuning before restore."""

    if getattr(engine_cls, "_concurrency_fix_installed", False):
        return

    original_session_settings = engine_cls._session_settings
    original_kick_discovery = engine_cls._kick_discovery

    def session_settings(self):
        settings = original_session_settings(self)
        settings.update(
            {
                "active_downloads": -1,
                "active_seeds": -1,
                "active_checking": -1,
                "active_dht_limit": -1,
                "active_tracker_limit": -1,
                "active_lsd_limit": -1,
                "active_limit": -1,
            }
        )

        if _setting_bool(_LARGE_PEER_POOL_KEY):
            settings.update(
                {
                    "connections_limit": max(
                        _LARGE_POOL_GLOBAL_CONNECTIONS,
                        int(getattr(self.config, "max_connections", 200)),
                    ),
                    "connection_speed": _LARGE_POOL_CONNECTION_SPEED,
                    "num_want": _LARGE_POOL_NUM_WANT,
                    "max_pex_peers": _LARGE_POOL_MAX_PEX_PEERS,
                    # Rotate weak connections more often when the expanded pool
                    # is full, so the extra sockets are used for discovery rather
                    # than keeping dead/slow peers indefinitely.
                    "peer_turnover": 10,
                    "peer_turnover_cutoff": 80,
                    "peer_turnover_interval": 60,
                }
            )
        else:
            # Restore libtorrent defaults immediately when the option is turned
            # off; apply_settings() only changes keys that are present.
            settings.update(
                {
                    "connection_speed": 30,
                    "num_want": 200,
                    "max_pex_peers": 50,
                    "peer_turnover": 4,
                    "peer_turnover_cutoff": 90,
                    "peer_turnover_interval": 300,
                }
            )
        return settings

    def kick_discovery(self, handle):
        if _setting_bool(_LARGE_PEER_POOL_KEY):
            try:
                handle.set_max_connections(
                    max(
                        _LARGE_POOL_TORRENT_CONNECTIONS,
                        int(getattr(self.config, "max_connections", 200)),
                    )
                )
            except Exception:
                pass
        return original_kick_discovery(self, handle)

    engine_cls._session_settings = session_settings
    engine_cls._kick_discovery = kick_discovery
    engine_cls._concurrency_fix_installed = True


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


def _peer_strategy_strings(language: str) -> dict[str, str]:
    if language == "ko":
        return {
            "group": "피어 전략",
            "large_pool": "대형 피어 풀 사용 (실험적)",
            "large_tip": (
                "전체 연결 한도를 약 1000개, 토렌트당 약 500개까지 넓히고 "
                "피어 탐색/교체를 더 적극적으로 합니다. 공유기/NAT와 CPU 사용량이 "
                "늘어날 수 있습니다."
            ),
            "seeder": "시더 우선 연결 (실험적)",
            "seeder_tip": (
                "연결된 시더가 2개 이상 확인되면 주기적으로 비시더 연결을 정리하고 "
                "확인된 시더를 다시 연결합니다. 시더가 부족하면 다운로드 정지를 "
                "피하기 위해 일반 피어도 유지합니다."
            ),
        }
    return {
        "group": "Peer strategy",
        "large_pool": "Use large peer pool (experimental)",
        "large_tip": (
            "Raises the global pool to about 1000 peers and each torrent to about "
            "500, with more aggressive peer discovery/turnover. This can increase "
            "router/NAT, CPU and memory usage."
        ),
        "seeder": "Prefer seeders (experimental)",
        "seeder_tip": (
            "When at least two connected seeders are known, periodically clears "
            "non-seeder connections and reconnects the known seeders. Mixed peers "
            "are retained when too few seeders are available to avoid stalling."
        ),
    }


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

        labels = _peer_strategy_strings(config.language)
        self.large_peer_pool = QCheckBox(labels["large_pool"], self)
        self.large_peer_pool.setChecked(_setting_bool(_LARGE_PEER_POOL_KEY))
        self.large_peer_pool.setToolTip(labels["large_tip"])

        self.seeder_preference = QCheckBox(labels["seeder"], self)
        self.seeder_preference.setChecked(_setting_bool(_SEEDER_PREFERENCE_KEY))
        self.seeder_preference.setToolTip(labels["seeder_tip"])

        layout = self.layout()
        form = layout.itemAt(0).layout() if layout and layout.count() else None
        if isinstance(form, QFormLayout):
            form.addRow(labels["group"], self.large_peer_pool)
            form.addRow(labels["group"], self.seeder_preference)
        self.resize(max(self.width(), 540), max(self.height(), 650))

    def extended_apply(self):
        close_to_tray = self.minimize_tray.isChecked()
        large_peer_pool = self.large_peer_pool.isChecked()
        seeder_preference = self.seeder_preference.isChecked()

        # Let the original settings code run without re-enabling the legacy
        # minimize-to-tray behavior.
        self.minimize_tray.setChecked(False)
        original_apply(self)
        self.config.minimize_to_tray = False

        settings = QSettings()
        settings.setValue(_CLOSE_TO_TRAY_KEY, close_to_tray)
        settings.setValue(_LEGACY_MINIMIZE_TO_TRAY_KEY, False)
        settings.setValue(_LARGE_PEER_POOL_KEY, large_peer_pool)
        settings.setValue(_SEEDER_PREFERENCE_KEY, seeder_preference)
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


def _peer_is_seed(peer) -> bool:
    peer_type = getattr(lt, "peer_info", None)
    seed_flag = getattr(peer_type, "seed", None) if peer_type is not None else None
    flags = getattr(peer, "flags", None)
    if seed_flag is None or flags is None:
        return False
    try:
        return bool(flags & seed_flag)
    except Exception:
        try:
            return bool(int(flags) & int(seed_flag))
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
    """Periodically retain known seeders when the optional preference is enabled.

    libtorrent exposes peer classification and bulk peer-list clearing, but not a
    portable per-peer disconnect in the Python torrent_handle API. To avoid
    repeatedly tearing down good connections, this policy runs at most once per
    torrent every 30 seconds and only when at least two seeders are already known.
    """

    last_prune: dict[str, float] = {}

    def apply_preference() -> None:
        if not _setting_bool(_SEEDER_PREFERENCE_KEY):
            last_prune.clear()
            return

        now = time.monotonic()
        for task_id, task in list(window.engine.tasks.items()):
            if bool(getattr(task, "paused", False)):
                continue
            if now - last_prune.get(task_id, 0.0) < _SEEDER_PRUNE_INTERVAL_SECONDS:
                continue

            try:
                state = window.engine._state_name(task.handle.status())
                if "CHECKING" in state or state == "DOWNLOADING METADATA":
                    continue

                peers = list(task.handle.get_peer_info())
                seed_endpoints = []
                non_seed_count = 0
                seen = set()

                for peer in peers:
                    if _peer_is_seed(peer):
                        endpoint = _peer_endpoint(peer)
                        if endpoint is None:
                            continue
                        key = repr(endpoint)
                        if key not in seen:
                            seen.add(key)
                            seed_endpoints.append(endpoint)
                    else:
                        non_seed_count += 1

                if (
                    len(seed_endpoints) < _SEEDER_PRUNE_MIN_SEEDS
                    or non_seed_count == 0
                ):
                    continue

                task.handle.clear_peers()
                for endpoint in seed_endpoints:
                    try:
                        task.handle.connect_peer(endpoint)
                    except Exception:
                        pass
                task.handle.resume()
                window.engine._kick_discovery(task.handle)
                last_prune[task_id] = now
            except Exception:
                continue

        for task_id in list(last_prune):
            if task_id not in window.engine.tasks:
                last_prune.pop(task_id, None)

    timer = QTimer(window)
    timer.setInterval(5000)
    timer.timeout.connect(apply_preference)
    timer.start()
    window._seeder_preference_timer = timer
    window._seeder_preference_last_prune = last_prune


def _install_status_bar(window) -> None:
    status = window.statusBar()
    status.setSizeGripEnabled(False)
    label = QLabel(window)
    status.addWidget(label, 1)

    def update_status() -> None:
        active = 0
        checking_or_waiting = 0
        paused = 0
        peers = 0
        seeders = 0
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

        if window.config.language == "ko":
            text = (
                f"활성 다운로드 {active}/{total}   |   "
                f"합계 다운로드 {format_rate(total_rate)}   |   "
                f"피어 {peers} (시더 {seeders})   |   "
                f"검사/대기 {checking_or_waiting}"
            )
            if paused:
                text += f"   |   일시정지 {paused}"
            if _setting_bool(_LARGE_PEER_POOL_KEY):
                text += "   |   대형 피어 풀"
            if _setting_bool(_SEEDER_PREFERENCE_KEY):
                text += "   |   시더 우선"
        else:
            text = (
                f"Active downloads {active}/{total}   |   "
                f"Total down {format_rate(total_rate)}   |   "
                f"Peers {peers} (seeds {seeders})   |   "
                f"Checking/waiting {checking_or_waiting}"
            )
            if paused:
                text += f"   |   Paused {paused}"
            if _setting_bool(_LARGE_PEER_POOL_KEY):
                text += "   |   Large peer pool"
            if _setting_bool(_SEEDER_PREFERENCE_KEY):
                text += "   |   Seeder preference"

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


def install_desktop_experience(window) -> None:
    """Install drag/drop, tray behavior, peer options, and a live status bar."""

    _install_close_to_tray_settings()
    _close_to_tray_enabled(window.config)
    _install_drag_and_drop(window)
    _install_seeder_preference(window)
    _install_status_bar(window)
    _install_tray_quit(window)
