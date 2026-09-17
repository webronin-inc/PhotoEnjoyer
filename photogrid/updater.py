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
def fetch_manifest(url: str, timeout: int = 10,
                   require_signature: bool = True) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": branding.user_agent(),
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))

    if require_signature:
        if not verify_manifest_signature(data):
            raise ValueError(
                "Манифест не подписан или подпись неверна — обновление отклонено"
            )
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
def run_installer_and_exit(installer_path, app, delay_ms: int = 3000):
    """Запускает скачанный Setup.exe в тихом режиме.

    Никаких .ps1/.bat — установщик Inno сам:
      1. Дождётся закрытия нашего процесса (через AppMutex).
      2. Установит новую версию.
      3. Запустит свежий EXE (благодаря [Run] в installer.iss).

    Мы только запускаем установщик и через `delay_ms` закрываемся.
    """
    import subprocess
    from pathlib import Path

    cur = current_exe()
    if cur is None:
        raise RuntimeError("не удалось определить путь к EXE")

    # Копируем установщик в путь без кириллицы (страховка от старых проблем)
    if os.name == "nt":
        work_dir = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / branding.APP_SLUG
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
            local_setup = work_dir / Path(installer_path).name
            shutil.copy2(installer_path, local_setup)
        except Exception:
            local_setup = Path(installer_path)
    else:
        local_setup = Path(installer_path)

    args = [
        str(local_setup),
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/FORCECLOSEAPPLICATIONS",
        "/CLOSEAPPLICATIONS",
    ]

    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            args,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        subprocess.Popen(args, start_new_session=True)

    # Даём установщику время стартовать и увидеть наш AppMutex.
    # После этого закрываемся — Inno подхватит и продолжит сам.
    app.root.after(delay_ms, app.on_close)
    
    # ---------- подпись Ed25519 ----------
def _load_public_key():
    """Публичный ключ, вшитый в приложение."""
    from pathlib import Path
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return None

    # Ищем рядом с модулем (при запуске из .py)
    here = Path(__file__).parent / "public_key.pem"
    # Или внутри распакованного PyInstaller bundle
    if not here.exists():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            here = Path(meipass) / "photogrid" / "public_key.pem"
    if not here.exists():
        return None

    pem = here.read_bytes()
    return serialization.load_pem_public_key(pem)


def verify_manifest_signature(manifest: dict) -> bool:
    """Проверяет Ed25519-подпись манифеста.

    Манифест должен содержать поле 'signature' (base64).
    Подписывается канонизированный JSON БЕЗ поля signature.
    Если поле signature отсутствует — возвращаем False (строгий режим).
    """
    sig_b64 = manifest.get("signature")
    if not sig_b64:
        return False

    try:
        import base64
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        print("cryptography не установлена — подпись не проверяется")
        return False

    pub = _load_public_key()
    if pub is None:
        print("Публичный ключ не найден — подпись не проверяется")
        return False

    # Канонизация: копия манифеста без signature, стабильный JSON
    payload = {k: v for k, v in manifest.items() if k != "signature"}
    canonical = json.dumps(payload, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")).encode("utf-8")

    try:
        pub.verify(base64.b64decode(sig_b64), canonical)
        return True
    except InvalidSignature:
        print("Подпись манифеста НЕВАЛИДНА")
        return False
    except Exception as e:
        print(f"Ошибка проверки подписи: {e}")
        return False