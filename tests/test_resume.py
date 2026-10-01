from __future__ import annotations

import libtorrent as lt

from conftest import (
    close_engine,
    make_engine,
    make_torrent,
    pump,
    read_session,
    write_session,
)


def _has_pieces(engine, count: int = 4) -> bool:
    return bool(engine.tasks) and all(
        task.handle.status().num_pieces >= count for task in engine.tasks.values()
    )


def test_restart_restores_from_resume_data_without_original_torrent(
    tmp_path, isolated_home, seeder
):
    content, torrent = make_torrent(tmp_path / "seed", "alpha.bin", 4 * 1024 * 1024)
    seeder.seed(content, torrent)
    original = tmp_path / "browser_cache" / "alpha.torrent"
    original.parent.mkdir()
    original.write_bytes(torrent)
    downloads = tmp_path / "dl"

    engine = make_engine(downloads)
    task_id = engine.add_torrent_file(str(original), str(downloads), [0])
    key = engine.tasks[task_id].key
    engine.tasks[task_id].handle.connect_peer(seeder.endpoint)
    assert pump(engine, 20, lambda: _has_pieces(engine))
    # Count before saving: pieces finished after the save are not in it.
    pieces_before = engine.tasks[task_id].handle.status().num_pieces
    engine.save_all_resume_data()
    assert engine.resume_path(key).is_file()
    assert engine.torrent_copy_path(key).is_file()
    close_engine(engine)

    # The browser cleaned up its download cache.
    original.unlink()

    engine = make_engine(downloads)
    try:
        assert engine.unrestored == []
        assert engine.check_queue == []
        (task,) = engine.tasks.values()
        status = task.handle.status()
        # Resume data: no full re-check, and every completed piece is kept.
        assert engine._state_name(status) != "CHECKING FILES"
        assert status.num_pieces >= pieces_before
        assert read_session(isolated_home)[0]["info_hash"] == key
    finally:
        close_engine(engine)


def test_v1_magnet_restores_without_fetching_metadata(tmp_path, seeder):
    content, torrent = make_torrent(tmp_path / "seed", "beta.bin", 2 * 1024 * 1024)
    seeder.seed(content, torrent)
    info = lt.torrent_info(torrent)
    # Most real magnet links carry only the v1 btih.
    magnet = f"magnet:?xt=urn:btih:{info.info_hashes().v1}"
    downloads = tmp_path / "dl"

    engine = make_engine(downloads)
    token = engine.prepare_magnet(magnet, str(downloads))
    engine.pending_magnets[token].handle.connect_peer(seeder.endpoint)
    assert pump(engine, 20, lambda: engine.magnet_metadata(token) is not None)
    engine.start_magnet(token, [0])
    pump(engine, 1)
    engine.save_all_resume_data()
    close_engine(engine)

    engine = make_engine(downloads)
    try:
        assert engine.pending_magnets == {}
        assert [task.name for task in engine.tasks.values()] == ["beta.bin"]
        assert str(info.info_hashes().v1) in {t.key for t in engine.tasks.values()}
    finally:
        close_engine(engine)


def test_unrestorable_entry_is_kept_not_dropped(tmp_path, isolated_home):
    entry = {
        "kind": "torrent",
        "source": str(tmp_path / "gone.torrent"),
        "save_path": str(tmp_path / "dl"),
        "selected_files": [0],
        "paused": False,
    }
    write_session(isolated_home, [entry])

    engine = make_engine(tmp_path / "dl")
    try:
        assert engine.tasks == {}
        assert engine.unrestored == [entry]
        engine._persist_tasks()
        assert read_session(isolated_home) == [entry]
    finally:
        close_engine(engine)


def test_remove_deletes_resume_data_and_copy(tmp_path):
    content, torrent = make_torrent(tmp_path / "seed", "gamma.bin", 256 * 1024)
    path = tmp_path / "gamma.torrent"
    path.write_bytes(torrent)
    engine = make_engine(tmp_path / "dl")
    try:
        task_id = engine.add_torrent_file(str(path), str(tmp_path / "dl"), [0])
        key = engine.tasks[task_id].key
        engine.save_all_resume_data()
        assert engine.resume_path(key).is_file()
        engine.remove(task_id)
        assert not engine.resume_path(key).exists()
        assert not engine.torrent_copy_path(key).exists()
    finally:
        close_engine(engine)
