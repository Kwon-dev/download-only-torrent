from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


MARKER = b"DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED"


def main() -> int:
    spec = importlib.util.find_spec("libtorrent")
    if spec is None or not spec.origin:
        raise SystemExit("libtorrent module is not installed")

    module_path = Path(spec.origin).resolve()
    if not module_path.is_file():
        raise SystemExit(f"libtorrent module path is not a file: {module_path}")

    data = module_path.read_bytes()
    if MARKER not in data:
        raise SystemExit(
            "patched libtorrent marker is missing from the compiled module; "
            "refusing to package a stock/upload-capable libtorrent build"
        )

    digest = hashlib.sha256(data).hexdigest()
    print(f"Patched libtorrent verified: {module_path}")
    print(f"SHA-256: {digest}")
    print(f"Marker: {MARKER.decode('ascii')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
