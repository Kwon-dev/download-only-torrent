# Qt / PySide6 LGPL source and relinking information

Download Only Torrent uses the Community Edition of Qt for Python (PySide6) and Qt under the GNU Lesser General Public License version 3 (LGPLv3).

## Relinking / replacing Qt libraries

Official Windows releases are distributed in **onedir** form. Qt and PySide6 shared libraries are kept as separate files next to the application rather than embedded into a single immutable executable.

You may replace LGPL-covered Qt/PySide6 shared libraries with compatible modified versions. The application does not intentionally use DRM, signature enforcement, or other technical restrictions to prevent that replacement. You may reverse engineer the application to the extent necessary to debug modifications to LGPL-covered libraries, as permitted by the LGPL.

Because incompatible Qt/PySide6 ABI changes may prevent the application from starting, replacement libraries should remain interface-compatible with the versions shipped in the corresponding release.

## Source-code offer

For each public binary release that contains LGPL-covered Qt/PySide6 components, the distributor offers to provide the complete corresponding source code for the exact LGPL-covered library versions used by that release, including any distributor-applied modifications (if any), for at least three years after that binary release.

To request the corresponding source, open an issue in this GitHub repository and include the release tag or exact build/run number you received:

https://github.com/Kwon-dev/download-only-torrent/issues

The source will be provided electronically at no charge. If physical media is specifically requested, only the reasonable cost of performing that distribution may be charged.

The project does not currently modify Qt or PySide6 source code. Build metadata pins PySide6 so that the corresponding upstream source version can be identified for each release.

## License texts

The Windows release package includes copies of:

- GNU Lesser General Public License version 3
- GNU General Public License version 3
- the libtorrent license/notices
- the Python runtime license
- this source offer
- `THIRD_PARTY_NOTICES.md`

For the complete LGPL terms, refer to the license texts included with the release.

This document is intended to support LGPL compliance and is not legal advice.
