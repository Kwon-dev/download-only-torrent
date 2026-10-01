from __future__ import annotations

from conftest import close_engine, make_engine, make_torrent

EXTRA = "udp://tracker.example.org:1337/announce\nudp://other.example.net:6969/announce"
OWN = "udp://own.example.com:80/announce"


def _urls(handle) -> list[str]:
    return [entry["url"] for entry in handle.trackers()]


def _add(engine, tmp_path, name: str, **kwargs):
    _, torrent = make_torrent(tmp_path / name, f"{name}.bin", 128 * 1024, **kwargs)
    path = tmp_path / f"{name}.torrent"
    path.write_bytes(torrent)
    task_id = engine.add_torrent_file(str(path), str(tmp_path / "dl"), [0])
    return engine.tasks[task_id].handle


def test_extra_trackers_added_to_public_torrents_only(tmp_path):
    engine = make_engine(tmp_path, add_extra_trackers=True, extra_trackers=EXTRA)
    try:
        public = _add(engine, tmp_path, "public", trackers=(OWN,))
        private = _add(engine, tmp_path, "private", private=True, trackers=(OWN,))
        assert set(EXTRA.splitlines()) | {OWN} == set(_urls(public))
        # Announcing a private info-hash to public trackers would leak it.
        assert _urls(private) == [OWN]
    finally:
        close_engine(engine)


def test_disabling_extra_trackers_removes_them_but_keeps_own(tmp_path):
    engine = make_engine(tmp_path, add_extra_trackers=True, extra_trackers=EXTRA)
    try:
        handle = _add(engine, tmp_path, "public", trackers=(OWN,))
        engine.config.add_extra_trackers = False
        engine.apply_config(engine.config)
        assert _urls(handle) == [OWN]
    finally:
        close_engine(engine)


def test_magnet_gets_extra_trackers_while_fetching_metadata(tmp_path):
    engine = make_engine(tmp_path, add_extra_trackers=True, extra_trackers=EXTRA)
    try:
        token = engine.prepare_magnet(
            "magnet:?xt=urn:btih:" + "ab" * 20, str(tmp_path / "dl")
        )
        assert set(_urls(engine.pending_magnets[token].handle)) == set(
            EXTRA.splitlines()
        )
    finally:
        close_engine(engine)
