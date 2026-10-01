# Download Only Torrent

A small Windows BitTorrent client focused on **download-only use**. It is built with Python, PySide6 and a patched libtorrent.

## Features

- Native Windows GUI with PySide6
- Open one or many `.torrent` files at once
- Paste magnet links, or open `magnet:` links from a browser
- Windows `.torrent` file association and magnet protocol integration
- Single-instance forwarding: shell/browser opens are sent to the already-running app
- Magnet metadata is fetched first, then the file list is shown
- Per-file checkbox selection before downloading
- File-selection list sorting by **name or size** by clicking the header
- Main download list sorting by **name, progress, download speed, piece upload, peers, state, or save path**
- Sort direction/state is remembered between launches
- Shift/Ctrl/mouse-drag multi-row selection in the main list
- Batch pause / resume / remove and keyboard shortcuts
- Configurable download folder and download speed limit
- Settings split into General and Advanced tabs; Advanced holds the peer strategies, interface binding, DHT/PEX/LSD/TCP/uTP, outstanding requests per peer (default 1500; libtorrent's is 500), peer connect timeout (default 7 s; libtorrent's is 15 s) and the extra tracker list
- Configurable listen port; first launch automatically chooses a currently unused TCP/UDP port
- Listens and announces only on the default-route address (not on VPN, Hyper-V/WSL or loopback adapters), following network changes; can be switched back to all interfaces
- Status bar shows whether the listen port is reachable (incoming connections, UPnP/NAT-PMP mapping), the average download rate since start and how many peer connections are still being set up
- Peer pane under the download list (like µTorrent's): every peer of the selected download with client, status (receiving / choking us / unchoked but idle / connecting), flags, progress, download speed, amount received and discovery source; sortable, resizable, remembered between launches
- Optional extra public trackers added to every non-private torrent (editable list, on by default; never added to private torrents)
- DHT, PEX, LSD, TCP and uTP toggles
- Active download/torrent queue limits disabled so the app does not impose an artificial simultaneous-download cap
- Adjustable row height and persistent column widths
- Active downloads are persisted and restored after app restart, using libtorrent resume data so already-downloaded pieces are not re-hashed and magnet links do not need to fetch metadata again
- A private copy of each added `.torrent` file is kept, so a download survives the original file being deleted (for example from a browser download cache); entries that still cannot be restored are kept and reported instead of being dropped
- Progress, download speed, connected peers and piece-payload-upload counters
- Diagnostic Properties window per torrent (peer list with seed/choke flags, disconnect reasons, tracker status, alerts) and a session-wide Diagnostics window (`Ctrl+D`)
- Restored downloads without resume data are checked one at a time instead of all at once, with multi-threaded hashing
- Seeding is disabled by policy
- Session unchoke slots are set to `0`
- BEP 6 "allowed fast" pieces are never offered (`allowed_fast_set_size = 0`), so choked peers have no path to request piece payload and are not disconnected for trying
- The libtorrent local peer class is changed so LAN peers do not bypass unchoke-slot limits
- **Release builds compile a patched libtorrent 2.1.1 in which `bt_peer_connection::write_piece()` no longer contains the code that queues BitTorrent PIECE payload bytes for transmission**
- If that removed upload path is nevertheless entered, the patched libtorrent logs a build marker and disconnects the peer immediately
- CI refuses to package a libtorrent module unless the compiled hard-disable marker is present
- A runtime guard additionally aborts a torrent if libtorrent ever reports non-zero BitTorrent piece payload upload
- As soon as all wanted files are complete, the torrent is paused, peers are disconnected, and it is removed from the session and GUI
- Manual removal asks for confirmation and optionally deletes downloaded data
- Optional automatic deletion of the original `.torrent` file after completion (enabled by default)
- Dark / light theme, Korean / English UI, system tray, completion notifications, and optional Windows startup
- Custom Windows application / tray / executable icon
- GitHub Actions builds a Windows release archive automatically

> **Important:** "download only" here refers to BitTorrent **file piece payload**. Normal networking still requires outbound protocol/control traffic such as tracker/DHT requests, BitTorrent handshakes, request messages and TCP acknowledgements. The app does not and cannot make total outbound network traffic equal to zero while downloading.

## Hard-disabled libtorrent build

Official Windows builds do **not** use the stock PyPI `libtorrent` wheel. The build process:

1. checks out upstream libtorrent `v2.1.1` (`56ae8caba38bf154ffc210403cb23f91d0ecaa49`),
2. applies `patches/libtorrent-no-piece-upload.patch`,
3. builds the Python binding from source,
4. verifies the compiled module contains `DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED`,
5. verifies the packaged `.pyd` contains the same marker before publishing.

The patch removes the upstream code in `bt_peer_connection::write_piece()` that constructs a PIECE message and appends the requested disk buffer to the socket send queue. This is intentionally redundant with the zero-unchoke policy and runtime payload counter guard.

Each release directory also contains `PATCHED_LIBTORRENT_BUILD.txt` with the upstream revision, patch hash, compiled libtorrent SHA-256, and application EXE SHA-256.

This design provides strong technical evidence that the distributed binary was built without libtorrent's normal BitTorrent piece-payload send path. It is still not a claim that the application sends zero network bytes of every kind.

## Keyboard shortcuts

- `Ctrl+O` — add `.torrent` files (multi-select supported)
- `Ctrl+M` — add magnet link
- `Delete` — remove selected torrent(s)
- `Space` — pause/resume selected torrent(s)
- `Ctrl+A` — select all rows
- `Alt+Enter` — properties / diagnostics
- `Ctrl+D` — session-wide diagnostics
- `Ctrl+,` — settings
- `Ctrl++` / `Ctrl+-` — increase/decrease row height

## Requirements for source mode

- Windows 10/11 x64
- Python 3.11 x64
- Visual Studio C++ build tools
- vcpkg (`VCPKG_ROOT` or `VCPKG_INSTALLATION_ROOT` set; GitHub-hosted Windows runners already provide it)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\tools\build_patched_libtorrent.ps1 -Python python
python app.py
```

The supported source-mode instructions intentionally build the same hard-disabled libtorrent variant used by CI instead of installing the stock PyPI libtorrent wheel.

## Build locally

```powershell
.\build.ps1
```

The application is written to:

```text
dist\DownloadOnlyTorrent\DownloadOnlyTorrent.exe
```

Keep the entire `dist\DownloadOnlyTorrent` directory together when distributing it. The build intentionally uses PyInstaller **onedir** mode so Qt/PySide6 shared libraries remain separately replaceable for LGPL compliance.

## Tests

`tests/` holds a pytest suite that drives the real engine and main window (offscreen Qt) against local libtorrent sessions: resume/restore, the check queue, extra trackers, peer strategies, listen-address selection and the diagnostics views. It uses the stock libtorrent wheel, so it checks the application logic; the piece-upload patch is verified by the Windows build.

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest tests
```

`.github/workflows/tests.yml` runs these on every branch push (about two minutes on Linux).

## Automatic Windows build

`.github/workflows/windows-build.yml` runs on pushes to `main`, on `v*` tags, every four days on `main` (so the cached patched-libtorrent wheel is not evicted after GitHub's 7 days of inactivity), and on demand from the Actions tab. Branches and pull requests run only the Linux tests. It builds the patched libtorrent from source, verifies the hard-disable marker, builds an onedir Windows application, includes the applicable license/source-offer and build-provenance files, smoke-tests the executable, then uploads an artifact for 14 days.

Pushing a tag beginning with `v` also creates or updates the corresponding GitHub Release and attaches one Windows ZIP:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

## Download behavior

For `.torrent` input, file priorities are set before the torrent is added. For magnet input, libtorrent's `default_dont_download` flag is used so no file is wanted while metadata is being fetched; after the user chooses files, only those files receive a normal download priority.

BitTorrent operates on pieces rather than exact file byte ranges. If two files share a boundary piece, libtorrent may need to fetch the whole piece even when one neighboring file is unchecked. This is normal BitTorrent behavior.

## Private trackers and community rules

Many private trackers enforce upload-ratio, minimum-seeding or hit-and-run rules and may restrict which client implementations or versions are allowed. This client intentionally does not transmit BitTorrent file-piece payload and removes completed torrents instead of seeding them, so it cannot contribute normal upload ratio or post-download seed time.

Do not use this client on a private tracker unless that tracker's rules explicitly permit this behavior and the client/version is allowed. This project is not intended to bypass tracker rules, ratio requirements, client whitelists, or other community policies.

## Completion behavior

When all wanted data is finished, the app immediately:

1. pauses the torrent,
2. disconnects and clears peers,
3. removes the torrent from the session,
4. removes it from the GUI and restart-persistence state,
5. optionally deletes the source `.torrent` file,
6. keeps downloaded files intact.

There is no post-download seeding period.

## Removal behavior

Manual removal always shows a confirmation dialog. By default it removes only the torrent task and keeps downloaded data. The dialog contains a checkbox to also delete downloaded data using libtorrent's delete-files removal option.

## Licensing and public repository use

The application's own source code is released under the **MIT License**; see `LICENSE`.

The project uses third-party software under separate licenses, most notably:

- PySide6 / Qt under LGPLv3/GPLv3/commercial licensing options; this project uses the Community Edition under LGPLv3 for the Qt libraries it distributes.
- a modified libtorrent 2.1.1 under its BSD license and bundled notices; the modification is provided as `patches/libtorrent-no-piece-upload.patch`.
- Boost libraries used to build/link the custom libtorrent Python binding under the Boost Software License 1.0.
- OpenSSL used by the custom libtorrent build for HTTPS tracker/SSL support under the license distributed with the exact vcpkg package used by CI.
- Python under the Python Software Foundation license.
- PyInstaller as the packaging tool under its license and executable-bundling exception.

See `THIRD_PARTY_NOTICES.md`, `QT_LGPL_SOURCE_OFFER.md`, and `LICENSES/` in release packages for details. Release packages include the Qt/PySide6 LGPL/GPL texts from deterministic pinned sources, libtorrent notices and patch, Boost/OpenSSL notices, and the Python runtime license.

The onedir release format is intentional: Qt/PySide6 DLLs remain separate and may be replaced with compatible modified versions. Nothing in this project's license is intended to prohibit LGPL-permitted debugging, reverse engineering, relinking, or replacement of those libraries.

This repository can be operated publicly, but users remain responsible for copyright law, tracker/private-site rules, and the licenses of content they download. A download-only client does not make unauthorized distribution or downloading lawful.

## CI note

The project pins upstream libtorrent `v2.1.1`, Boost `1.91.0`, PySide6 `6.9.2`, and Python 3.11 for the Windows workflow. CI builds and verifies the patched libtorrent, performs syntax checks, builds the onedir GUI app, verifies the embedded Windows icon and packaged libtorrent marker, packages legal/provenance files, smoke-tests `--version`, and publishes the artifact.
