# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

HERE = Path(SPECPATH).resolve()
sys.path.insert(0, str(HERE))

import photogrid               # noqa: F401
import photogrid.app           # noqa: F401

from photogrid import branding
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ---- tkinterdnd2 ----
dnd_datas, dnd_bins, dnd_hidden = collect_all("tkinterdnd2")

# ---- публичный ключ Ed25519 ----
key_path = HERE / "photogrid" / "public_key.pem"
extra_datas = []
if key_path.exists():
    extra_datas.append((str(key_path), "photogrid"))
    print(f"[spec] ✓ public_key.pem вшит")
else:
    print(f"[spec] ⚠ public_key.pem не найден: {key_path}")

# ---- весь пакет photogrid целиком ----
photogrid_submodules = collect_submodules("photogrid")
print(f"[spec] photogrid submodules: {len(photogrid_submodules)}")

a = Analysis(
    ["sikisiki.py"],
    pathex=[str(HERE)],
    binaries=dnd_bins,
    datas=dnd_datas + extra_datas,
    hiddenimports=dnd_hidden + photogrid_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# ВАЖНО для onedir: exclude_binaries=True
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=branding.APP_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / branding.APP_ICON)
        if (HERE / branding.APP_ICON).exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=branding.APP_EXE_NAME,
)