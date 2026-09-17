"""Ядро системы обновлений: проверка, скачивание, применение."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from .version import __version__, compare, is_newer
from . import branding
import threading

# URL по умолчанию — замените на свой при публикации
DEFAULT_MANIFEST_URL = branding.APP_MANIFEST_URL


# ---------- окружение ----------
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Папка, где лежит EXE (или корень проекта при запуске из исходников)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Куда писать данные пользователя (настройки, плагины, кэш)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / branding.APP_SLUG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / branding.APP_SLUG
    base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / branding.APP_SLUG


def external_plugins_dir() -> Path:
    """Пользовательская папка для внешних плагинов (всегда доступна на запись)."""
    d = user_data_dir() / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def portable_plugins_dir() -> Path:
    """Папка плагинов рядом с EXE (portable-режим, только чтение)."""
    return app_dir() / "plugins"


def current_exe() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve()
    return None


# ---------- проверка ----------
def fetch_manifest(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": branding.user_agent(),
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data


def analyze(manifest: dict) -> dict:
    """Возвращает инфо об обновлении: available, version, notes, ..."""
    remote = (manifest.get("version") or "").strip()
    info = {
        "current": __version__,
        "remote": remote,
        "available": bool(remote) and is_newer(remote, __version__),
        "notes": manifest.get("notes", ""),
        "release_date": manifest.get("release_date", ""),
        "download_url": manifest.get("download_url", ""),
        "sha256": manifest.get("sha256", ""),
        "plugins": manifest.get("plugins", []) or [],
        "homepage": manifest.get("homepage", ""),
    }
    return info


# ---------- скачивание ----------
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path,
                  progress_cb=None, chunk: int = 65536) -> Path:
    """Скачивает url в dest. progress_cb(got_bytes, total_bytes|None)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={
        "User-Agent": branding.user_agent(),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        total = None
        try:
            total = int(r.headers.get("Content-Length") or 0) or None
        except Exception:
            pass
        got = 0
        with open(dest, "wb") as f:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                got += len(buf)
                if progress_cb:
                    progress_cb(got, total)
    return dest


def verify_sha256(path: Path, expected: str) -> bool:
    if not expected:
        return True  # проверка не задана
    return _sha256_file(path).lower() == expected.lower()


# ---------- применение (подмена exe) ----------
def schedule_self_replace(new_exe: Path) -> bool:
    """Планирует подмену работающего EXE при выходе. True — если сработало.

    Windows: bat-скрипт с циклом попыток.
    Linux/macOS: sh-скрипт.
    """
    if not is_frozen():
        return False
    cur = current_exe()
    if cur is None:
        return False

    tmp = Path(tempfile.mkdtemp(prefix="photogrid_upd_"))
    helper = tmp / ("update.bat" if os.name == "nt" else "update.sh")

    if os.name == "nt":
        script = f"""@echo off
:wait
move /y "{cur}" "{cur}.old" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
move /y "{new_exe}" "{cur}" >nul 2>&1
if errorlevel 1 (
    move /y "{cur}.old" "{cur}" >nul 2>&1
    exit /b 1
)
start "" "{cur}"
del "{cur}.old" >nul 2>&1
del "%~f0" >nul 2>&1
"""
    else:
        script = f"""#!/bin/sh
while ! mv -f "{cur}" "{cur}.old" 2>/dev/null; do sleep 1; done
mv -f "{new_exe}" "{cur}"
chmod +x "{cur}"
"{cur}" &
sleep 1
rm -f "{cur}.old"
rm -f "$0"
"""
    helper.write_text(script, encoding="utf-8")
    if os.name != "nt":
        os.chmod(helper, 0o755)

    try:
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", str(helper)],
                             creationflags=subprocess.DETACHED_PROCESS |
                                           subprocess.CREATE_NEW_PROCESS_GROUP,
                             close_fds=True)
        else:
            subprocess.Popen(["/bin/sh", str(helper)],
                             start_new_session=True, close_fds=True)
        return True
    except Exception as e:
        print(f"schedule_self_replace failed: {e}")
        return False


