# Technical design

[← English README](../README.md) · [한국어 README](../README.ko.md) · [Development guide](DEVELOPMENT.md)

This document describes the implementation and verification of Download Only Torrent, especially the distinction between **BitTorrent file-piece payload** and other network traffic.

## Stack and scope

- Windows desktop UI: **Python 3.11**, **PySide6 6.9.2**, packaged with PyInstaller in **onedir** mode.
- Torrent engine: **libtorrent 2.1.1**, compiled from the pinned upstream revision in [`tools/libtorrent_build_manifest.json`](../tools/libtorrent_build_manifest.json).
- Core implementation: [`download_only_torrent/engine.py`](../download_only_torrent/engine.py); persistent application settings: [`config.py`](../download_only_torrent/config.py).
- Download paths: toolbar and multi-file picker in [`network_ui.py`](../download_only_torrent/network_ui.py), in-app dialogs in [`ui.py`](../download_only_torrent/ui.py), and Windows file/protocol open requests in [`windows_integration.py`](../download_only_torrent/windows_integration.py).

## Exactly what is disabled

The **official Windows build** patches upstream `src/bt_peer_connection.cpp` using [`tools/patch_libtorrent_no_piece_upload.py`](../tools/patch_libtorrent_no_piece_upload.py). The transformation replaces the normal `bt_peer_connection::write_piece()` behavior that would queue a BitTorrent PIECE message containing file-piece data. If that forbidden path is entered, the patched implementation emits a marker and disconnects rather than sending the piece payload.

Other defenses include:

1. Session seeding is disabled and the unchoke-slot limit is set to zero.
2. BEP 6 allowed-fast piece allowances are disabled.
3. The local peer class is configured so LAN connections cannot bypass the unchoke policy.
4. A runtime check aborts a torrent if its piece-payload upload counter becomes nonzero.
5. The Windows build verifies the compiled `DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED` marker before packaging and verifies the packaged binary afterward.

**Limit:** This policy is specifically about **BitTorrent file-piece payload**. The client still transmits ordinary protocol traffic such as tracker and DHT requests, handshakes, piece requests, keep-alives and transport acknowledgements. It is not designed to guarantee zero outbound bytes, privacy, anonymous downloads or compliance with private-tracker ratio rules.

## Peer discovery and turnover

Configurable discovery includes DHT, PEX, LSD, TCP, uTP, optional IPv6 and a configurable list of extra public trackers. Extra trackers are **not** injected into private torrents.

By default, the client listens and announces on the default-route interface rather than indiscriminately binding to VPN, virtual or loopback adapters. The option is configurable and is not a privacy or VPN-leak prevention guarantee.

[The peer-turnover transformation](../tools/patch_libtorrent_peer_turnover.py) modifies upstream `src/torrent.cpp` so the periodic turnover strategy avoids dropping peers in their first two minutes or while sending wanted pieces to us, then ranks remaining candidates using download rate. The build checks its marker alongside the piece-upload patch.

## File selection and metadata

For a `.torrent` file, the app reads its metadata before adding the torrent and assigns priorities based on the selected file indexes.

For a magnet link, the engine initially uses libtorrent's `default_dont_download` flag while fetching metadata. After file selection, only chosen files receive normal download priority.

The optional **file-size filter**, disabled by default, unchecks files whose metadata size is **less than or equal to** the configured MB threshold (decimal MB: 1,000,000 bytes). It is an initial selection convenience, not a transfer-time enforcement rule; users can recheck excluded files. The current configuration is supplied to every file picker, including the toolbar, magnet and Windows shell entry paths.

Pieces can span file boundaries. libtorrent may fetch complete boundary pieces even if one adjacent file is not selected. Therefore the filter is not a guarantee that absolutely no bytes associated with skipped files will be transferred or written.

## Task lifecycle and persistence

- Selected file priorities and active torrent state are preserved across restarts using libtorrent resume data and local session state.
- A private copy of an imported `.torrent` can be retained for restoration if the original source file disappears.
- Restored tasks requiring verification are checked sequentially with multithreaded hashing.
- When all selected content completes, the client pauses the torrent, disconnects peers and removes the task from the session and UI without deleting downloaded files.
- Manual removal displays a confirmation and optionally deletes downloaded content; source `.torrent` deletion after completion is configurable.

## Build verification and provenance

The Windows CI does **not** package the ordinary stock `libtorrent` wheel. It compiles the pinned upstream revision with both Python source transformations applied. The pipeline:

1. Builds or retrieves a verified patched libtorrent wheel from the Windows cache.
2. Confirms patched markers and stages the exact binary outside PyInstaller's working directory.
3. Builds the onedir GUI and restores/compares the exact verified libtorrent binary in the package.
4. Adds third-party notices, patcher scripts and `PATCHED_LIBTORRENT_BUILD.txt` containing upstream revision, transformation hashes and binary SHA-256 hashes.
5. Performs executable smoke checks and uploads an Actions artifact.
6. For `vMAJOR.MINOR.PATCH` tags, attaches the verified Windows ZIP to the GitHub Release.

The **source transformations are Python scripts**, not `patches/libtorrent-no-piece-upload.patch`: that historical file path does not exist in the repository. The release includes the transformation scripts under `LICENSES/`.

For exact local build commands, workflow triggers and tests, see the [development guide](DEVELOPMENT.md).

## Licensing, tracker rules and copyright

The application's own code uses [MIT](../LICENSE), while libtorrent, Qt/PySide6, Boost, OpenSSL and the bundled Python runtime carry their separate terms. Consult [third-party notices](../THIRD_PARTY_NOTICES.md) and the [Qt source offer](../QT_LGPL_SOURCE_OFFER.md).

Private trackers may forbid download-only use and may require approved clients, ratios or post-download seeding. This client is not intended to evade those requirements. Users are responsible for obtaining content lawfully.
