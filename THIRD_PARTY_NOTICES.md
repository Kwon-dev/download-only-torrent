# Third-party notices

Download Only Torrent is licensed under the MIT License. The application also uses and/or distributes third-party components under their own licenses.

## Qt for Python / PySide6 6.9.2 and Qt 6.9.x

This project uses the Community Edition of Qt for Python (PySide6), which is available under the GNU Lesser General Public License version 3 (LGPLv3), GNU GPLv3, and commercial licensing options. This distribution relies on the LGPLv3 option for the Qt/PySide6 libraries used by the application.

The Windows release is intentionally packaged as an **onedir** application rather than a single-file bundle. Qt/PySide6 DLLs remain separate from `DownloadOnlyTorrent.exe`, so recipients can replace compatible Qt libraries with modified versions as contemplated by the LGPL.

The binary distribution includes copies of the GNU LGPLv3 and GPLv3 license texts. See `QT_LGPL_SOURCE_OFFER.md` for the source-code offer and relinking information.

Official Qt for Python licensing information:
- https://doc.qt.io/qtforpython-6/
- https://www.qt.io/development/open-source-lgpl-obligations

## libtorrent 2.1.1

This project uses libtorrent. libtorrent is released under the BSD license and includes additional third-party notices in its upstream license file.

A copy of the libtorrent license and bundled notices is included at `LICENSES/libtorrent.txt`.

Upstream project:
- https://libtorrent.org/
- https://github.com/arvidn/libtorrent

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
