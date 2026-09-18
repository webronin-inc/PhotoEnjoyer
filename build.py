"""Сборка EXE + инсталлятора + генерация manifest.json.

Запуск: python build.py
Требует: pip install pyinstaller pillow tkinterdnd2 + Inno Setup 6.
"""
import sys

# UTF-8 для Windows-раннера GitHub Actions
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import hashlib
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from photogrid import branding
from photogrid.version import __version__

DIST      = HERE / "dist"
BUILD     = HERE / "build"
INSTALLER = HERE / "installer"
SPEC_FILE = HERE / f"{branding.APP_SLUG}.spec"
ISS_FILE  = HERE / "installer.iss"
EXE_NAME  = f"{branding.APP_EXE_NAME}.exe" if sys.platform == "win32" \
            else branding.APP_EXE_NAME


# ---------------------------------------------------------------- проверки
def check_dependencies():
    missing = []
    for mod, pip in (("PyInstaller", "pyinstaller"),
                     ("PIL", "pillow"),
                     ("tkinterdnd2", "tkinterdnd2"),
                     ("win32clipboard", "pywin32")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip)
    if missing:
        print("✗ Не хватает зависимостей:")
        for m in missing:
            print(f"    • {m}")
        print(f"\nУстановите: pip install {' '.join(missing)}")
        sys.exit(1)
    print("✓ зависимости на месте")


def check_spec():
    if not SPEC_FILE.exists():
        print(f"✗ Не найден spec-файл: {SPEC_FILE.name}")
        sys.exit(1)
    print(f"✓ spec: {SPEC_FILE.name}")


def check_icon():
    icon = HERE / branding.APP_ICON
    if icon.exists():
        print(f"✓ иконка: {icon.name}")
    else:
        print(f"· иконка {branding.APP_ICON} не найдена — сборка без иконки")


def find_inno_setup():
    if sys.platform != "win32":
        return None
    for p in (
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    ):
        if p.exists():
            return p
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    return Path(found) if found else None


# ---------------------------------------------------------------- шаги
def clean():
    for p in (DIST, BUILD, INSTALLER):
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    print("✓ очищено")


def build_exe():
    cmd = [sys.executable, "-m", "PyInstaller",
           "--clean", "--noconfirm", SPEC_FILE.name]
    print("▶", " ".join(cmd))
    try:
        res = subprocess.run(cmd, cwd=HERE)
    except KeyboardInterrupt:
        print("\n✗ Прервано")
        sys.exit(130)
    if res.returncode != 0:
        print("✗ сборка EXE не удалась")
        sys.exit(res.returncode)
    print("✓ EXE собран")


def cleanup_build_dir():
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)
        print("✓ промежуточная build/ удалена")


def build_installer():
    if sys.platform != "win32":
        print("· инсталлятор пропущен (только Windows)")
        return False
    if not ISS_FILE.exists():
        print(f"· {ISS_FILE.name} не найден")
        return False
    iscc = find_inno_setup()
    if not iscc:
        print("· Inno Setup не найден → https://jrsoftware.org/isdl.php")
        return False

    has_license = (HERE / "LICENSE.txt").exists()
    has_readme  = (HERE / "README.md").exists()

    cmd = [
        str(iscc), "/Qp",
        f"/DAppVersion={__version__}",
        f"/DAppName={branding.APP_NAME}",
        f"/DAppPublisher={branding.APP_PUBLISHER}",
        f"/DAppExeName={branding.APP_EXE_NAME}",
        f"/DAppIcon={HERE / branding.APP_ICON}",
        f"/DAppUrl={branding.APP_HOMEPAGE}",
    ]
    if has_license:
        cmd.append("/DHasLicense=1")
    if has_readme:
        cmd.append("/DHasReadme=1")
    cmd.append(str(ISS_FILE))

    print("▶", " ".join(cmd))
    res = subprocess.run(cmd, cwd=HERE)
    if res.returncode != 0:
        print("✗ сборка инсталлятора не удалась")
        return False
    print("✓ инсталлятор собран")
    return True


# ---------------------------------------------------------------- manifest
def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def print_manifest_snippet(has_installer):
    if not has_installer:
        return
    setup = INSTALLER / f"{branding.APP_NAME}-Setup-{__version__}.exe"
    if not setup.exists():
        return

    sha = _sha256(setup)
    download = (f"https://github.com/USER/REPO/releases/download/"
                f"v{__version__}/{setup.name}")

    snippet = {
        "version": __version__,
        "release_date": str(date.today()),
        "homepage": branding.APP_HOMEPAGE,
        "download_url": download,
        "sha256": sha,
        "notes": ("Что нового:\n"
                  "• …\n"
                  "• …"),
        "plugins": [],
    }

    print()
    print("─" * 68)
    print("  📄 Фрагмент для manifest.json — вставьте в GitHub:")
    print("─" * 68)
    print(json.dumps(snippet, ensure_ascii=False, indent=2))
    print("─" * 68)


def final_report(has_installer):
    print()
    print("═" * 64)
    print(f"  ✅  {branding.APP_NAME} v{__version__}")
    print("═" * 64)

    # onedir: EXE внутри папки
    app_dir = DIST / branding.APP_EXE_NAME
    exe = app_dir / EXE_NAME

    if app_dir.exists():
        print(f"  Папка приложения:  {app_dir}")
        if exe.exists():
            size_mb = exe.stat().st_size / (1024 * 1024)
            print(f"  EXE:               {exe.name} ({size_mb:.1f} МБ)")

        # размер всей папки
        total = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file())
        print(f"  Вся папка:         {total / (1024*1024):.1f} МБ")

    if has_installer:
        setup = INSTALLER / f"{branding.APP_NAME}-Setup-{__version__}.exe"
        if setup.exists():
            print(f"  Установщик:        {setup}")
            print(f"  Размер:            {setup.stat().st_size / (1024*1024):.1f} МБ")
            print()
            print(f"  👉 Отдавайте людям: {setup.name}")
    print("═" * 64)


# ---------------------------------------------------------------- main
def main():
    print(f"▶ Сборка {branding.APP_NAME} v{__version__}\n")
    check_dependencies()
    check_spec()
    check_icon()
    print()
    clean()
    build_exe()
    cleanup_build_dir()
    has_installer = build_installer()
    final_report(has_installer)
    print_manifest_snippet(has_installer)


if __name__ == "__main__":
    main()