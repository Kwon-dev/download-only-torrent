$ErrorActionPreference = 'Stop'

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
python -m compileall -q app.py download_only_torrent
pyinstaller --noconfirm --clean --onefile --windowed --name DownloadOnlyTorrent --collect-all libtorrent app.py
Write-Host "Built: dist\DownloadOnlyTorrent.exe"
