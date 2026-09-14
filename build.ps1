$ErrorActionPreference = 'Stop'

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pillow
python tools/generate_icon.py
python -m compileall -q app.py download_only_torrent tools

pyinstaller --noconfirm --clean --onedir --windowed --name DownloadOnlyTorrent --icon assets/app.ico --collect-all libtorrent app.py

$app = ".\dist\DownloadOnlyTorrent"
$licenses = Join-Path $app "LICENSES"
New-Item -ItemType Directory -Force -Path $licenses | Out-Null
Copy-Item .\LICENSE (Join-Path $app "LICENSE")
Copy-Item .\THIRD_PARTY_NOTICES.md (Join-Path $app "THIRD_PARTY_NOTICES.md")
Copy-Item .\QT_LGPL_SOURCE_OFFER.md (Join-Path $app "QT_LGPL_SOURCE_OFFER.md")
Copy-Item .\LICENSES\libtorrent.txt (Join-Path $licenses "libtorrent.txt")
Invoke-WebRequest https://www.gnu.org/licenses/lgpl-3.0.txt -OutFile (Join-Path $licenses "LGPL-3.0.txt")
Invoke-WebRequest https://www.gnu.org/licenses/gpl-3.0.txt -OutFile (Join-Path $licenses "GPL-3.0.txt")

@'
from pathlib import Path
import shutil
import sys

out = Path(r"dist\DownloadOnlyTorrent\LICENSES\Python-3.11.txt")
candidates = [
    Path(sys.base_prefix) / "LICENSE.txt",
    Path(sys.base_prefix) / "LICENSE",
    Path(sys.prefix) / "LICENSE.txt",
    Path(sys.prefix) / "LICENSE",
]
for candidate in candidates:
    if candidate.is_file():
        shutil.copy2(candidate, out)
        break
else:
    raise SystemExit("Python runtime license file not found")
'@ | python -

Write-Host "Built: dist\DownloadOnlyTorrent\DownloadOnlyTorrent.exe"
Write-Host "Keep the whole dist\DownloadOnlyTorrent folder together when distributing."
