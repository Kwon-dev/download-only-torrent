from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from verify_patched_libtorrent import TURNOVER_MARKER, find_libtorrent_binaries, verify_binary


QT_LICENSES = ("LGPL-3.0-only.txt", "GPL-3.0-only.txt")
PYSIDE_SOURCE_COMMIT = "d5c8535130fafc65d868753f5cf72b6b9b10d628"
PYSIDE_LICENSE_BLOBS = {
    "LGPL-3.0-only.txt": "65c5ca88a67c30becee01c5a8816d964b03862f9",
    "GPL-3.0-only.txt": "94a9ed024d3859793618152ea559a168bbcbb5e2",
}
PATCH_MARKER = b"DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED"
LIBTORRENT_TAG = "v2.1.1"
LIBTORRENT_COMMIT = "56ae8caba38bf154ffc210403cb23f91d0ecaa49"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def copy(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Copied {src} -> {dst}")


def materialize_qt_license(repo_root: Path, filename: str, dst: Path) -> None:
    vendored = repo_root / "LICENSES" / filename
    if vendored.is_file():
        copy(vendored, dst)
        return

    expected_blob = PYSIDE_LICENSE_BLOBS[filename]
    url = (
        "https://raw.githubusercontent.com/pyside/pyside-setup/"
        f"{PYSIDE_SOURCE_COMMIT}/LICENSES/{filename}"
    )
    last_error: Exception | None = None
    data: bytes | None = None
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "download-only-torrent-release-builder"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            break
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            print(f"Qt license fetch attempt {attempt}/3 failed for {filename}: {exc}")

    if data is None:
        raise RuntimeError(
            f"could not fetch pinned PySide6 license {filename} from {url}: {last_error}"
        )

    actual_blob = git_blob_sha1(data)
    if actual_blob != expected_blob:
        raise RuntimeError(
            f"pinned PySide6 license blob mismatch for {filename}: "
            f"expected {expected_blob}, got {actual_blob}"
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    print(
        f"Fetched pinned PySide6 license {filename} from commit "
        f"{PYSIDE_SOURCE_COMMIT}; verified blob {actual_blob}"
    )


def find_python_license() -> Path:
    candidates = [
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
        Path(sys.prefix) / "LICENSE.txt",
        Path(sys.prefix) / "LICENSE",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Python runtime license file not found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    repo_root = Path(args.repo_root).resolve()
    licenses = app_dir / "LICENSES"
    licenses.mkdir(parents=True, exist_ok=True)

    copy(repo_root / "LICENSE", app_dir / "LICENSE")
    copy(repo_root / "THIRD_PARTY_NOTICES.md", app_dir / "THIRD_PARTY_NOTICES.md")
    copy(repo_root / "QT_LGPL_SOURCE_OFFER.md", app_dir / "QT_LGPL_SOURCE_OFFER.md")

    patcher = repo_root / "tools" / "patch_libtorrent_no_piece_upload.py"
    copy(patcher, licenses / "libtorrent-no-piece-upload-patcher.py")
    turnover_patcher = repo_root / "tools" / "patch_libtorrent_peer_turnover.py"
    copy(turnover_patcher, licenses / "libtorrent-peer-turnover-patcher.py")
    copy(repo_root / "LICENSES" / "libtorrent.txt", licenses / "libtorrent.txt")

    for name in QT_LICENSES:
        materialize_qt_license(repo_root, name, licenses / name)
    copy(find_python_license(), licenses / "Python-3.11.txt")
    copy(cache_dir / "licenses" / "Boost-1.0.txt", licenses / "Boost-1.0.txt")
    copy(cache_dir / "licenses" / "OpenSSL.txt", licenses / "OpenSSL.txt")

    modules = find_libtorrent_binaries(app_dir)
    if not modules:
        raise FileNotFoundError(f"packaged libtorrent module not found under {app_dir}")

    module_hashes: list[tuple[Path, str]] = []
    for module in modules:
        module_hashes.append((module, verify_binary(module)))
    unique_hashes = {digest for _, digest in module_hashes}
    if len(unique_hashes) != 1:
        raise RuntimeError("packaged libtorrent candidates are not byte-for-byte identical")

    exe = app_dir / "DownloadOnlyTorrent.exe"
    lines = [
        "Download Only Torrent - patched libtorrent build provenance",
        "",
        f"libtorrent upstream tag: {LIBTORRENT_TAG}",
        f"libtorrent upstream commit: {LIBTORRENT_COMMIT}",
        "patched source: src/bt_peer_connection.cpp::write_piece()",
        "source transformation: tools/patch_libtorrent_no_piece_upload.py",
        "policy: BitTorrent PIECE payload queueing code removed; attempted entry disconnects the peer",
        f"compiled marker: {PATCH_MARKER.decode('ascii')}",
        f"source patcher SHA-256: {sha256(patcher)}",
        "",
        "patched source: src/torrent.cpp::compare_disconnect_peer(), torrent::disconnect_peers()",
        "source transformation: tools/patch_libtorrent_peer_turnover.py",
        "policy: peer turnover keeps new and currently sending peers; ranks by current rate",
        f"compiled marker: {TURNOVER_MARKER.decode('ascii')}",
        f"source patcher SHA-256: {sha256(turnover_patcher)}",
        "",
    ]
    for module, digest in module_hashes:
        relative = module.relative_to(app_dir)
        lines.append(f"packaged libtorrent module: {relative}")
        lines.append(f"packaged libtorrent module SHA-256: {digest}")
    if exe.is_file():
        lines.append(f"DownloadOnlyTorrent.exe SHA-256: {sha256(exe)}")
    (app_dir / "PATCHED_LIBTORRENT_BUILD.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote PATCHED_LIBTORRENT_BUILD.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
