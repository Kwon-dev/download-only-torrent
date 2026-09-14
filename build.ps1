$ErrorActionPreference = 'Stop'

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pillow
python tools/generate_icon.py
python -m compileall -q app.py download_only_torrent tools
pyinstaller --noconfirm --clean --onefile --windowed --name DownloadOnlyTorrent --icon assets/app.ico --collect-all libtorrent app.py
Write-Host "Built: dist\DownloadOnlyTorrent.exe"
