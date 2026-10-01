from __future__ import annotations

import libtorrent as lt

from . import __version__


PEER_ID_CODE = "DO"


def _version_components() -> tuple[int, int, int]:
    core = __version__.split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    values: list[int] = []
    for part in parts[:3]:
        try:
            values.append(max(0, int(part)))
        except ValueError:
            values.append(0)
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def client_user_agent() -> str:
    return f"DownloadOnlyTorrent/{__version__}"


def client_peer_fingerprint() -> str:
    major, minor, revision = _version_components()
    return lt.generate_fingerprint(
        PEER_ID_CODE,
        major,
        minor,
        revision,
        0,
    )
