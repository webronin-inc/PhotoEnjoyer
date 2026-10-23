"""Единая точка настройки бренда. Здесь меняется НАЗВАНИЕ ПРОГРАММЫ и всё, что с ним связано."""

# ═══════════════════════════════════════════════════════════════════
#  ★  ГЛАВНАЯ НАСТРОЙКА — НАЗВАНИЕ ПРОГРАММЫ
# ═══════════════════════════════════════════════════════════════════
APP_NAME       = "PhotoEnjoyer"          # ← название, которое видит пользователь
APP_TAGLINE    = ""
APP_PUBLISHER  = "EndlessOder inc"        # для "О программе" и метаданных EXE
APP_HOMEPAGE   = "https://github.com/webronin-inc/PhotoEnjoyer"  # открывается в браузере
APP_EMAIL      = "@disperial"                 # контакт автора (показывается в «О программе»)

# URL манифеста обновлений
APP_MANIFEST_URL = "https://raw.githubusercontent.com/webronin-inc/PhotoEnjoyer/refs/heads/main/manifest.json"

# Технические имена (для файлов и папок). Обычно = APP_NAME, но без пробелов.
APP_SLUG       = APP_NAME.replace(" ", "")          # "PhotoGrid"
APP_EXE_NAME   = APP_SLUG                            # "PhotoGrid.exe"
APP_ICON       = "icon.ico"                          # иконка рядом со spec
APP_CONFIG_DIR = f".{APP_SLUG.lower()}"              # ~/.photogrid
# ═══════════════════════════════════════════════════════════════════


def window_title(extra: str = "") -> str:
    from .version import __version__
    base = f"{APP_NAME} — {APP_TAGLINE}" if APP_TAGLINE else APP_NAME
    base = f"{base}  v{__version__}"
    return f"{base}  ·  {extra}" if extra else base


def user_agent() -> str:
    from .version import __version__
    return f"{APP_NAME}/{__version__}"


def about_text() -> str:
    from .version import __version__, __release_date__
    head = f"{APP_NAME} v{__version__}   ({__release_date__})"
    if APP_TAGLINE:
        head += f"\n{APP_TAGLINE}"
    return (
        f"{head}\n\n"
        f"Модульное приложение для объединения фото в одну таблицу.\n"
        f"Раскладки от 1×1 до 3×3 · рамки · режимы вписать/заполнить\n"
        f"предпросмотр · подписи · drag & drop · плагины.\n\n"
        f"© {APP_PUBLISHER}\n"
        f"{APP_HOMEPAGE}\n"
        f"{APP_EMAIL}"
    )