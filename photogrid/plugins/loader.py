"""Автозагрузка плагинов: встроенные (внутри EXE) + внешние (<APPDATA> и <exe_dir>).

Работает и при запуске из .py, и из PyInstaller onefile EXE.
Итерация по файлам заменена на явный список BUNDLED, потому что
в замороженном приложении pkgutil.iter_modules(__path__) не работает.
"""
import importlib
import importlib.util
import sys
import traceback
from pathlib import Path

from ..updater import external_plugins_dir, portable_plugins_dir


# Встроенные плагины. При добавлении нового — просто допишите его имя сюда.
BUNDLED = [
    "drag_drop",
    "batch",
    "watermark",
    "pdf_export",
    "crop_editor",
    "clipboard",
    "templates",
    "auto_updater",
    "updater_ui",
]


def load_all(app):
    loaded = []
    seen = set()

    # 1) Внешние плагины (приоритет — можно перекрыть встроенный)
    for name, module in _iter_external():
        if name in seen:
            continue
        seen.add(name)
        if _register(module, name, app):
            loaded.append(name)

    # 2) Встроенные
    for name in BUNDLED:
        if name in seen:
            continue
        seen.add(name)
        try:
            module = importlib.import_module(f".{name}", package=__package__)
        except Exception as e:
            _safe_print(f"✗ не удалось импортировать встроенный {name}: {e}")
            traceback.print_exc()
            continue
        if _register(module, name, app):
            loaded.append(name)

    return loaded


def _safe_print(*args, **kwargs):
    """print, который никогда не падает из-за кодировки консоли."""
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            text = " ".join(str(a) for a in args)
            sys.stderr.buffer.write((text + "\n").encode("utf-8", "replace"))
        except Exception:
            pass


def _register(module, name, app) -> bool:
    if not hasattr(module, "register"):
        return False
    try:
        module.register(app)
        _safe_print(f"✓ плагин: {name}")
        return True
    except Exception as e:
        _safe_print(f"✗ ошибка в плагине {name}: {e}")
        try:
            traceback.print_exc()
        except Exception:
            pass
        return False


def _iter_external():
    """Внешние плагины из:
       1. %APPDATA%/PhotoEnjoyer/plugins/     (пользовательский каталог)
       2. <папка рядом с EXE>/plugins/        (portable-режим)
    """
    dirs = []
    try:
        dirs.append(external_plugins_dir())
    except Exception:
        pass
    try:
        dirs.append(portable_plugins_dir())
    except Exception:
        pass

    seen_paths = set()
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
        for path in sorted(d.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                rp = path.resolve()
            except Exception:
                rp = path
            if rp in seen_paths:
                continue
            seen_paths.add(rp)

            name = path.stem
            try:
                spec = importlib.util.spec_from_file_location(
                    f"photogrid_external_{name}", path
                )
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                yield name, mod
            except Exception as e:
                _safe_print(f"✗ внешний плагин {name} не загрузился: {e}")
                traceback.print_exc()