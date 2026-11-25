"""Запуск установщика (по умолчанию тихий) и разбор кода завершения."""
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000


class InstallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class InstallResult:
    ok: bool
    reboot: bool = False
    code: int = 0
    message: str = ""


def is_admin():
    if sys.platform == "win32":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def write_config(pkg, directory):
    """Файл конфигурации (например, configuration.xml для Office Deployment Tool)."""
    if not pkg.config_xml.strip():
        return None
    path = Path(directory) / "configuration.xml"
    path.write_text(pkg.config_xml, encoding="utf-8")
    return path


def build_command(installer, pkg, config_path=None):
    args = [a.replace("{config}", str(config_path or "")).replace("{installer}", str(installer))
            for a in pkg.args]
    if Path(installer).suffix.lower() == ".msi":
        return ["msiexec", "/i", str(installer)] + (args or ["/qn", "/norestart"])
    return [str(installer)] + args


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def elevated_command(cmd):
    """Обёртка PowerShell: запрос UAC, ожидание, возврат кода завершения.
    Отказ пользователя в UAC превращается в код 1223."""
    exe, args = cmd[0], cmd[1:]
    arglist = ", ".join(_ps_quote(a) for a in args)
    script = ("try { $p = Start-Process -FilePath " + _ps_quote(exe) +
              (" -ArgumentList @(" + arglist + ")" if args else "") +
              " -Verb RunAs -Wait -PassThru; exit $p.ExitCode } catch { exit 1223 }")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", script]


def run_installer(cmd, admin=None, runner=subprocess.run):
    """Запускает команду, при необходимости с повышением прав. Возвращает код."""
    admin = is_admin() if admin is None else admin
    final = cmd if admin else elevated_command(cmd)
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    try:
        res = runner(final, **kwargs)
    except FileNotFoundError:
        raise InstallError("not_found", "Не удалось запустить установщик (файл не найден).")
    except OSError as e:
        raise InstallError("os", f"Не удалось запустить установщик: {e}")
    return int(res.returncode)


def interpret(code):
    if code == 0:
        return InstallResult(True, False, 0, "Установка завершена")
    if code in (3010, 1641):
        return InstallResult(True, True, code, "Установка завершена, нужна перезагрузка компьютера")
    messages = {
        1223: "Установка отменена: не получено разрешение на запуск от имени администратора.",
        1602: "Установка отменена пользователем.",
        1618: "Уже идёт другая установка. Дождитесь её окончания и повторите.",
        1603: "Установщик сообщил о критической ошибке (код 1603).",
        1625: "Установка запрещена политикой безопасности компьютера.",
    }
    return InstallResult(False, False, code, messages.get(
        code, f"Установщик завершился с ошибкой (код {code}). Подробности — в журнале."))


def work_dir():
    base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    root = Path(base) if base else Path(tempfile.gettempdir())
    return root / "PhotoEnjoyer" / "downloads"
