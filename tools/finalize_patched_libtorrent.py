from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from verify_patched_libtorrent import (
    find_installed_libtorrent_binary,
    find_libtorrent_binaries,
    verify_binary,
)


def stage(stage_dir: Path) -> None:
    source = find_installed_libtorrent_binary()
    digest = verify_binary(source)

    stage_dir.mkdir(parents=True, exist_ok=True)
    for stale in stage_dir.glob("*.pyd"):
        stale.unlink()

    target = stage_dir / source.name
    shutil.copy2(source, target)
    staged_digest = verify_binary(target)
    if staged_digest != digest:
        raise RuntimeError("staged libtorrent differs from the verified installed module")

    print(f"Staged verified libtorrent: {source} -> {target}")
    print(f"SHA-256: {staged_digest}")


def finalize(stage_dir: Path, dist_dir: Path) -> None:
    # The wheel packages the extension as libtorrent/__init__.<abi>.pyd, so once
    # staged outside the package directory its filename no longer contains the
    # word "libtorrent". The staging directory is dedicated to this exact
    # verified module, therefore select its single top-level .pyd directly.
    staged = sorted(path.resolve() for path in stage_dir.glob("*.pyd") if path.is_file())
    if len(staged) != 1:
        raise RuntimeError(
            f"expected exactly one staged libtorrent .pyd, found {len(staged)}: {staged}"
        )

    staged_module = staged[0]
    expected_digest = verify_binary(staged_module)
    packaged = find_libtorrent_binaries(dist_dir)
    if not packaged:
        raise RuntimeError(f"no packaged libtorrent .pyd found under {dist_dir.resolve()}")

    print(f"Verified staged libtorrent: {staged_module}")
    print(f"Expected SHA-256: {expected_digest}")
    for target in packaged:
        before_digest = None
        try:
            before_digest = verify_binary(target)
        except RuntimeError:
            pass
        print(f"Replacing packaged libtorrent: {target} (pre-replacement SHA-256={before_digest or 'unverified'})")
        shutil.copy2(staged_module, target)
        actual_digest = verify_binary(target)
        if actual_digest != expected_digest:
            raise RuntimeError(
                f"final packaged libtorrent SHA mismatch for {target}: "
                f"expected {expected_digest}, got {actual_digest}"
            )
        print(f"Final packaged libtorrent verified: {target} SHA-256={actual_digest}")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--stage-dir", required=True, type=Path)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--stage-dir", required=True, type=Path)
    finalize_parser.add_argument("--dist-dir", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "stage":
        stage(args.stage_dir.resolve())
    else:
        finalize(args.stage_dir.resolve(), args.dist_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
