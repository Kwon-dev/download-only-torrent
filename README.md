# Download Only Torrent

A lightweight, open-source **Windows BitTorrent client focused on downloading files without uploading BitTorrent file-piece payloads**.

[English](README.md) · [한국어](README.ko.md)

[![Tests](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/tests.yml/badge.svg)](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/tests.yml)
[![Windows build](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/windows-build.yml/badge.svg)](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/windows-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Windows 10/11 (x64)** · Python + PySide6 · Patched libtorrent 2.1.1 · English / 한국어

> **What “download-only” means:** Official Windows builds remove libtorrent's normal BitTorrent PIECE payload sending path and enforce additional safeguards. The client **still sends protocol/control traffic** (for example, tracker/DHT queries, handshakes, piece requests and TCP acknowledgements). It is **not** a zero-upload-bandwidth or anonymity tool.

## Download and run

1. Open the [latest release](https://github.com/Kwon-dev/download-only-torrent/releases/latest).
2. Download the **DownloadOnlyTorrent-windows-x64-…zip** asset. If the newest release has no ZIP yet, its Windows release workflow may still be running; check [Actions](https://github.com/Kwon-dev/download-only-torrent/actions/workflows/windows-build.yml).
3. Extract the **entire** ZIP into a folder.
4. Run `DownloadOnlyTorrent.exe` inside the extracted folder. Keep the other files and folders beside it; this is a portable, **onedir** build.

You do **not** need Python, Visual Studio or vcpkg to run a published Windows release. Those are only for building from source.

## Why use it?

| Feature | What it does |
| --- | --- |
| **Download-only piece policy** | Uses a patched libtorrent build and verification checks to disable BitTorrent file-piece payload uploads. |
| **Pick only what you need** | Preview torrent or magnet contents and select individual files before starting. |
| **Small-file filter** | Optionally uncheck files at or below your chosen size threshold, useful for skipping extras. |
| **Resume after restart** | Persists active tasks and libtorrent resume data, reducing unnecessary rechecking. |
| **Desktop-friendly controls** | Multiple torrents, queue actions, sorting, peer diagnostics, tray integration and notifications. |
| **Network settings** | Configurable speed, peer limits, listening interface, IPv6, discovery and extra trackers. |

Supports `.torrent` files, magnet links, Windows file/protocol associations, light/dark themes and English/Korean UI.

## Getting started

1. Click **Add .torrent** to choose one or more torrent files, or **Add magnet** to paste a magnet URI. You can also open associated links/files from Windows.
2. In the file selection dialog, review the files and adjust their checkboxes. Choose a destination.
3. Start the download. The main window shows progress, peers and download speed.
4. When all **selected** files finish, the client removes the completed torrent task from its session while keeping the downloaded files.

### Skip small files automatically

Go to **Settings → General → File size filter** and enable **Skip files at or below the limit**. Enter a value such as **10 MB**.

- The filter is **off by default** and remembers its setting.
- Files **at or below** the threshold are initially unchecked; larger files remain selected.
- **1 MB = 1,000,000 bytes** for this setting.
- It applies when creating a **new** file selection from a torrent or magnet, not retroactively to downloads already added.
- You can manually reselect an excluded file in the preview.

**Note:** BitTorrent downloads data in pieces, which sometimes cross file boundaries. Small amounts of data belonging to an unchecked neighboring file may be transferred as part of a shared piece.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Add one or more `.torrent` files |
| `Ctrl+M` | Add a magnet link |
| `Space` | Pause/resume selected torrents |
| `Delete` | Remove selected torrents (confirmation shown) |
| `Ctrl+A` | Select all rows |
| `Alt+Enter` | Torrent properties / diagnostics |
| `Ctrl+D` | Session diagnostics |
| `Ctrl+,` | Settings |
| `Ctrl++` / `Ctrl+-` | Adjust row height |

## Important limitations

- **No seeding / piece-payload uploads:** This program is intentionally incompatible with ordinary post-download seeding and ratio-building.
- **Private trackers:** Many require an approved client, seeding time or upload ratio. **Do not use this client where those rules prohibit its behavior.** It is not intended to bypass community rules.
- **Not total traffic suppression:** Network and protocol-control bytes still leave your computer.
- **Copyright:** Only download content you have the right to access and use.

For exact safeguards, design decisions and build verification, read the [technical documentation](docs/TECHNICAL.md).

## Developers and contributors

- [Development guide — build, tests and CI](docs/DEVELOPMENT.md)
- [Technical architecture and download-only policy](docs/TECHNICAL.md)
- [Issue tracker](https://github.com/Kwon-dev/download-only-torrent/issues)
- [Source code](https://github.com/Kwon-dev/download-only-torrent)

Bug reports should include the release tag/build number, Windows version and clear reproduction steps. For a potential security issue, avoid publishing secrets or sensitive data in an issue.

## License

The application's original source is licensed under [MIT](LICENSE). Distributed dependencies keep their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md), [Qt/PySide6 source offer](QT_LGPL_SOURCE_OFFER.md) and [LICENSES](LICENSES).

Official packages include dependency notices, the source-transformation scripts and `PATCHED_LIBTORRENT_BUILD.txt` with build provenance and hashes.

