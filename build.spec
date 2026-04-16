# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Portal Frame Generator

import os

block_cipher = None

# Bundle the section library as fallback data
library_src = r"C:\ProgramData\SPACE GASS\Custom Libraries\LIBRARY_SG14_SECTION_FS.slsc"
datas = []
if os.path.isfile(library_src):
    datas.append((library_src, "libraries"))

# Bundle the CFS span table (used by the design check module)
span_table_src = os.path.join(os.path.dirname(os.path.abspath(SPEC)), "docs", "CFS_Span_Table.xlsx")
if os.path.isfile(span_table_src):
    datas.append((span_table_src, "docs"))

a = Analysis(
    ['portal_frame_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PortalFrameGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window — GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)
