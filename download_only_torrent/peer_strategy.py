from __future__ import annotations

from PySide6.QtCore import QSettings


LARGE_PEER_POOL_KEY = "network/large_peer_pool"
SEEDER_PREFERENCE_KEY = "network/seeder_preference"

LARGE_POOL_GLOBAL_CONNECTIONS = 1000
LARGE_POOL_TORRENT_CONNECTIONS = 500
_LARGE_POOL_CONNECTION_SPEED = 80
_LARGE_POOL_NUM_WANT = 500
_LARGE_POOL_MAX_PEX_PEERS = 200

# Peer turnover (percent of peers dropped, pool fill cutoff percent, interval
# seconds). libtorrent drops uninteresting peers first, then non-seeds, then the
# slowest senders, and only when it has new candidates to replace them with.
_DEFAULT_TURNOVER = (4, 90, 300)
_LARGE_POOL_TURNOVER = (10, 80, 60)
_SEEDER_TURNOVER = (10, 80, 90)
_LARGE_POOL_SEEDER_TURNOVER = (15, 75, 45)


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def setting_bool(key: str, default: bool = False) -> bool:
    return as_bool(QSettings().value(key, default))


def large_pool_enabled() -> bool:
    return setting_bool(LARGE_PEER_POOL_KEY)


def seeder_preference_enabled() -> bool:
    return setting_bool(SEEDER_PREFERENCE_KEY)


def set_options(large_pool: bool, prefer_seeders: bool) -> None:
    settings = QSettings()
    settings.setValue(LARGE_PEER_POOL_KEY, bool(large_pool))
    settings.setValue(SEEDER_PREFERENCE_KEY, bool(prefer_seeders))
    settings.sync()


def turnover_profile(large_pool: bool, prefer_seeders: bool) -> tuple[int, int, int]:
    """Pick how aggressively libtorrent rotates peers out of a full pool.

    Rotating weak connections lets the large pool spend its extra sockets on
    discovery, and lets the seeder preference free slots for new seeders without
    tearing down the connections that are already delivering data.
    """

    if large_pool and prefer_seeders:
        return _LARGE_POOL_SEEDER_TURNOVER
    if large_pool:
        return _LARGE_POOL_TURNOVER
    if prefer_seeders:
        return _SEEDER_TURNOVER
    return _DEFAULT_TURNOVER


def session_settings(max_connections: int) -> dict[str, object]:
    """libtorrent settings for the optional peer strategies.

    Every key is always present so turning an option off restores the
    libtorrent default; apply_settings() only changes keys it is given.
    """

    large_pool = large_pool_enabled()
    if large_pool:
        settings: dict[str, object] = {
            "connections_limit": max(LARGE_POOL_GLOBAL_CONNECTIONS, max_connections),
            "connection_speed": _LARGE_POOL_CONNECTION_SPEED,
            "num_want": _LARGE_POOL_NUM_WANT,
            "max_pex_peers": _LARGE_POOL_MAX_PEX_PEERS,
        }
    else:
        settings = {"connection_speed": 30, "num_want": 200, "max_pex_peers": 50}

    turnover, cutoff, interval = turnover_profile(
        large_pool, seeder_preference_enabled()
    )
    settings.update(
        {
            "peer_turnover": turnover,
            "peer_turnover_cutoff": cutoff,
            "peer_turnover_interval": interval,
        }
    )
    return settings


def torrent_connection_limit(max_connections: int) -> int:
    limit = max(2, max_connections)
    if large_pool_enabled():
        limit = max(LARGE_POOL_TORRENT_CONNECTIONS, limit)
    return limit
