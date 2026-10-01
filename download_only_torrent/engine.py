from __future__ import annotations

import json
import os
import time
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
class RestoredMagnet:
    token: str
    uri: str
    save_path: str
    selected_files: tuple[int, ...]
    paused: bool


@dataclass(slots=True)
class TorrentTask:
    task_id: str
    name: str
    handle: object
    selected_files: tuple[int, ...]
    files: tuple[TorrentFile, ...]
    save_path: str
    source_torrent_path: str | None
    magnet_uri: str | None = None
    initial_payload_upload: int = 0
    paused: bool = False
    key: str | None = None


def _hash_key(info_hashes) -> str | None:
    """Stable file-name-safe key for a torrent: the v1 hash when it has one.

    get_best() would prefer v2 for hybrid torrents, but most magnet links only
    carry the v1 btih, so restoring from the link must find the same key.
    """

    try:
        key = str(info_hashes.v1) if info_hashes.has_v1() else str(info_hashes.get_best())
    except Exception:
        key = str(info_hashes) if info_hashes is not None else ""
    return key if key and key.strip("0") else None


def handle_key(handle: object) -> str | None:
    try:
        return _hash_key(handle.info_hashes())
    except Exception:
        try:
            return _hash_key(handle.info_hash())
        except Exception:
            return None


def _resume_flags():
    flags = 0
    for name in ("save_info_dict", "only_if_modified"):
        value = getattr(lt.torrent_handle, name, None)
        if value is not None:
            flags |= value
    return flags


def _final_resume_flags():
    flags = 0
    for name in ("save_info_dict", "flush_disk_cache"):
        value = getattr(lt.torrent_handle, name, None)
        if value is not None:
            flags |= value
    return flags


_RESUME_SAVE_INTERVAL_SECONDS = 60.0

# Restored torrents without resume data must hash everything already on disk.
# They are not auto-managed, so libtorrent's active_checking limit does not
# apply and they would all read at once; on a hard disk that seeks constantly.
# Check them one at a time instead; hashing_threads keeps that one fast.
_MAX_CONCURRENT_CHECKS = 1
_CHECKING_STATES = ("CHECKING FILES", "CHECKING RESUME DATA")


