# Download Only Torrent

A small Windows BitTorrent client focused on **download-only use**. It is built with Python, PySide6 and libtorrent.

## Features

- Native Windows GUI with PySide6
- Open `.torrent` files or paste magnet links
- Magnet metadata is fetched first, then the file list is shown
- Per-file checkbox selection before downloading
- Select all / clear all controls
- Configurable download folder and download speed limit
- DHT, PEX, LSD, TCP and uTP toggles
- Pause / resume / remove
- Progress, download speed, connected peers and piece-payload-upload counters
- Seeding is disabled by policy
- Each torrent is created with `max_uploads = 0`
- Session unchoke slots are set to `0`
- The libtorrent local peer class is changed so LAN peers do not bypass unchoke-slot limits
- A runtime guard aborts a torrent if libtorrent ever reports non-zero BitTorrent piece payload upload
- As soon as all wanted files are complete, the torrent is paused, peers are disconnected, and it is removed from the session
- Optional automatic deletion of the original `.torrent` file after completion (enabled by default)
- Dark / light theme, system tray, completion notifications, and optional Windows startup
- GitHub Actions builds a standalone Windows `.exe` automatically

> **Important:** "download only" here means zero intended **BitTorrent piece payload upload**. Normal networking still requires outbound protocol traffic such as tracker/DHT requests, BitTorrent handshakes, request messages and TCP acknowledgements. The app does not and cannot make total outbound network traffic equal to zero while downloading.

## Requirements for source mode

- Windows 10/11 x64
- Python 3.11 x64

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Build the EXE locally

```powershell
.\build.ps1
```

The result is written to:

```text
dist\DownloadOnlyTorrent.exe
```

## Automatic Windows build

`.github/workflows/windows-build.yml` runs on pull requests and pushes to `main`, then uploads `DownloadOnlyTorrent.exe` as a GitHub Actions artifact for 14 days.

Pushing a tag beginning with `v` also creates a GitHub Release and attaches the EXE:

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
4. removes it from the GUI,
5. optionally deletes the source `.torrent` file,
6. keeps downloaded files intact.

There is no post-download seeding period.

## CI note

The project pins `libtorrent==2.1.1` with Python 3.11 for the Windows build workflow. GitHub Actions installs dependencies, performs a syntax check, builds a one-file GUI executable with PyInstaller, smoke-tests `--version`, then uploads the EXE artifact.
