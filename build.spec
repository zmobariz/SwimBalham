# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Swim Balham app.
Builds a single-file portable .exe.
"""

import customtkinter
import os

ctk_path = os.path.dirname(customtkinter.__file__)
project_root = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(project_root, 'app.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        (ctk_path, 'customtkinter'),
        # Bundle logo files into the exe
        (os.path.join(project_root, 'logo.ico'), '.'),
        (os.path.join(project_root, 'logo_header.png'), '.'),
        (os.path.join(project_root, 'logo_sidebar.png'), '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL._tkinter_finder',
        'PIL.Image',
        'PIL.ImageTk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'scipy', 'pandas', 'tkinter.test'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SwimBalham',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    version=os.path.join(project_root, 'version_info.txt'),
    uac_admin=False,
    uac_uiaccess=False,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'logo.ico'),
)
