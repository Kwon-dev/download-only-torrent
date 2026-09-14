# Download Only Torrent

A small Windows BitTorrent client focused on **download-only use**. It is built with Python, PySide6 and libtorrent.

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
- Configurable listen port; first launch automatically chooses a currently unused TCP/UDP port
- DHT, PEX, LSD, TCP and uTP toggles
- Active download/torrent queue limits disabled so the app does not impose an artificial simultaneous-download cap
- Adjustable row height and persistent column widths
- Active downloads are persisted and restored after app restart
- Progress, download speed, connected peers and piece-payload-upload counters
- Diagnostic Properties window with tracker, DHT, listen-port and recent libtorrent alert information
- Seeding is disabled by policy
- Session unchoke slots are set to `0`
- The libtorrent local peer class is changed so LAN peers do not bypass unchoke-slot limits
- A runtime guard aborts a torrent if libtorrent ever reports non-zero BitTorrent piece payload upload
- As soon as all wanted files are complete, the torrent is paused, peers are disconnected, and it is removed from the session and GUI
- Manual removal asks for confirmation and optionally deletes downloaded data
- Optional automatic deletion of the original `.torrent` file after completion (enabled by default)
- Dark / light theme, Korean / English UI, system tray, completion notifications, and optional Windows startup
- Custom Windows application / tray / executable icon
- GitHub Actions builds a Windows release archive automatically

> **Important:** "download only" here means zero intended **BitTorrent piece payload upload**. Normal networking still requires outbound protocol traffic such as tracker/DHT requests, BitTorrent handshakes, request messages and TCP acknowledgements. The app does not and cannot make total outbound network traffic equal to zero while downloading.

## Keyboard shortcuts

- `Ctrl+O` — add `.torrent` files (multi-select supported)
- `Ctrl+M` — add magnet link
- `Delete` — remove selected torrent(s)
- `Space` — pause/resume selected torrent(s)
- `Ctrl+A` — select all rows
- `Alt+Enter` — properties / diagnostics
- `Ctrl+,` — settings
- `Ctrl++` / `Ctrl+-` — increase/decrease row height

## Requirements for source mode

- Windows 10/11 x64
- Python 3.11 x64

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Build locally

```powershell
.\build.ps1
```

The application is written to:

```text
dist\DownloadOnlyTorrent\DownloadOnlyTorrent.exe
```

Keep the entire `dist\DownloadOnlyTorrent` directory together when distributing it. The build intentionally uses PyInstaller **onedir** mode so Qt/PySide6 shared libraries remain separately replaceable for LGPL compliance.

## Automatic Windows build

`.github/workflows/windows-build.yml` runs on pull requests and pushes to `main`. It builds an onedir Windows application, includes the applicable license/source-offer files, smoke-tests the executable, then uploads a ZIP artifact for 14 days.

Pushing a tag beginning with `v` also creates a GitHub Release and attaches the ZIP:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

## Download behavior

For `.torrent` input, file priorities are set before the torrent is added. For magnet input, libtorrent's `default_dont_download` flag is used so no file is wanted while metadata is being fetched; after the user chooses files, only those files receive a normal download priority.

BitTorrent operates on pieces rather than exact file byte ranges. If two files share a boundary piece, libtorrent may need to fetch the whole piece even when one neighboring file is unchecked. This is normal BitTorrent behavior.

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
- libtorrent under the BSD license and additional bundled notices.
- Python under the Python Software Foundation license.
- PyInstaller as the packaging tool under its license and executable-bundling exception.

See `THIRD_PARTY_NOTICES.md`, `QT_LGPL_SOURCE_OFFER.md`, and `LICENSES/` for details. Release ZIPs include the GNU LGPLv3/GPLv3 texts, libtorrent notices, and the Python runtime license.

The onedir release format is intentional: Qt/PySide6 DLLs remain separate and may be replaced with compatible modified versions. Nothing in this project's license is intended to prohibit LGPL-permitted debugging, reverse engineering, relinking, or replacement of those libraries.

This repository can be operated publicly, but users remain responsible for copyright law, tracker/private-site rules, and the licenses of content they download. A download-only client does not make unauthorized distribution or downloading lawful.

## CI note

The project pins `libtorrent==2.1.1`, `PySide6==6.9.2`, and Python 3.11 for the Windows workflow. CI performs syntax checks, builds the onedir GUI app, verifies the embedded Windows icon, copies legal notices/license texts, smoke-tests `--version`, and publishes a ZIP artifact.
