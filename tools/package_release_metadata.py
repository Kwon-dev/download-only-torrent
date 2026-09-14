from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import shutil
import site
import sys
from pathlib import Path

from verify_patched_libtorrent import find_libtorrent_binaries, verify_binary


QT_LICENSES = ("LGPL-3.0-only.txt", "GPL-3.0-only.txt")
PATCH_MARKER = b"DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED"
LIBTORRENT_TAG = "v2.1.1"
LIBTORRENT_COMMIT = "56ae8caba38bf154ffc210403cb23f91d0ecaa49"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Copied {src} -> {dst}")


def find_distribution_license(filename: str) -> Path:
    for dist_name in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6"):
        try:
            dist = importlib.metadata.distribution(dist_name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for entry in dist.files or ():
            if Path(str(entry)).name != filename:
                continue
            candidate = Path(dist.locate_file(entry)).resolve()
            if candidate.is_file():
                return candidate

    roots: set[Path] = set()
    for value in site.getsitepackages():
        roots.add(Path(value))
    try:
        roots.add(Path(site.getusersitepackages()))
    except Exception:
        pass
    for root in roots:
        if not root.is_dir():
            continue
        patterns = (
            f"PySide6*/**/{filename}",
            f"shiboken6*/**/{filename}",
            f"PySide6/**/{filename}",
        )
        for pattern in patterns:
            for candidate in root.glob(pattern):
                if candidate.is_file():
                    return candidate.resolve()
    raise FileNotFoundError(f"could not find installed Qt/PySide6 license: {filename}")


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
    copy(repo_root / "LICENSES" / "libtorrent.txt", licenses / "libtorrent.txt")

    for name in QT_LICENSES:
        copy(find_distribution_license(name), licenses / name)
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
