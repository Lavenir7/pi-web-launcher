@echo off
setlocal
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PiWebLauncher pi_web_launcher.py
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo Built dist\PiWebLauncher.exe
