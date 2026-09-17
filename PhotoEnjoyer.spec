# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

HERE = Path(SPECPATH).resolve()
sys.path.insert(0, str(HERE))

# Явно подгружаем пакет, чтобы PyInstaller точно его увидел
import photogrid               # noqa: F401
import photogrid.app           # noqa: F401

from photogrid import branding
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ---- tkinterdnd2 ----
dnd_datas, dnd_bins, dnd_hidden = collect_all("tkinterdnd2")

# ---- весь пакет photogrid целиком ----
photogrid_submodules = collect_submodules("photogrid")
print(f"[spec] photogrid submodules: {len(photogrid_submodules)}")
for m in photogrid_submodules:
    print(f"   • {m}")

a = Analysis(
    ["sikisiki.py"],
    pathex=[str(HERE)],
    binaries=dnd_bins,
    datas=dnd_datas,
    hiddenimports=dnd_hidden + photogrid_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=branding.APP_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / branding.APP_ICON)
        if (HERE / branding.APP_ICON).exists() else None,
)