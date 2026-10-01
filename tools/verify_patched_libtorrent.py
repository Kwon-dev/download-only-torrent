from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


MARKER = b"DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED"
# Peer turnover grace period (tools/patch_libtorrent_peer_turnover.py).
TURNOVER_MARKER = b"DOWNLOAD_ONLY_TORRENT_TURNOVER_GRACE"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_binary(path: Path) -> str:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    data = path.read_bytes()
    if MARKER not in data:
        raise RuntimeError(
            f"patched libtorrent marker is missing from {path}; "
            "refusing to package a stock/upload-capable libtorrent build"
        )
    if TURNOVER_MARKER not in data:
        raise RuntimeError(
            f"peer turnover patch marker is missing from {path}; "
            "the libtorrent build predates the turnover grace period patch"
        )
    return hashlib.sha256(data).hexdigest()


def find_libtorrent_binaries(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        return []

    root_is_libtorrent_package = root.name.lower() == "libtorrent"
    matches: list[Path] = []
    for path in root.rglob("*.pyd"):
        relative = path.relative_to(root)
        parent_parts = {part.lower() for part in relative.parts[:-1]}
        if (
            root_is_libtorrent_package
            or "libtorrent" in path.name.lower()
            or "libtorrent" in parent_parts
        ):
            matches.append(path.resolve())
    return sorted(matches)


def find_installed_libtorrent_binary() -> Path:
    spec = importlib.util.find_spec("libtorrent")
    if spec is None or not spec.origin:
        raise FileNotFoundError("libtorrent module is not installed")

    origin = Path(spec.origin).resolve()
    candidates: list[Path] = []
    if origin.is_file() and origin.suffix.lower() == ".pyd":
        candidates.append(origin)

    search_roots: list[Path] = []
    if origin.exists():
        search_roots.append(origin.parent)
    for location in spec.submodule_search_locations or ():
        root = Path(location).resolve()
        if root.is_dir():
            search_roots.append(root)

    for root in search_roots:
        candidates.extend(find_libtorrent_binaries(root))

    unique = list(dict.fromkeys(path for path in candidates if path.is_file()))
    if not unique:
        raise FileNotFoundError(
            f"no compiled libtorrent .pyd found for import origin {origin}"
        )
    if len(unique) == 1:
        return unique[0]

    verified: list[Path] = []
    for candidate in unique:
        try:
            verify_binary(candidate)
        except RuntimeError:
            continue
        verified.append(candidate)
    if len(verified) == 1:
        return verified[0]

    raise RuntimeError(
        "could not identify a unique installed libtorrent extension module: "
        + ", ".join(str(path) for path in unique)
    )


def main() -> int:
    module_path = find_installed_libtorrent_binary()
    digest = verify_binary(module_path)
    print(f"Patched libtorrent verified: {module_path}")
    print(f"SHA-256: {digest}")
    print(f"Markers: {MARKER.decode('ascii')}, {TURNOVER_MARKER.decode('ascii')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
