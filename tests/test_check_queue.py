from __future__ import annotations

from conftest import close_engine, make_engine, make_torrent, pump, write_session

MIB = 1024 * 1024


def _partial_downloads(tmp_path, count: int = 3):
    """Torrents whose files are 3/4 present on disk, with no resume data."""

    downloads = tmp_path / "dl"
    entries = []
    for index in range(count):
        name = f"part{index}.bin"
        content, torrent = make_torrent(
            downloads, name, 8 * MIB, piece_size=256 * 1024
        )
        with (content / name).open("r+b") as handle:
            handle.seek(6 * MIB)
            handle.write(b"\0" * (2 * MIB))
        source = tmp_path / f"t{index}.torrent"
        source.write_bytes(torrent)
        entries.append(
            {
                "kind": "torrent",
                "source": str(source),
                "save_path": str(downloads),
                "selected_files": [0],
                "paused": False,
            }
        )
    return downloads, entries


def test_restored_torrents_are_checked_one_at_a_time(tmp_path, isolated_home):
    downloads, entries = _partial_downloads(tmp_path)
    write_session(isolated_home, entries)

    engine = make_engine(downloads)
    try:
        assert len(engine.check_queue) == 3
        most_checking = 0

        def all_checked() -> bool:
            nonlocal most_checking
            most_checking = max(most_checking, len(engine._checking))
            return not engine.check_queue and not engine._checking

        assert pump(engine, 60, all_checked)
        assert most_checking == 1
        for task in engine.tasks.values():
            status = task.handle.status()
            assert engine._state_name(status) == "DOWNLOADING"
            assert status.total_wanted_done == 6 * MIB

        # Resume data is written as each check ends.
        assert pump(
            engine,
            10,
            lambda: all(engine.resume_path(t.key).is_file() for t in engine.tasks.values()),
        )
    finally:
        close_engine(engine)

    engine = make_engine(downloads)
    try:
        assert engine.check_queue == []
        for task in engine.tasks.values():
            assert task.handle.status().total_wanted_done == 6 * MIB
    finally:
        close_engine(engine)


def test_queued_torrent_shows_queued_state_and_manual_resume_skips_queue(
    tmp_path, isolated_home
):
    downloads, entries = _partial_downloads(tmp_path)
    write_session(isolated_home, entries)
    engine = make_engine(downloads)
    try:
        snapshots = {snap.task_id: snap.state for snap in engine.poll()}
        queued = list(engine.check_queue)
        assert queued and all(snapshots[t] == "QUEUED FOR CHECK" for t in queued)

        engine.resume(queued[-1])
        assert queued[-1] not in engine.check_queue
    finally:
        close_engine(engine)
