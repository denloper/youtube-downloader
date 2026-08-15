@echo off
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean YouTubeDownloader.spec

echo.
echo Готово. EXE лежит в папке dist\YouTubeDownloader.exe
pause