# ---------- применение обновления плагинов ----------
def apply_plugin_updates(plugins: list, progress_cb=None) -> list:
    """Скачивает и раскладывает внешние плагины в <app_dir>/plugins/.

    Каждый элемент: {name, url, sha256}
    Возвращает список отчётов: {name, ok, error}
    """
    target_dir = external_plugins_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for item in plugins:
        name = item.get("name")
        url = item.get("url")
        sha = item.get("sha256", "")
        if not name or not url:
            continue
        if not name.endswith(".py"):
            name += ".py"
        dest = target_dir / name
        report = {"name": name, "ok": False, "error": None}
        try:
            download_file(url, dest, progress_cb=progress_cb)
            if sha and not verify_sha256(dest, sha):
                dest.unlink(missing_ok=True)
                raise ValueError("sha256 mismatch")
            report["ok"] = True
        except Exception as e:
            report["error"] = str(e)
        reports.append(report)
    return reports
# =====================================================================
#  СИГНАЛЬНАЯ ШИНА (для бейджика обновления в UI)
# =====================================================================
_listeners = []
_pending = {"info": None}


def subscribe(fn):
    """Подписка на изменения состояния обновления. fn(info|None)."""
    _listeners.append(fn)
    try:
        fn(_pending["info"])
    except Exception:
        pass


def set_pending(info):
    """Установить/сбросить уведомление о доступном обновлении."""
    _pending["info"] = info
    for fn in list(_listeners):
        try:
            fn(info)
        except Exception:
            pass


def get_pending():
    return _pending["info"]


# =====================================================================
#  АСИНХРОННАЯ ПРОВЕРКА
# =====================================================================
def check_async(root, url, callback, timeout=10):
    """Проверяет манифест в фоне. callback(info|None, exception|None) в UI-потоке."""
    def worker():
        try:
            manifest = fetch_manifest(url, timeout=timeout)
            info = analyze(manifest)
            info["_checked_url"] = url
            root.after(0, lambda: callback(info, None))
        except Exception as e:
            root.after(0, lambda: callback(None, e))
    threading.Thread(target=worker, daemon=True).start()


def perform_check(app, silent=False, on_done=None):
    """Полный цикл проверки: URL → запрос → установка состояния."""
    url = app.config.data.get("updates", {}).get("manifest_url", "")
    if not url or "example.com" in url or "USER/REPO" in url:
        if on_done:
            on_done(None, "url_not_configured")
        return

    if not silent:
        app.set_status("Проверка обновлений…")

    def done(info, err):
        if info is not None:
            set_pending(info if info.get("available") else None)
        if on_done:
            on_done(info, err)

    check_async(app.root, url, done)


# =====================================================================
#  ОПРЕДЕЛЕНИЕ ТИПА УСТАНОВКИ
# =====================================================================
def is_installed_via_inno() -> bool:
    """True — если EXE поставлен через Inno Setup (есть unins*.exe рядом)."""
    if not is_frozen():
        return False
    d = current_exe().parent
    for pat in ("unins*.exe", "unins*.dat"):
        if list(d.glob(pat)):
            return True
    return False


# =====================================================================
#  УСТАНОВКА ОБНОВЛЕНИЯ (установщик в тихом режиме)
# =====================================================================
def run_installer_and_exit(installer_path, app):
    """Запускает скачанный Setup.exe в тихом режиме, закрывает приложение,
    затем снова его открывает.

    Работает через .bat, чтобы развязаться с текущим процессом.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    cur = current_exe()
    if cur is None:
        raise RuntimeError("не удалось определить путь к EXE")

    if os.name == "nt":
        bat = Path(tempfile.gettempdir()) / f"{branding.APP_SLUG}_update.bat"
        bat.write_text(
            "@echo off\n"
            "timeout /t 2 /nobreak >nul\n"
            f'start /wait "" "{installer_path}" '
            "/SILENT /SUPPRESSMSGBOXES /NORESTART /FORCECLOSEAPPLICATIONS\n"
            "timeout /t 1 /nobreak >nul\n"
            f'start "" "{cur}"\n'
            'del "%~f0"\n',
            encoding="utf-8",
        )
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            creationflags=subprocess.DETACHED_PROCESS |
                          subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        # Linux/macOS: просто запускаем и закрываемся
        subprocess.Popen([str(installer_path)], start_new_session=True)

    app.root.after(300, app.on_close)