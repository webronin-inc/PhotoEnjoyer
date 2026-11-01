"""Подпись файлов signtool'ом (Windows SDK). Используется из build.py и вручную.

Настройка через переменные окружения (чтобы секреты не попадали в логи/код):
    PE_SIGN_PFX           путь к .pfx            ИЛИ
    PE_SIGN_PFX_BASE64    содержимое .pfx в base64 (так хранится секрет в GitHub)
    PE_SIGN_PASSWORD      пароль от .pfx
    PE_SIGN_TIMESTAMP     сервер меток времени (по умолчанию DigiCert, бесплатный)

Если переменные не заданы — подпись просто пропускается (локальная сборка).
"""
import base64
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_TIMESTAMP = "http://timestamp.digicert.com"


def enabled(env=None):
    env = env if env is not None else os.environ
    return bool((env.get("PE_SIGN_PFX") or env.get("PE_SIGN_PFX_BASE64"))
                and env.get("PE_SIGN_PASSWORD"))


def find_signtool():
    found = shutil.which("signtool") or shutil.which("signtool.exe")
    if found:
        return found
    pattern = r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe"
    hits = sorted(glob.glob(pattern))
    return hits[-1] if hits else None


def build_command(signtool, files, pfx, password, timestamp, description):
    cmd = [signtool, "sign", "/fd", "SHA256", "/f", str(pfx), "/p", password]
    if timestamp:
        cmd += ["/tr", timestamp, "/td", "SHA256"]
    if description:
        cmd += ["/d", description]
    return cmd + [str(f) for f in files]


def sign_files(files, description="PhotoEnjoyer", env=None, runner=subprocess.run):
    """Подписывает файлы. Возвращает True, если подпись выполнена."""
    env = env if env is not None else os.environ
    files = [Path(f) for f in files if Path(f).exists()]
    if not enabled(env):
        print("· подпись кода пропущена (PE_SIGN_* не заданы)")
        return False
    signtool = find_signtool()
    if not signtool:
        print("✗ signtool не найден (нужен Windows SDK) — подпись пропущена")
        return False
    tmp = None
    pfx = env.get("PE_SIGN_PFX")
    if not pfx:
        fd, tmp = tempfile.mkstemp(suffix=".pfx")
        with os.fdopen(fd, "wb") as f:
            f.write(base64.b64decode(env["PE_SIGN_PFX_BASE64"]))
        pfx = tmp
    try:
        cmd = build_command(signtool, files, pfx, env["PE_SIGN_PASSWORD"],
                            env.get("PE_SIGN_TIMESTAMP", DEFAULT_TIMESTAMP), description)
        shown = [("***" if i and cmd[i - 1] == "/p" else c) for i, c in enumerate(cmd)]
        print("▶", " ".join(shown))
        res = runner(cmd)
        if res.returncode != 0:
            print("✗ подпись не удалась")
            return False
        print("✓ подписано:", ", ".join(f.name for f in files))
        return True
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    ok = sign_files(sys.argv[1:])
    sys.exit(0 if ok else 1)
