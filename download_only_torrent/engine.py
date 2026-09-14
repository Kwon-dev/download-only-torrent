from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import libtorrent as lt

from .config import AppConfig


@dataclass(slots=True)
class TorrentFile:
    index: int
    path: str
    size: int


@dataclass(slots=True)
class PendingMagnet:
    token: str
    uri: str
    save_path: str
    handle: object


@dataclass(slots=True)
class TorrentTask:
    task_id: str
    name: str
    handle: object
    selected_files: tuple[int, ...]
    files: tuple[TorrentFile, ...]
    save_path: str
    source_torrent_path: str | None
    initial_payload_upload: int = 0
    paused: bool = False


@dataclass(slots=True)
class TaskSnapshot:
    task_id: str
    name: str
    progress: float
    download_rate: int
    payload_uploaded: int
    peers: int
    state: str
    save_path: str
    completed: bool = False
    removed: bool = False
    error: str | None = None


class TorrentEngine:
    """libtorrent wrapper with a strict no-piece-upload policy.

    Protocol control traffic (tracker/DHT/handshake/ACKs) is still required for
    BitTorrent to work. The guard here concerns BitTorrent piece payload data.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.session = lt.session(self._session_settings())
        self.pending_magnets: dict[str, PendingMagnet] = {}
        self.tasks: dict[str, TorrentTask] = {}
        self._configure_local_peer_class()

    def _session_settings(self) -> dict:
        settings: dict[str, object] = {
            "enable_dht": self.config.enable_dht,
            "enable_lsd": self.config.enable_lsd,
            "enable_incoming_tcp": self.config.enable_tcp,
            "enable_outgoing_tcp": self.config.enable_tcp,
            "enable_incoming_utp": self.config.enable_utp,
            "enable_outgoing_utp": self.config.enable_utp,
            "connections_limit": max(2, self.config.max_connections),
            "unchoke_slots_limit": 0,
            "user_agent": "DownloadOnlyTorrent/0.1.0",
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
        }
        settings["download_rate_limit"] = self.config.download_limit_kib * 1024 if self.config.download_limit_kib > 0 else 0
        return settings

    def _configure_local_peer_class(self) -> None:
        try:
            local_id = lt.session.local_peer_class_id
            info = self.session.get_peer_class(local_id)
            info.ignore_unchoke_slots = False
            self.session.set_peer_class(local_id, info)
        except Exception:
            pass

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.session.apply_settings(self._session_settings())
        self._configure_local_peer_class()
        for task in self.tasks.values():
            try:
                task.handle.set_max_uploads(0)
                task.handle.set_max_connections(max(2, config.max_connections))
                self._apply_feature_flags(task.handle)
            except Exception:
                pass

    def preview_torrent(self, torrent_path: str) -> tuple[str, list[TorrentFile]]:
        ti = lt.torrent_info(torrent_path)
        return ti.name(), self._files_from_info(ti)

    def prepare_magnet(self, magnet_uri: str, save_path: str) -> str:
        params = lt.parse_magnet_uri(magnet_uri)
        params.save_path = save_path
        params.max_uploads = 0
        params.max_connections = max(2, self.config.max_connections)
        params.flags |= lt.torrent_flags.default_dont_download
        params.flags &= ~lt.torrent_flags.auto_managed
        params = self._apply_param_feature_flags(params)
        handle = self.session.add_torrent(params)
        handle.set_max_uploads(0)
        token = uuid.uuid4().hex
        self.pending_magnets[token] = PendingMagnet(token, magnet_uri, save_path, handle)
        return token

    def magnet_metadata(self, token: str) -> tuple[str, list[TorrentFile]] | None:
        pending = self.pending_magnets[token]
        status = pending.handle.status()
        if not status.has_metadata:
            return None
        ti = pending.handle.torrent_file()
        if ti is None:
            return None
        return ti.name(), self._files_from_info(ti)

    def cancel_pending_magnet(self, token: str) -> None:
        pending = self.pending_magnets.pop(token, None)
        if pending is not None:
            try:
                self.session.remove_torrent(pending.handle)
            except Exception:
                pass

    def start_magnet(self, token: str, selected_files: Iterable[int]) -> str:
        pending = self.pending_magnets.pop(token)
        ti = pending.handle.torrent_file()
        if ti is None:
            raise RuntimeError("Magnet metadata is not available yet.")
        files = self._files_from_info(ti)
        selected = self._normalize_selection(selected_files, len(files))
        pending.handle.prioritize_files([4 if i in selected else 0 for i in range(len(files))])
        pending.handle.set_max_uploads(0)
        self._apply_feature_flags(pending.handle)
        pending.handle.resume()
        return self._register_task(pending.handle, ti.name(), selected, files, pending.save_path, None)

    def add_torrent_file(self, torrent_path: str, save_path: str, selected_files: Iterable[int]) -> str:
        ti = lt.torrent_info(torrent_path)
        files = self._files_from_info(ti)
        selected = self._normalize_selection(selected_files, len(files))
        params = lt.add_torrent_params()
        params.ti = ti
        params.save_path = save_path
        params.max_uploads = 0
        params.max_connections = max(2, self.config.max_connections)
        params.file_priorities = [4 if i in selected else 0 for i in range(len(files))]
        params.flags |= lt.torrent_flags.default_dont_download
        params.flags &= ~lt.torrent_flags.auto_managed
        params = self._apply_param_feature_flags(params)
        handle = self.session.add_torrent(params)
        handle.set_max_uploads(0)
        self._apply_feature_flags(handle)
        return self._register_task(handle, ti.name(), selected, files, save_path, torrent_path)

    def pause(self, task_id: str) -> None:
        task = self.tasks[task_id]
        task.handle.pause()
        task.paused = True

    def resume(self, task_id: str) -> None:
        task = self.tasks[task_id]
        task.handle.set_max_uploads(0)
        task.handle.resume()
        task.paused = False

    def remove(self, task_id: str) -> None:
        task = self.tasks.pop(task_id, None)
        if task is None:
            return
        try:
            task.handle.pause()
            task.handle.clear_peers()
        except Exception:
            pass
        try:
            self.session.remove_torrent(task.handle)
        except Exception:
            pass

    def poll(self) -> list[TaskSnapshot]:
        snapshots: list[TaskSnapshot] = []
        for task_id, task in list(self.tasks.items()):
            try:
                status = task.handle.status()
                payload_uploaded = int(getattr(status, "total_payload_upload", 0))
                uploaded_delta = max(0, payload_uploaded - task.initial_payload_upload)
                progress = self._selected_progress(task)

                if uploaded_delta > 0:
                    snapshots.append(TaskSnapshot(task_id, task.name, progress, int(getattr(status, "download_payload_rate", 0)), uploaded_delta, int(getattr(status, "num_peers", 0)), "ABORTED", task.save_path, removed=True, error=f"Piece payload upload detected ({uploaded_delta} bytes). Torrent was stopped."))
                    self.remove(task_id)
                    continue

                if bool(getattr(status, "is_finished", False)) or progress >= 1.0:
                    snapshots.append(TaskSnapshot(task_id, task.name, 1.0, 0, 0, int(getattr(status, "num_peers", 0)), "COMPLETED", task.save_path, completed=True, removed=True))
                    self._finish_task(task_id)
                    continue

                snapshots.append(TaskSnapshot(task_id, task.name, progress, int(getattr(status, "download_payload_rate", 0)), uploaded_delta, int(getattr(status, "num_peers", 0)), "PAUSED" if task.paused else self._state_name(status), task.save_path))
            except Exception as exc:
                snapshots.append(TaskSnapshot(task_id, task.name, 0.0, 0, 0, 0, "ERROR", task.save_path, removed=True, error=str(exc)))
                self.remove(task_id)
        return snapshots

    def _register_task(self, handle: object, name: str, selected: tuple[int, ...], files: list[TorrentFile], save_path: str, source_torrent_path: str | None) -> str:
        status = handle.status()
        task_id = uuid.uuid4().hex
        self.tasks[task_id] = TorrentTask(task_id, name, handle, selected, tuple(files), save_path, source_torrent_path, int(getattr(status, "total_payload_upload", 0)))
        return task_id

    def _finish_task(self, task_id: str) -> None:
        task = self.tasks.pop(task_id, None)
        if task is None:
            return
        try:
            task.handle.pause()
            task.handle.clear_peers()
        except Exception:
            pass
        try:
            self.session.remove_torrent(task.handle)
        except Exception:
            pass
        if self.config.delete_torrent_source and task.source_torrent_path:
            try:
                source = Path(task.source_torrent_path)
                if source.is_file() and source.suffix.lower() == ".torrent":
                    source.unlink()
            except OSError:
                pass

    def _selected_progress(self, task: TorrentTask) -> float:
        progress = task.handle.file_progress()
        total = sum(task.files[i].size for i in task.selected_files)
        if total <= 0:
            return 1.0
        done = sum(min(int(progress[i]), task.files[i].size) for i in task.selected_files)
        return max(0.0, min(1.0, done / total))

    def _apply_param_feature_flags(self, params):
        if not self.config.enable_dht:
            params.flags |= lt.torrent_flags.disable_dht
        if not self.config.enable_lsd:
            params.flags |= lt.torrent_flags.disable_lsd
        if not self.config.enable_pex:
            params.flags |= lt.torrent_flags.disable_pex
        return params

    def _apply_feature_flags(self, handle: object) -> None:
        for allowed, flag in ((self.config.enable_dht, lt.torrent_flags.disable_dht), (self.config.enable_lsd, lt.torrent_flags.disable_lsd), (self.config.enable_pex, lt.torrent_flags.disable_pex)):
            if allowed:
                handle.unset_flags(flag)
            else:
                handle.set_flags(flag)
        handle.set_max_uploads(0)

    @staticmethod
    def _normalize_selection(selected_files: Iterable[int], count: int) -> tuple[int, ...]:
        selected = tuple(sorted({int(i) for i in selected_files if 0 <= int(i) < count}))
        if not selected:
            raise ValueError("Select at least one file to download.")
        return selected

    @staticmethod
    def _files_from_info(ti) -> list[TorrentFile]:
        storage = ti.files()
        return [TorrentFile(i, storage.file_path(i), int(storage.file_size(i))) for i in range(storage.num_files())]

    @staticmethod
    def _state_name(status) -> str:
        state = getattr(status, "state", None)
        name = getattr(state, "name", None)
        if name:
            return str(name).replace("_", " ").upper()
        return str(state).split(".")[-1].replace("_", " ").upper()