def _hashing_threads() -> int:
    return max(2, min(8, (os.cpu_count() or 2) // 2))


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

    The session uses the fixed-slot choker with zero unchoke slots and offers no
    BEP 6 allowed-fast pieces. Local peers are forced to honor the same policy,
    and a payload counter guard immediately aborts a torrent if any piece payload
    upload is observed.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.session = lt.session(self._session_settings())
        self.pending_magnets: dict[str, PendingMagnet] = {}
        self.restored_magnets: dict[str, RestoredMagnet] = {}
        self.tasks: dict[str, TorrentTask] = {}
        # Saved entries that could not be restored (for example, the original
        # .torrent file is gone). They stay in session.json so they are not
        # silently lost, and the UI reports them.
        self.unrestored: list[dict[str, object]] = []
        self._alert_listeners: list = []
        self._last_resume_save = time.monotonic()
        # Task ids waiting for a full check, and the ones currently checking.
        self.check_queue: list[str] = []
        self._checking: set[str] = set()
        self._ensure_resume_alerts()
        self._configure_local_peer_class()
        self._restore_tasks()

    def _session_settings(self) -> dict:
        settings: dict[str, object] = {
            "enable_dht": self.config.enable_dht,
            "enable_lsd": self.config.enable_lsd,
            "enable_incoming_tcp": self.config.enable_tcp,
            "enable_outgoing_tcp": self.config.enable_tcp,
            "enable_incoming_utp": self.config.enable_utp,
            "enable_outgoing_utp": self.config.enable_utp,
            "connections_limit": max(2, self.config.max_connections),
            # Faster full checks: hash on several threads (default 1) and keep
            # 16 MiB of reads outstanding instead of 4 MiB.
            "hashing_threads": _hashing_threads(),
            "checking_mem_usage": 1024,
            "choking_algorithm": 0,
            "unchoke_slots_limit": 0,
            # BEP 6 "allowed fast" lets peers request a few pieces while we keep
            # them choked. Requests for those pieces bypass the zero-unchoke
            # policy and reach the patched write_piece(), which disconnects the
            # peer. Never offer the set, so interested peers stay connected.
            "allowed_fast_set_size": 0,
            "user_agent": "DownloadOnlyTorrent/0.1.0",
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
        }
        settings["download_rate_limit"] = (
            self.config.download_limit_kib * 1024
            if self.config.download_limit_kib > 0
            else 0
        )
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
                task.handle.set_max_connections(max(2, config.max_connections))
                self._apply_feature_flags(task.handle)
                self._kick_discovery(task.handle)
            except Exception:
                pass

    def preview_torrent(self, torrent_path: str) -> tuple[str, list[TorrentFile]]:
        ti = lt.torrent_info(torrent_path)
        return ti.name(), self._files_from_info(ti)

    def prepare_magnet(self, magnet_uri: str, save_path: str) -> str:
        params = lt.parse_magnet_uri(magnet_uri)
        params.save_path = save_path
        params.max_connections = max(2, self.config.max_connections)
        params.flags |= lt.torrent_flags.default_dont_download
        params.flags &= ~lt.torrent_flags.auto_managed
        params.flags &= ~lt.torrent_flags.paused
        params = self._apply_param_feature_flags(params)
        handle = self.session.add_torrent(params)
        handle.resume()
        self._kick_discovery(handle)
        token = uuid.uuid4().hex
        self.pending_magnets[token] = PendingMagnet(
            token, magnet_uri, save_path, handle
        )
        return token

    def magnet_metadata(
        self, token: str
    ) -> tuple[str, list[TorrentFile]] | None:
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

    def start_magnet(
        self, token: str, selected_files: Iterable[int]
    ) -> str:
        pending = self.pending_magnets.pop(token)
        ti = pending.handle.torrent_file()
        if ti is None:
            raise RuntimeError("Magnet metadata is not available yet.")
        files = self._files_from_info(ti)
        selected = self._normalize_selection(selected_files, len(files))
        pending.handle.prioritize_files(
            [4 if i in selected else 0 for i in range(len(files))]
        )
        self._apply_feature_flags(pending.handle)
        pending.handle.resume()
        self._kick_discovery(pending.handle)
        task_id = self._register_task(
            pending.handle,
            ti.name(),
            selected,
            files,
            pending.save_path,
            None,
            magnet_uri=pending.uri,
        )
        self._request_resume_save(pending.handle)
        self._persist_tasks()
        return task_id

    def add_torrent_file(
        self,
        torrent_path: str,
        save_path: str,
        selected_files: Iterable[int],
        *,
        persist: bool = True,
    ) -> str:
        ti = lt.torrent_info(torrent_path)
        self._keep_torrent_copy(torrent_path, _hash_key(ti.info_hashes()))
        return self._add_with_info(
            ti,
            save_path,
            selected_files,
            torrent_path,
            persist=persist,
        )

    def _add_with_info(
        self,
        ti,
        save_path: str,
        selected_files: Iterable[int],
        source_torrent_path: str | None,
        *,
        magnet_uri: str | None = None,
        resume=None,
        persist: bool = True,
        queue_check: bool = False,
    ) -> str:
        files = self._files_from_info(ti)
        selected = self._normalize_selection(selected_files, len(files))
        params = resume if resume is not None else lt.add_torrent_params()
        params.ti = ti
        params.save_path = save_path
        params.max_connections = max(2, self.config.max_connections)
        params.file_priorities = [
            4 if i in selected else 0 for i in range(len(files))
        ]
        params.flags &= ~lt.torrent_flags.auto_managed
        if queue_check:
            # A paused torrent does not start checking until it is resumed.
            params.flags |= lt.torrent_flags.paused
        else:
            params.flags &= ~lt.torrent_flags.paused
        params = self._apply_param_feature_flags(params)
        handle = self.session.add_torrent(params)
        self._apply_feature_flags(handle)
        if not queue_check:
            handle.resume()
            self._kick_discovery(handle)
        task_id = self._register_task(
            handle,
            ti.name(),
            selected,
            files,
            save_path,
            source_torrent_path,
            magnet_uri=magnet_uri,
        )
        if queue_check:
            self.check_queue.append(task_id)
        if persist:
            self._persist_tasks()
        return task_id

    def pause(self, task_id: str) -> None:
        task = self.tasks[task_id]
        task.handle.pause()
        task.paused = True
        self._request_resume_save(task.handle)
        self._persist_tasks()

    def resume(self, task_id: str) -> None:
        task = self.tasks[task_id]
        # Resuming by hand starts the check right away instead of waiting.
        if task_id in self.check_queue:
            self.check_queue.remove(task_id)
        task.handle.resume()
        task.paused = False
        self._kick_discovery(task.handle)
        self._persist_tasks()

    def is_paused(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        return bool(task.paused) if task else False

    def remove(self, task_id: str, *, persist: bool = True) -> None:
        task = self.tasks.pop(task_id, None)
        if task is None:
            return
        self.forget_check(task_id)
        self.discard_saved_state(task.key)
        try:
            task.handle.pause()
            task.handle.clear_peers()
        except Exception:
            pass
        try:
            self.session.remove_torrent(task.handle)
        except Exception:
            pass
        if persist:
            self._persist_tasks()

    def add_alert_listener(self, callback) -> None:
        """Receive every alert batch; the engine is the only alert consumer."""

        self._alert_listeners.append(callback)

    def forget_check(self, task_id: str) -> None:
        if task_id in self.check_queue:
            self.check_queue.remove(task_id)
        self._checking.discard(task_id)

    def _pump_check_queue(self) -> None:
        for task_id in list(self._checking):
            task = self.tasks.get(task_id)
            if task is None or task.paused:
                # Gone, or the user paused it and took over.
                self._checking.discard(task_id)
                continue
            try:
                state = self._state_name(task.handle.status())
            except Exception:
                self._checking.discard(task_id)
                continue
            if state not in _CHECKING_STATES:
                self._checking.discard(task_id)
                # Save right away so the next launch can skip this check.
                self._request_resume_save(task.handle, _resume_flags())

        while self.check_queue and len(self._checking) < _MAX_CONCURRENT_CHECKS:
            task_id = self.check_queue.pop(0)
            task = self.tasks.get(task_id)
            if task is None or task.paused:
                continue
            try:
                task.handle.resume()
                self._kick_discovery(task.handle)
            except Exception:
                continue
            self._checking.add(task_id)

    def poll(self) -> list[TaskSnapshot]:
        self._drain_alerts()
        self._pump_check_queue()
        self._save_resume_periodically()
        self._process_restored_magnets()
        snapshots: list[TaskSnapshot] = []
        for task_id, task in list(self.tasks.items()):
            try:
                status = task.handle.status()
                payload_uploaded = int(
                    getattr(status, "total_payload_upload", 0)
                )
                uploaded_delta = max(
                    0, payload_uploaded - task.initial_payload_upload
                )
                progress = self._selected_progress(task)

                if uploaded_delta > 0:
                    snapshots.append(
                        TaskSnapshot(
                            task_id,
                            task.name,
                            progress,
                            int(getattr(status, "download_payload_rate", 0)),
                            uploaded_delta,
                            int(getattr(status, "num_peers", 0)),
                            "ABORTED",
                            task.save_path,
                            removed=True,
                            error=(
                                "Piece payload upload detected "
                                f"({uploaded_delta} bytes). Torrent was stopped."
                            ),
                        )
                    )
                    self.remove(task_id)
                    continue

                if (
                    bool(getattr(status, "is_finished", False))
                    or progress >= 1.0
                ):
                    snapshots.append(
                        TaskSnapshot(
                            task_id,
                            task.name,
                            1.0,
                            0,
                            0,
                            int(getattr(status, "num_peers", 0)),
                            "COMPLETED",
                            task.save_path,
                            completed=True,
                            removed=True,
                        )
                    )
                    self._finish_task(task_id)
                    continue

                snapshots.append(
                    TaskSnapshot(
                        task_id,
                        task.name,
                        progress,
                        int(getattr(status, "download_payload_rate", 0)),
                        uploaded_delta,
                        int(getattr(status, "num_peers", 0)),
                        "PAUSED"
                        if task.paused
                        else "QUEUED FOR CHECK"
                        if task_id in self.check_queue
                        else self._state_name(status),
                        task.save_path,
                    )
                )
            except Exception as exc:
                snapshots.append(
                    TaskSnapshot(
                        task_id,
                        task.name,
                        0.0,
                        0,
                        0,
                        0,
                        "ERROR",
                        task.save_path,
                        removed=True,
                        error=str(exc),
                    )
                )
                self.remove(task_id)
        return snapshots

    def _register_task(
        self,
        handle: object,
        name: str,
        selected: tuple[int, ...],
        files: list[TorrentFile],
        save_path: str,
        source_torrent_path: str | None,
        *,
        magnet_uri: str | None = None,
    ) -> str:
        status = handle.status()
        task_id = uuid.uuid4().hex
        self.tasks[task_id] = TorrentTask(
            task_id,
            name,
            handle,
            selected,
            tuple(files),
            save_path,
            source_torrent_path,
            magnet_uri,
            int(getattr(status, "total_payload_upload", 0)),
            key=handle_key(handle),
        )
        return task_id

    def _finish_task(self, task_id: str) -> None:
        task = self.tasks.pop(task_id, None)
        if task is None:
            return
        self.forget_check(task_id)
        self.discard_saved_state(task.key)
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
        self._persist_tasks()

    def _selected_progress(self, task: TorrentTask) -> float:
        progress = task.handle.file_progress()
        total = sum(task.files[i].size for i in task.selected_files)
        if total <= 0:
            return 1.0
        done = sum(
            min(int(progress[i]), task.files[i].size)
            for i in task.selected_files
        )
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
        for allowed, flag in (
            (self.config.enable_dht, lt.torrent_flags.disable_dht),
            (self.config.enable_lsd, lt.torrent_flags.disable_lsd),
            (self.config.enable_pex, lt.torrent_flags.disable_pex),
        ):
            if allowed:
                handle.unset_flags(flag)
            else:
                handle.set_flags(flag)

    def _kick_discovery(self, handle: object) -> None:
        try:
            handle.force_reannounce()
        except Exception:
            pass
        if self.config.enable_dht:
            try:
                handle.force_dht_announce()
            except Exception:
                pass

    def _data_dir(self) -> Path:
        if os.name == "nt":
            base = Path(
                os.environ.get(
                    "LOCALAPPDATA",
                    str(Path.home() / "AppData" / "Local"),
                )
            )
            folder = base / "DownloadOnlyTorrent"
        else:
            folder = Path.home() / ".download-only-torrent"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _state_file(self) -> Path:
        return self._data_dir() / "session.json"

    def resume_path(self, key: str) -> Path:
        return self._data_dir() / "resume" / f"{key}.fastresume"

    def torrent_copy_path(self, key: str) -> Path:
        return self._data_dir() / "torrents" / f"{key}.torrent"

    @staticmethod
    def _write_atomic(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        try:
            temp.write_bytes(data)
            temp.replace(target)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def _keep_torrent_copy(self, torrent_path: str, key: str | None) -> None:
        """Keep a private copy so restore does not depend on the original file.

        Browsers often save .torrent files into cache folders that they clean
        up on their own, and the app itself may delete the original after a
        download completes.
        """

        if not key:
            return
        target = self.torrent_copy_path(key)
        try:
            if Path(torrent_path).resolve() == target.resolve():
                return
            self._write_atomic(target, Path(torrent_path).read_bytes())
        except OSError:
            pass

    def discard_saved_state(self, key: str | None) -> None:
        if not key:
            return
        for path in (self.resume_path(key), self.torrent_copy_path(key)):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _load_resume(self, key: str | None):
        if not key:
            return None
        path = self.resume_path(key)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        try:
            return lt.read_resume_data(data)
        except Exception:
            return None

    def _ensure_resume_alerts(self) -> None:
        try:
            current = int(self.session.get_settings().get("alert_mask", 0))
            needed = int(lt.alert_category.error) | int(lt.alert_category.storage)
            self.session.apply_settings({"alert_mask": current | needed})
        except Exception:
            pass

    def _request_resume_save(self, handle: object, flags=None) -> None:
        try:
            if handle.status().has_metadata:
                handle.save_resume_data(_resume_flags() if flags is None else flags)
        except Exception:
            pass

    def _save_resume_periodically(self) -> None:
        now = time.monotonic()
        if now - self._last_resume_save < _RESUME_SAVE_INTERVAL_SECONDS:
            return
        self._last_resume_save = now
        for task in list(self.tasks.values()):
            try:
                if task.handle.status().need_save_resume:
                    self._request_resume_save(task.handle)
            except Exception:
                continue

    def _known_key(self, key: str | None) -> bool:
        return bool(key) and any(task.key == key for task in self.tasks.values())

    def _handle_resume_alert(self, alert) -> str | None:
        """Write resume data for a live task. Returns the torrent key."""

        what = alert.what()
        if what not in ("save_resume_data", "save_resume_data_failed"):
            return None
        key = handle_key(alert.handle)
        # A late reply for a torrent that was removed meanwhile must not
        # recreate its file.
        if what == "save_resume_data" and self._known_key(key):
            try:
                data = lt.write_resume_data_buf(alert.params)
            except Exception:
                data = None
            if data:
                self._write_atomic(self.resume_path(key), bytes(data))
        return key

    def _drain_alerts(self) -> None:
        try:
            alerts = self.session.pop_alerts()
        except Exception:
            return
        for alert in alerts:
            try:
                self._handle_resume_alert(alert)
            except Exception:
                continue
        for listener in list(self._alert_listeners):
            try:
                listener(alerts)
            except Exception:
                continue

    def save_all_resume_data(self, timeout: float = 10.0) -> None:
        """Flush resume data for every task before the app exits."""

        self._drain_alerts()
        outstanding: set[str] = set()
        for task in list(self.tasks.values()):
            try:
                if not task.key or not task.handle.status().has_metadata:
                    continue
                task.handle.save_resume_data(_final_resume_flags())
                outstanding.add(task.key)
            except Exception:
                continue

        deadline = time.monotonic() + timeout
        while outstanding and time.monotonic() < deadline:
            try:
                self.session.wait_for_alert(200)
                alerts = self.session.pop_alerts()
            except Exception:
                break
            for alert in alerts:
                try:
                    key = self._handle_resume_alert(alert)
                except Exception:
                    continue
                if key:
                    outstanding.discard(key)

    def _persist_tasks(self) -> None:
        data: list[dict[str, object]] = []
        for task in self.tasks.values():
            data.append(
                {
                    "kind": "magnet" if task.magnet_uri else "torrent",
                    "source": task.magnet_uri
                    if task.magnet_uri
                    else task.source_torrent_path,
                    "info_hash": task.key,
                    "save_path": task.save_path,
                    "selected_files": list(task.selected_files),
                    "paused": task.paused,
                }
            )
        for pending in self.restored_magnets.values():
            data.append(
                {
                    "kind": "magnet",
                    "source": pending.uri,
                    "save_path": pending.save_path,
                    "selected_files": list(pending.selected_files),
                    "paused": pending.paused,
                }
            )
        data.extend(self.unrestored)

        target = self._state_file()
        temp = target.with_suffix(".tmp")
        try:
            temp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(target)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def _restore_tasks(self) -> None:
        target = self._state_file()
        if not target.is_file():
            return
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return

        for entry in raw:
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind", ""))
            source = str(entry.get("source", "") or "")
            save_path = str(entry.get("save_path", "") or "")
            selected_raw = entry.get("selected_files", [])
            if not source or not save_path or not isinstance(selected_raw, list):
                continue
            try:
                selected = tuple(sorted({int(i) for i in selected_raw}))
            except (TypeError, ValueError):
                continue
            if not selected:
                continue
            paused = bool(entry.get("paused", False))

            try:
                if kind == "torrent":
                    restored = self._restore_torrent(
                        entry, source, save_path, selected, paused
                    )
                elif kind == "magnet" and source.lower().startswith("magnet:?"):
                    restored = self._restore_magnet(
                        source, save_path, selected, paused
                    )
                else:
                    restored = False
            except Exception:
                restored = False
            if not restored:
                self.unrestored.append(entry)

    def _restore_torrent(
        self,
        entry: dict,
        source: str,
        save_path: str,
        selected: tuple[int, ...],
        paused: bool,
    ) -> bool:
        key = str(entry.get("info_hash") or "") or None
        if key is None and Path(source).is_file():
            try:
                key = _hash_key(lt.torrent_info(source).info_hashes())
            except Exception:
                key = None

        resume = self._load_resume(key)
        ti = getattr(resume, "ti", None) if resume is not None else None
        if ti is None:
            for candidate in (
                self.torrent_copy_path(key) if key else None,
                Path(source),
            ):
                if candidate is not None and candidate.is_file():
                    ti = lt.torrent_info(str(candidate))
                    break
        if ti is None:
            return False

        if Path(source).is_file():
            self._keep_torrent_copy(source, key)
        task_id = self._add_with_info(
            ti,
            save_path,
            selected,
            source,
            resume=resume,
            persist=False,
            queue_check=resume is None and not paused,
        )
        if paused:
            task = self.tasks[task_id]
            task.handle.pause()
            task.paused = True
        return True

    def _restore_magnet(
        self,
        uri: str,
        save_path: str,
        selected: tuple[int, ...],
        paused: bool,
    ) -> bool:
        params = lt.parse_magnet_uri(uri)
        resume = self._load_resume(_hash_key(params.info_hashes))
        ti = getattr(resume, "ti", None) if resume is not None else None
        if ti is not None:
            # Saved metadata: no need to wait for peers to send it again.
            task_id = self._add_with_info(
                ti,
                save_path,
                selected,
                None,
                magnet_uri=uri,
                resume=resume,
                persist=False,
            )
            if paused:
                task = self.tasks[task_id]
                task.handle.pause()
                task.paused = True
            return True

        params.save_path = save_path
        params.max_connections = max(2, self.config.max_connections)
        params.flags |= lt.torrent_flags.default_dont_download
        params.flags &= ~lt.torrent_flags.auto_managed
        params.flags &= ~lt.torrent_flags.paused
        params = self._apply_param_feature_flags(params)
        handle = self.session.add_torrent(params)
        handle.resume()
        self._kick_discovery(handle)
        token = uuid.uuid4().hex
        self.pending_magnets[token] = PendingMagnet(
            token, uri, save_path, handle
        )
        self.restored_magnets[token] = RestoredMagnet(
            token, uri, save_path, selected, paused
        )
        return True

    def _process_restored_magnets(self) -> None:
        changed = False
        for token, restored in list(self.restored_magnets.items()):
            pending = self.pending_magnets.get(token)
            if pending is None:
                self.restored_magnets.pop(token, None)
                changed = True
                continue
            try:
                if not pending.handle.status().has_metadata:
                    continue
                ti = pending.handle.torrent_file()
                if ti is None:
                    continue
                files = self._files_from_info(ti)
                selected = self._normalize_selection(
                    restored.selected_files, len(files)
                )
                pending.handle.prioritize_files(
                    [4 if i in selected else 0 for i in range(len(files))]
                )
                self._apply_feature_flags(pending.handle)
                pending.handle.resume()
                self._kick_discovery(pending.handle)
                task_id = self._register_task(
                    pending.handle,
                    ti.name(),
                    selected,
                    files,
                    restored.save_path,
                    None,
                    magnet_uri=restored.uri,
                )
                self._request_resume_save(pending.handle)
                if restored.paused:
                    task = self.tasks[task_id]
                    task.handle.pause()
                    task.paused = True
                self.pending_magnets.pop(token, None)
                self.restored_magnets.pop(token, None)
                changed = True
            except Exception:
                continue
        if changed:
            self._persist_tasks()

    @staticmethod
    def _normalize_selection(
        selected_files: Iterable[int], count: int
    ) -> tuple[int, ...]:
        selected = tuple(
            sorted({int(i) for i in selected_files if 0 <= int(i) < count})
        )
        if not selected:
            raise ValueError("Select at least one file to download.")
        return selected

    @staticmethod
    def _files_from_info(ti) -> list[TorrentFile]:
        storage = ti.files()
        return [
            TorrentFile(i, storage.file_path(i), int(storage.file_size(i)))
            for i in range(storage.num_files())
        ]

    @staticmethod
    def _state_name(status) -> str:
        state = getattr(status, "state", None)
        name = getattr(state, "name", None)
        if name:
            return str(name).replace("_", " ").upper()
        return str(state).split(".")[-1].replace("_", " ").upper()
