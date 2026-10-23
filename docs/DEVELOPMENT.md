# Development guide

[← README](../README.md) · [한국어 README](../README.ko.md) · [Technical design](TECHNICAL.md)

The GitHub [Releases](https://github.com/Kwon-dev/download-only-torrent/releases) page provides prebuilt Windows ZIP archives. **The requirements below are for contributors building from source**, not for users running a release.

## Requirements for Windows source builds

- Windows 10/11 x64
- Python **3.11 x64**, pip and PowerShell
- Git
- Visual Studio C++ build tools / MSBuild
- vcpkg with `VCPKG_ROOT` or `VCPKG_INSTALLATION_ROOT` set (a `C:\vcpkg` installation is also detected)
- Network access to fetch pinned upstream sources/dependencies on a fresh build

Windows CI uses `windows-2022`; the version pins and build options are recorded in [`tools/libtorrent_build_manifest.json`](../tools/libtorrent_build_manifest.json). The modified libtorrent build can be resource intensive on a cold cache.

## Run from source (Windows PowerShell)

```powershell
git clone https://github.com/Kwon-dev/download-only-torrent.git
cd download-only-torrent

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\tools\build_patched_libtorrent.ps1 -Python python
python app.py
```

**Do not substitute the ordinary PyPI libtorrent wheel** when validating the official download-only piece-payload policy. Source mode intentionally builds and verifies the patched libtorrent version.

## Build the Windows app

In a Python 3.11 environment with the dependencies above:

```powershell
.\build.ps1
```

The script builds/verifies the patched libtorrent module, packages the GUI and associated licenses/provenance, and writes the application to:

```text
dist\DownloadOnlyTorrent\DownloadOnlyTorrent.exe
```

Keep the entire `dist\DownloadOnlyTorrent` folder together. Its Qt/PySide6 shared libraries remain separately replaceable for LGPL compliance.

## Tests

The test suite uses **stock libtorrent** to exercise application behavior (it does not replace the Windows patched-binary checks).

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```

The example above uses POSIX shell syntax. In PowerShell, set `$env:QT_QPA_PLATFORM = 'offscreen'` before invoking pytest. Tests cover torrent state, resume/restore, peer behavior, network settings, UI/file-selection behavior and patch transformations.

## Continuous integration and releases

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| [Tests](../.github/workflows/tests.yml) | Pushes to branches (including `main`), or manual dispatch | Python syntax check and Linux pytest |
| [Windows EXE](../.github/workflows/windows-build.yml) | Push to `main`, `v*` tags, four-day schedule, or manual dispatch | Verify patched libtorrent, package Windows EXE and upload 14-day artifact |
| Release job | Only a `v*` tag | Publish the Windows ZIP to the GitHub Release |

To publish a **new** version, choose a tag not already used, then push it after verifying the main branch:

```powershell
git checkout main
git pull --ff-only
git tag v1.2.6
git push origin v1.2.6
```

The tag shown is an **example**, not a statement that `v1.2.6` already exists or should be used without checking. The Windows tag workflow derives the packaged `--version` display from the semantic-version release tag; it does not modify your committed source file or historic release archives.

A release may appear before its ZIP asset is attached. Check the **Windows EXE** Actions run for success. Do not distribute a failed or partial build.

## Reporting bugs and contributing

1. Search [existing issues](https://github.com/Kwon-dev/download-only-torrent/issues) and describe the expected vs. actual result.
2. Include the release tag/build number, Windows version and concise reproduction steps. Screenshots are useful if they contain no private tracker credentials or other secrets.
3. For changes, use a focused branch, add regression tests when possible, and open a pull request.
4. Explain how you verified the change, especially for networking, file priorities or persistence.

## License and release compliance

Application code is [MIT](../LICENSE); bundled third-party components retain their licenses. The build includes [notices](../THIRD_PARTY_NOTICES.md), the [Qt/PySide6 LGPL source offer](../QT_LGPL_SOURCE_OFFER.md), and exact patcher scripts in the packaged `LICENSES` folder.

When changing the patched libtorrent build, update the transformation scripts, verification markers, provenance generation and tests together. The goal is a reproducible **download-only file-piece payload** policy, not a claim of zero network upload bytes.
