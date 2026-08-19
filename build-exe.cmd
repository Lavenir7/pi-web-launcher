@echo off
setlocal
cd /d "%~dp0"
python tools\generate_icons.py
if errorlevel 1 (
    echo Icon generation failed.
    exit /b 1
)
python -m PyInstaller --noconfirm --clean PiWebLauncher.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo Built dist\PiWebLauncher\PiWebLauncher.exe
