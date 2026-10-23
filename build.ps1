$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path $PSScriptRoot).Path
Push-Location $repoRoot
try {
    python -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw 'Python build tooling installation failed' }
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python runtime dependency installation failed' }
    python -m pip install pyinstaller pillow pefile
    if ($LASTEXITCODE -ne 0) { throw 'Packaging dependency installation failed' }

    # The build installs and checks a custom patched libtorrent Python binding.
    & .\tools\build_patched_libtorrent.ps1 -Python python
    if ($LASTEXITCODE -ne 0) { throw 'Patched libtorrent build failed' }
    python tools\verify_patched_libtorrent.py
    if ($LASTEXITCODE -ne 0) { throw 'Patched libtorrent verification failed' }

    $workRoot = Join-Path $repoRoot '.build-deps'
    $stageDir = Join-Path $workRoot 'patched-libtorrent-stage'
    $cacheDir = $env:PATCHED_LIBTORRENT_CACHE
    if ([string]::IsNullOrWhiteSpace($cacheDir)) {
        $cacheDir = Join-Path $workRoot 'artifact-cache'
    }

    # Keep the verified binary outside the PyInstaller work directory.
    python tools\finalize_patched_libtorrent.py stage --stage-dir $stageDir
    if ($LASTEXITCODE -ne 0) { throw 'Staging patched libtorrent failed' }
    python tools\generate_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    python -m compileall -q app.py download_only_torrent tools
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed' }

    pyinstaller --noconfirm --clean --onedir --windowed --noupx --name DownloadOnlyTorrent --icon assets\app.ico --collect-all libtorrent app.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

    $appDir = Join-Path $repoRoot 'dist\DownloadOnlyTorrent'
    python tools\finalize_patched_libtorrent.py finalize --stage-dir $stageDir --dist-dir $appDir
    if ($LASTEXITCODE -ne 0) { throw 'Final patched libtorrent verification failed' }
    python tools\package_release_metadata.py --app-dir $appDir --cache-dir $cacheDir
    if ($LASTEXITCODE -ne 0) { throw 'License/provenance packaging failed' }

    Write-Host 'Built: dist\DownloadOnlyTorrent\DownloadOnlyTorrent.exe'
    Write-Host 'Keep the entire dist\DownloadOnlyTorrent directory together when distributing.'
}
finally {
    Pop-Location
}
