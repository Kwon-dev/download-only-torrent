# Third-party notices

Download Only Torrent is licensed under the MIT License. The application also uses and/or distributes third-party components under their own licenses.

## Qt for Python / PySide6 6.9.2 and Qt 6.9.x

This project uses the Community Edition of Qt for Python (PySide6), which is available under the GNU Lesser General Public License version 3 (LGPLv3), GNU GPLv3, and commercial licensing options. This distribution relies on the LGPLv3 option for the Qt/PySide6 libraries used by the application.

The Windows release is intentionally packaged as an **onedir** application rather than a single-file bundle. Qt/PySide6 DLLs remain separate from `DownloadOnlyTorrent.exe`, so recipients can replace compatible Qt libraries with modified versions as contemplated by the LGPL.

The binary distribution includes the LGPLv3 and GPLv3 license texts shipped with the exact pinned PySide6 distribution used to build the release. The build copies these texts from the installed package instead of downloading them from a network server during CI. See `QT_LGPL_SOURCE_OFFER.md` for source-code offer and relinking information.

Official Qt for Python licensing information:
- https://doc.qt.io/qtforpython-6/
- https://www.qt.io/development/open-source-lgpl-obligations

## Modified libtorrent 2.1.1

This project builds libtorrent from the upstream `v2.1.1` source revision and applies `patches/libtorrent-no-piece-upload.patch` before compiling the Python binding.

The modification removes the normal BitTorrent PIECE payload queueing implementation from `bt_peer_connection::write_piece()`. If that path is entered, the patched implementation records a compile-time marker and disconnects the peer rather than queueing file-piece bytes. The release package includes the exact patch and `PATCHED_LIBTORRENT_BUILD.txt` with build provenance and SHA-256 hashes.

libtorrent is released under the BSD license and includes additional third-party notices in its upstream license file. A copy of the exact upstream license/notices is included at `LICENSES/libtorrent.txt`.

Upstream project:
- https://libtorrent.org/
- https://github.com/arvidn/libtorrent

## Boost 1.91.0

The custom libtorrent Python binding is built with Boost 1.91.0. Boost is distributed under the Boost Software License 1.0. The Windows release includes a copy at `LICENSES/Boost-1.0.txt`.

Upstream project:
- https://www.boost.org/

## OpenSSL

The custom libtorrent build uses OpenSSL supplied by vcpkg for HTTPS tracker / SSL support. The release package includes the license/copyright material from the exact vcpkg OpenSSL package used by the build at `LICENSES/OpenSSL.txt`.

Upstream project:
- https://www.openssl.org/

## Python 3.11

Windows binary builds produced by PyInstaller include the Python runtime. Python is distributed under the Python Software Foundation License and related historical licenses. The release packaging step copies the Python license file from the exact Python runtime used for the build into the `LICENSES` directory.

Official Python licensing information:
- https://docs.python.org/3.11/license.html

## PyInstaller

PyInstaller is used as a build tool. PyInstaller's GPL license includes a special exception allowing generated executable bundles to be distributed under the application's license, subject to the licenses of bundled dependencies. PyInstaller itself is not treated as the license for this project.

Official PyInstaller licensing information:
- https://pyinstaller.org/en/stable/license.html

## Build-only dependencies

Pillow is used to generate the Windows icon during the build, and `pefile` is used in CI to verify Windows icon resources. These tools are not required by the running application.

## No restriction on LGPL debugging/relinking

Nothing in the Download Only Torrent license is intended to prevent reverse engineering, modification, replacement, or relinking of LGPL-covered Qt/PySide6 libraries for the purpose of exercising rights granted by the LGPL.

This notice is provided to make third-party licensing visible; it is not legal advice.
