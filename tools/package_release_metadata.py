from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import shutil
import site
import sys
from pathlib import Path


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
    # Qt for Python wheels include their license files. Prefer files belonging
    # to the exact PySide6/shiboken distributions installed for this build so
    # release packaging does not depend on an external license web server.
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


def find_libtorrent_binary() -> Path:
    spec = importlib.util.find_spec("libtorrent")
    if spec is None or not spec.origin:
        raise FileNotFoundError("libtorrent module is not installed")
    path = Path(spec.origin).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if PATCH_MARKER not in path.read_bytes():
        raise RuntimeError("installed libtorrent is not the hard-disabled patched build")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--boost-root")
    parser.add_argument("--openssl-root")
    parser.add_argument("--libtorrent-source")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    repo_root = Path(args.repo_root).resolve()
    licenses = app_dir / "LICENSES"
    licenses.mkdir(parents=True, exist_ok=True)

    copy(repo_root / "LICENSE", app_dir / "LICENSE")
    copy(repo_root / "THIRD_PARTY_NOTICES.md", app_dir / "THIRD_PARTY_NOTICES.md")
    copy(repo_root / "QT_LGPL_SOURCE_OFFER.md", app_dir / "QT_LGPL_SOURCE_OFFER.md")

    patcher = repo_root / "tools" / "patch_libtorrent_no_piece_upload.py"
    copy(patcher, licenses / "libtorrent-no-piece-upload-patcher.py")

    libtorrent_license = repo_root / "LICENSES" / "libtorrent.txt"
    if args.libtorrent_source:
        upstream_license = Path(args.libtorrent_source).resolve() / "LICENSE"
        if upstream_license.is_file():
            libtorrent_license = upstream_license
    copy(libtorrent_license, licenses / "libtorrent.txt")

    for name in QT_LICENSES:
        copy(find_distribution_license(name), licenses / name)

    copy(find_python_license(), licenses / "Python-3.11.txt")

    if args.boost_root:
        copy(Path(args.boost_root).resolve() / "LICENSE_1_0.txt", licenses / "Boost-1.0.txt")

    if args.openssl_root:
        openssl_root = Path(args.openssl_root).resolve()
        candidates = [
            openssl_root / "share" / "openssl" / "copyright",
            openssl_root / "LICENSE.txt",
            openssl_root / "LICENSE",
        ]
        for candidate in candidates:
            if candidate.is_file():
                copy(candidate, licenses / "OpenSSL.txt")
                break
        else:
            raise FileNotFoundError(f"OpenSSL license not found under {openssl_root}")

    module = find_libtorrent_binary()
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
        f"libtorrent module: {module.name}",
        f"libtorrent module SHA-256: {sha256(module)}",
        f"source patcher SHA-256: {sha256(patcher)}",
    ]
    if exe.is_file():
        lines.append(f"DownloadOnlyTorrent.exe SHA-256: {sha256(exe)}")
    (app_dir / "PATCHED_LIBTORRENT_BUILD.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote PATCHED_LIBTORRENT_BUILD.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
