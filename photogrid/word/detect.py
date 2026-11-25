"""Определение установленного Microsoft Word.

Версия Office в реестре «16.0» одинакова у 2016/2019/2021/Microsoft 365, поэтому
различаем по идентификаторам продукта Click-to-Run (ProductReleaseIds), например
«ProPlus2021Volume», «Word2021Retail», «O365ProPlusRetail». Читаем только реестр
Windows — Word не запускается и не проверяется «изнутри»."""
import os
import re
import sys
from dataclasses import dataclass, field

C2R = r"SOFTWARE\Microsoft\Office\ClickToRun\Configuration"
APP_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
DEFAULT_MATCH = ("2021",)

FAMILIES = (                       # порядок важен: первое совпадение
    ("2024", ("2024",)), ("2021", ("2021",)), ("2019", ("2019",)),
    ("Microsoft 365", ("o365", "microsoft365", "m365")), ("2016", ("2016",)),
)
MSI_VERSIONS = (("16.0", "2016"), ("15.0", "2013"), ("14.0", "2010"), ("12.0", "2007"))


class WinRegistry:
    """Чтение HKLM в 64- и 32-битном представлении."""

    def get(self, path, name=""):
        if sys.platform != "win32":
            return None
        import winreg
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                                    winreg.KEY_READ | view) as k:
                    return winreg.QueryValueEx(k, name)[0]
            except OSError:
                continue
        return None

    def key_exists(self, path):
        if sys.platform != "win32":
            return False
        import winreg
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                                               winreg.KEY_READ | view))
                return True
            except OSError:
                continue
        return False


@dataclass
class WordInfo:
    installed: bool = False
    exe_path: str = ""
    product_ids: tuple = ()
    version: str = ""
    platform: str = ""
    family: str = ""               # «2021», «2019», «Microsoft 365», «2016», … или ""
    notes: list = field(default_factory=list)

    def matches(self, patterns=DEFAULT_MATCH):
        """Word подходит, если один из идентификаторов продукта содержит признак."""
        if not self.installed:
            return False
        return any(p.lower() in pid.lower() for pid in self.product_ids for p in patterns)

    def describe(self):
        if not self.installed:
            return "Microsoft Word не найден"
        name = f"Word {self.family}" if self.family and self.family != "Microsoft 365" \
            else (self.family or "Word неизвестной версии")
        return name + (f" (сборка {self.version})" if self.version else "")

    def as_log(self):
        return (f"installed={self.installed} family={self.family or '-'} "
                f"ids={','.join(self.product_ids) or '-'} version={self.version or '-'} "
                f"platform={self.platform or '-'} exe={self.exe_path or '-'}")


def _family_from_ids(ids):
    low = " ".join(ids).lower()
    for name, keys in FAMILIES:
        if any(k in low for k in keys):
            return name
    return "" if not ids else "неизвестная"


def detect_word(reader=None, file_exists=os.path.exists):
    reader = reader or WinRegistry()
    info = WordInfo()
    ids_raw = reader.get(C2R, "ProductReleaseIds") or ""
    info.product_ids = tuple(i.strip() for i in re.split(r"[,;]", str(ids_raw)) if i.strip())
    info.version = str(reader.get(C2R, "VersionToReport") or "")
    info.platform = str(reader.get(C2R, "Platform") or "")

    exe = reader.get(APP_PATH, "") or ""
    if not exe:                                     # запасной путь — каталог установки
        for ver, _ in MSI_VERSIONS:
            root = reader.get(rf"SOFTWARE\Microsoft\Office\{ver}\Word\InstallRoot", "Path")
            if root:
                exe = os.path.join(str(root), "WINWORD.EXE")
                break
    exe = str(exe).strip('"')
    if exe and file_exists(exe):
        info.exe_path = exe
    elif exe:
        info.notes.append("путь к WINWORD.EXE есть в реестре, но файла нет")

    if info.product_ids:
        info.family = _family_from_ids(info.product_ids)
    else:                                           # установка через MSI (без Click-to-Run)
        for ver, name in MSI_VERSIONS:
            if reader.key_exists(rf"SOFTWARE\Microsoft\Office\{ver}\Word\InstallRoot"):
                info.family = name
                info.product_ids = (f"MSI{name}",)
                break
    info.installed = bool(info.exe_path or (info.product_ids and info.family))
    return info
