param(
    [string]$Python = "python",
    [string]$WorkRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    if ($env:RUNNER_TEMP) {
        $WorkRoot = Join-Path $env:RUNNER_TEMP "download-only-torrent-deps"
    } else {
        $WorkRoot = Join-Path $repoRoot ".build-deps"
    }
}
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
$WorkRoot = (Resolve-Path $WorkRoot).Path

$libtorrentDir = Join-Path $WorkRoot "libtorrent"
$boostDir = Join-Path $WorkRoot "boost"
$patcher = Join-Path $repoRoot "tools\patch_libtorrent_no_piece_upload.py"

Write-Host "Dependency workspace: $WorkRoot"

if (Test-Path $libtorrentDir) {
    git -C $libtorrentDir reset --hard | Out-Host
    git -C $libtorrentDir clean -xfd | Out-Host
    git -C $libtorrentDir fetch --depth=1 origin tag v2.1.1 --force | Out-Host
    git -C $libtorrentDir checkout --force v2.1.1 | Out-Host
} else {
    git clone --depth=1 --branch v2.1.1 https://github.com/arvidn/libtorrent.git $libtorrentDir | Out-Host
}
if ($LASTEXITCODE -ne 0) { throw "libtorrent v2.1.1 checkout failed" }

$actualRevision = (git -C $libtorrentDir rev-parse HEAD).Trim()
$expectedRevision = "56ae8caba38bf154ffc210403cb23f91d0ecaa49"
if ($actualRevision -ne $expectedRevision) {
    throw "unexpected libtorrent v2.1.1 revision: $actualRevision"
}

# libtorrent's root Jamfile unconditionally loads the try_signal and
# libdatachannel sub-projects, even when WebTorrent is disabled. A shallow
# source clone does not populate those git submodules, so initialize only the
# build-time submodules we need (recursively for their own dependencies).
git -C $libtorrentDir submodule sync --recursive | Out-Host
if ($LASTEXITCODE -ne 0) { throw "libtorrent submodule sync failed" }
git -C $libtorrentDir submodule update --init --recursive --depth=1 -- deps/try_signal deps/libdatachannel | Out-Host
if ($LASTEXITCODE -ne 0) { throw "libtorrent dependency submodule initialization failed" }

$patchedSource = Join-Path $libtorrentDir "src\bt_peer_connection.cpp"
& $Python $patcher $patchedSource
if ($LASTEXITCODE -ne 0) { throw "libtorrent source hardening failed" }

if (-not (Test-Path $boostDir)) {
    git clone --depth=1 --recurse-submodules -j10 --branch boost-1.91.0 https://github.com/boostorg/boost.git $boostDir | Out-Host
}
if ($LASTEXITCODE -ne 0) { throw "Boost checkout failed" }

if (-not (Test-Path (Join-Path $boostDir "b2.exe"))) {
    Push-Location $boostDir
    try {
        cmd /c bootstrap.bat
        if ($LASTEXITCODE -ne 0) { throw "Boost bootstrap failed" }
    } finally {
        Pop-Location
    }
}

Push-Location $boostDir
try {
    & (Join-Path $boostDir "b2.exe") headers
    if ($LASTEXITCODE -ne 0) { throw "Boost header staging failed" }
} finally {
    Pop-Location
}

$vcpkgRoot = $env:VCPKG_ROOT
if ([string]::IsNullOrWhiteSpace($vcpkgRoot)) {
    $vcpkgRoot = $env:VCPKG_INSTALLATION_ROOT
}
if ([string]::IsNullOrWhiteSpace($vcpkgRoot)) {
    $candidate = "C:\vcpkg"
    if (Test-Path (Join-Path $candidate "vcpkg.exe")) {
        $vcpkgRoot = $candidate
    }
}
if ([string]::IsNullOrWhiteSpace($vcpkgRoot) -or -not (Test-Path (Join-Path $vcpkgRoot "vcpkg.exe"))) {
    throw "vcpkg is required to build the patched libtorrent with HTTPS tracker support. Set VCPKG_ROOT."
}

$triplet = "x64-windows-static-md"
& (Join-Path $vcpkgRoot "vcpkg.exe") install "openssl:$triplet"
if ($LASTEXITCODE -ne 0) { throw "vcpkg OpenSSL installation failed" }
$opensslRoot = Join-Path $vcpkgRoot "installed\$triplet"
if (-not (Test-Path (Join-Path $opensslRoot "include\openssl\ssl.h"))) {
    throw "OpenSSL headers not found under $opensslRoot"
}

& $Python -m pip install --upgrade setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Python build dependency installation failed" }

$env:BOOST_ROOT = $boostDir
$env:BOOST_BUILD_PATH = Join-Path $boostDir "tools\build"
$env:PATH = "$boostDir;$env:PATH"

$opensslInclude = (Join-Path $opensslRoot "include").Replace("\", "/")
$opensslLib = (Join-Path $opensslRoot "lib").Replace("\", "/")
$b2Args = "release address-model=64 libtorrent-link=static boost-link=static runtime-link=shared cxxstd=17 crypto=openssl webtorrent=off openssl-include=$opensslInclude openssl-lib=$opensslLib"

Push-Location (Join-Path $libtorrentDir "bindings\python")
try {
    & $Python setup.py build_ext --b2-args $b2Args bdist_wheel
    if ($LASTEXITCODE -ne 0) { throw "patched libtorrent wheel build failed" }

    $wheel = Get-ChildItem -Path .\dist -Filter "libtorrent-2.1.1-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $wheel) { throw "patched libtorrent wheel was not produced" }
    Write-Host "Installing patched wheel: $($wheel.FullName)"
    & $Python -m pip install --force-reinstall --no-deps $wheel.FullName
    if ($LASTEXITCODE -ne 0) { throw "patched libtorrent wheel installation failed" }
} finally {
    Pop-Location
}

& $Python (Join-Path $repoRoot "tools\verify_patched_libtorrent.py")
if ($LASTEXITCODE -ne 0) { throw "patched libtorrent verification failed" }

Write-Host "Patched libtorrent v2.1.1 is installed and verified."
