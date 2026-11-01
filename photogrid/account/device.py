"""Стабильный отпечаток устройства (в сыром виде не покидает компьютер)."""
import hashlib
import platform
import sys
import uuid


def _machine_guid():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except Exception:
            pass
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return f"mac-{uuid.getnode():012x}"


def hwid():
    """SHA-256 от идентификатора машины + соль приложения (32 hex-символа)."""
    raw = "photoenjoyer|" + _machine_guid()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def device_name():
    return (platform.node() or "Компьютер")[:40]
