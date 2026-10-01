param(
    [string]$Python = "python",
    [string]$WorkRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$manifestPath = Join-Path $repoRoot "tools\libtorrent_build_manifest.json"
$manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json

$libtorrentVersion = [string]$manifest.libtorrent.version
$libtorrentTag = [string]$manifest.libtorrent.tag
$expectedRevision = [string]$manifest.libtorrent.commit
$boostTag = [string]$manifest.boost.tag
$triplet = [string]$manifest.vcpkg.triplet
$b2BaseArgs = (@($manifest.b2_args) -join " ")

if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    if ($env:RUNNER_TEMP) {
        $WorkRoot = Join-Path $env:RUNNER_TEMP "download-only-torrent-deps"
    } else {
        $WorkRoot = Join-Path $repoRoot ".build-deps"
    }
}
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
$WorkRoot = (Resolve-Path $WorkRoot).Path

$cacheDir = $env:PATCHED_LIBTORRENT_CACHE
if ([string]::IsNullOrWhiteSpace($cacheDir)) {
    $cacheDir = Join-Path $WorkRoot "artifact-cache"
}
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
$cacheDir = (Resolve-Path $cacheDir).Path
$licenseCacheDir = Join-Path $cacheDir "licenses"

$libtorrentDir = Join-Path $WorkRoot "libtorrent"
$boostDir = Join-Path $WorkRoot "boost"
$patcher = Join-Path $repoRoot "tools\patch_libtorrent_no_piece_upload.py"
$turnoverPatcher = Join-Path $repoRoot "tools\patch_libtorrent_peer_turnover.py"
$wheelPattern = "libtorrent-$libtorrentVersion-*.whl"

Write-Host "Dependency workspace: $WorkRoot"
Write-Host "Patched libtorrent artifact cache: $cacheDir"

$cachedWheel = Get-ChildItem -Path $cacheDir -Filter $wheelPattern -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$cachedBoostLicense = Join-Path $licenseCacheDir "Boost-1.0.txt"
$cachedOpenSslLicense = Join-Path $licenseCacheDir "OpenSSL.txt"
$cacheComplete = $null -ne $cachedWheel -and
    (Test-Path $cachedBoostLicense) -and
    (Test-Path $cachedOpenSslLicense)

if ($cacheComplete) {
    Write-Host "Using cached patched libtorrent wheel: $($cachedWheel.FullName)"
    & $Python -m pip install --force-reinstall --no-deps $cachedWheel.FullName
    if ($LASTEXITCODE -ne 0) { throw "cached patched libtorrent wheel installation failed" }

    & $Python (Join-Path $repoRoot "tools\verify_patched_libtorrent.py")
    if ($LASTEXITCODE -ne 0) { throw "cached patched libtorrent verification failed" }

    Write-Host "Cached patched libtorrent $libtorrentVersion is installed and verified; source build skipped."
    exit 0
}

if ($cachedWheel) {
    Write-Warning "Patched wheel cache is incomplete (license bundle missing); rebuilding instead of trusting a partial cache."
}

if (Test-Path $libtorrentDir) {
    git -C $libtorrentDir reset --hard | Out-Host
    git -C $libtorrentDir clean -xfd | Out-Host
    git -C $libtorrentDir fetch --depth=1 origin tag $libtorrentTag --force | Out-Host
    git -C $libtorrentDir checkout --force $libtorrentTag | Out-Host
} else {
    git clone --depth=1 --branch $libtorrentTag https://github.com/arvidn/libtorrent.git $libtorrentDir | Out-Host
}
if ($LASTEXITCODE -ne 0) { throw "libtorrent $libtorrentTag checkout failed" }

$actualRevision = (git -C $libtorrentDir rev-parse HEAD).Trim()
if ($actualRevision -ne $expectedRevision) {
    throw "unexpected libtorrent $libtorrentTag revision: $actualRevision"
}

git -C $libtorrentDir submodule sync --recursive | Out-Host
if ($LASTEXITCODE -ne 0) { throw "libtorrent submodule sync failed" }
git -C $libtorrentDir submodule update --init --recursive --depth=1 -- deps/try_signal deps/libdatachannel | Out-Host
if ($LASTEXITCODE -ne 0) { throw "libtorrent dependency submodule initialization failed" }

$patchedSource = Join-Path $libtorrentDir "src\bt_peer_connection.cpp"
& $Python $patcher $patchedSource
if ($LASTEXITCODE -ne 0) { throw "libtorrent source hardening failed" }

$turnoverSource = Join-Path $libtorrentDir "src\torrent.cpp"
& $Python $turnoverPatcher $turnoverSource
if ($LASTEXITCODE -ne 0) { throw "libtorrent peer turnover patch failed" }

if (-not (Test-Path $boostDir)) {
    git clone --depth=1 --recurse-submodules -j10 --branch $boostTag https://github.com/boostorg/boost.git $boostDir | Out-Host
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
$b2Args = "$b2BaseArgs openssl-include=$opensslInclude openssl-lib=$opensslLib"

Push-Location (Join-Path $libtorrentDir "bindings\python")
try {
    & $Python setup.py build_ext --b2-args $b2Args bdist_wheel
    if ($LASTEXITCODE -ne 0) { throw "patched libtorrent wheel build failed" }

    $wheel = Get-ChildItem -Path .\dist -Filter $wheelPattern |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $wheel) { throw "patched libtorrent wheel was not produced" }

    Write-Host "Installing patched wheel: $($wheel.FullName)"
    & $Python -m pip install --force-reinstall --no-deps $wheel.FullName
    if ($LASTEXITCODE -ne 0) { throw "patched libtorrent wheel installation failed" }
} finally {
    Pop-Location
}

& $Python (Join-Path $repoRoot "tools\verify_patched_libtorrent.py")
if ($LASTEXITCODE -ne 0) { throw "patched libtorrent verification failed" }

New-Item -ItemType Directory -Force -Path $licenseCacheDir | Out-Null
Get-ChildItem -Path $cacheDir -Filter $wheelPattern -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item $wheel.FullName (Join-Path $cacheDir $wheel.Name) -Force
Copy-Item (Join-Path $boostDir "LICENSE_1_0.txt") $cachedBoostLicense -Force

$opensslLicenseCandidates = @(
    (Join-Path $opensslRoot "share\openssl\copyright"),
    (Join-Path $opensslRoot "LICENSE.txt"),
    (Join-Path $opensslRoot "LICENSE")
)
$opensslLicense = $opensslLicenseCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $opensslLicense) {
    throw "OpenSSL license not found under $opensslRoot"
}
Copy-Item $opensslLicense $cachedOpenSslLicense -Force
Copy-Item $manifestPath (Join-Path $cacheDir "libtorrent_build_manifest.json") -Force

Write-Host "Patched libtorrent $libtorrentVersion is installed and verified."
Write-Host "Compact reusable cache populated: wheel + Boost/OpenSSL licenses."
