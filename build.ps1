$ErrorActionPreference = 'Stop'

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pillow pefile setuptools wheel

# Build libtorrent 2.1.1 from source with the PIECE payload send path removed.
# This replaces any stock libtorrent module in the active Python environment.
& .\tools\build_patched_libtorrent.ps1 -Python python

python tools/generate_icon.py
python -m compileall -q app.py download_only_torrent tools
python tools/verify_patched_libtorrent.py

pyinstaller --noconfirm --clean --onedir --windowed --name DownloadOnlyTorrent --icon assets/app.ico --collect-all libtorrent app.py

$app = ".\dist\DownloadOnlyTorrent"
$workRoot = if ($env:RUNNER_TEMP) {
    Join-Path $env:RUNNER_TEMP "download-only-torrent-deps"
} else {
    Join-Path (Resolve-Path .).Path ".build-deps"
}
$boostRoot = Join-Path $workRoot "boost"
$libtorrentRoot = Join-Path $workRoot "libtorrent"

$vcpkgRoot = $env:VCPKG_ROOT
if ([string]::IsNullOrWhiteSpace($vcpkgRoot)) { $vcpkgRoot = $env:VCPKG_INSTALLATION_ROOT }
if ([string]::IsNullOrWhiteSpace($vcpkgRoot) -and (Test-Path "C:\vcpkg\vcpkg.exe")) { $vcpkgRoot = "C:\vcpkg" }
$opensslRoot = Join-Path $vcpkgRoot "installed\x64-windows-static-md"

python tools/package_release_metadata.py `
  --app-dir $app `
  --boost-root $boostRoot `
  --openssl-root $opensslRoot `
  --libtorrent-source $libtorrentRoot

Write-Host "Built: dist\DownloadOnlyTorrent\DownloadOnlyTorrent.exe"
Write-Host "Keep the whole dist\DownloadOnlyTorrent folder together when distributing."
