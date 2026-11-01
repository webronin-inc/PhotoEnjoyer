"""Хранение сессии на диске.

Токен шифруется средствами Windows (DPAPI — привязан к пользователю ОС).
На остальных системах — лёгкая обфускация (честно: это не шифрование)."""
import base64
import json
import os
import sys
import time
from pathlib import Path

from .. import branding


def _path():
    return Path.home() / f".{branding.APP_CONFIG_DIR}_session"


# ------------------------------------------------------------------ DPAPI
def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _xor(data):
    key = b"photoenjoyer-session"
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def protect(data):
    if sys.platform == "win32":
        try:
            return b"W" + _dpapi(data, True)
        except Exception:
            pass
    return b"X" + _xor(data)


def unprotect(blob):
    if blob[:1] == b"W" and sys.platform == "win32":
        return _dpapi(blob[1:], False)
    if blob[:1] == b"X":
        return _xor(blob[1:])
    raise ValueError("unknown format")


# ----------------------------------------------------------------- сессия
def save(token, username, remember=True, last_seen=None):
    """Сохраняет токен. last_seen — наибольшее «серверное» время, которое мы видели
    (нужно, чтобы заметить откат системных часов)."""
    data = {"token": token, "username": username, "remember": bool(remember),
            "last_seen": int(last_seen or time.time())}
    blob = protect(json.dumps(data).encode("utf-8"))
    p = _path()
    p.write_text(base64.b64encode(blob).decode("ascii"), encoding="ascii")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def load():
    p = _path()
    try:
        blob = base64.b64decode(p.read_text(encoding="ascii"))
        data = json.loads(unprotect(blob).decode("utf-8"))
        return data if isinstance(data, dict) and data.get("token") else None
    except Exception:
        return None


def clear():
    try:
        _path().unlink()
    except OSError:
        pass


def touch_last_seen(ts):
    data = load()
    if data and ts > data.get("last_seen", 0):
        save(data["token"], data["username"], data.get("remember", True), ts)
