# -*- mode: python ; coding: utf-8 -*-

hiddenimports = [
    'pywintypes',
    'pythoncom',
    'win32api',
    'win32con',
    'win32gui',
    'win32gui_struct',
    'win32com',
]

a = Analysis(
    ['pi_web_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icons/*.ico', 'assets/icons')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PiWebLauncher',
    icon='assets/icons/idle.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PiWebLauncher',
)
