@echo off
setlocal
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean PiWebLauncher.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo Built dist\PiWebLauncher.exe
