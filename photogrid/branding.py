"""Единая точка настройки бренда. Здесь меняется НАЗВАНИЕ ПРОГРАММЫ и всё, что с ним связано."""

# ═══════════════════════════════════════════════════════════════════
#  ★  ГЛАВНАЯ НАСТРОЙКА — НАЗВАНИЕ ПРОГРАММЫ
# ═══════════════════════════════════════════════════════════════════
APP_NAME       = "PhotoEnjoyer"          # ← название, которое видит пользователь
APP_TAGLINE    = "Удобное ПО для составления фото-таблиц"
APP_PUBLISHER  = "EndlessOder inc"        # для "О программе" и метаданных EXE
APP_HOMEPAGE   = "@disperial"
APP_EMAIL      = "@disperial"

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
    return (
        f"{APP_NAME} v{__version__}   ({__release_date__})\n"
        f"{APP_TAGLINE}\n\n"
        f"Модульное приложение для объединения 4 фото в таблицу.\n"
        f"Раскладки 2×2, 4×1, 1×4 · рамки · режимы вписать/заполнить\n"
        f"предпросмотр · авто-загрузка · drag & drop · плагины.\n\n"
        f"© {APP_PUBLISHER}\n"
        f"{APP_HOMEPAGE}\n"
        f"{APP_EMAIL}"
    )
    # URL манифеста обновлений. Замените USER/REPO на свои.
APP_MANIFEST_URL = "https://raw.githubusercontent.com/webronin-inc/PhotoEnjoyer/refs/heads/main/manifest.json"