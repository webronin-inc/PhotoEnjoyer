"""Фоновые авто-проверки обновлений + анимированный значок в рельсе.

Создаёт именованный mutex {APP_SLUG}SingleInstance — Inno Setup
использует его, чтобы не переустанавливать файлы, пока приложение работает.

Значок обновления показывает app.set_update_badge() — он сам
управляет видимостью и анимацией кнопки в боковой панели.
"""
import sys

from .. import branding, updater


def register(app):
    _ensure_defaults(app)
    _create_single_instance_mutex()
    # Подписка: любое изменение состояния → показать/скрыть значок
    updater.subscribe(lambda info: _on_state_change(app, info))
    _schedule_next_check(app, first=True)
    app.plugin_flags["auto_updater"] = True


def _ensure_defaults(app):
    u = app.config.data.setdefault("updates", {})
    u.setdefault("check_interval_hours", 6)
    u.setdefault("manifest_url", updater.DEFAULT_MANIFEST_URL)


# ---------- mutex для Inno Setup ----------
_mutex_handle = None


def _create_single_instance_mutex():
    global _mutex_handle
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        name = f"{branding.APP_SLUG}SingleInstance"
        _mutex_handle = kernel32.CreateMutexW(None, False, name)
    except Exception:
        pass


# ---------- реакция на изменение состояния ----------
def _on_state_change(app, info):
    """Показывает или скрывает анимированный значок обновления в рельсе.

    info — словарь из updater.analyze() или None.
    """
    if hasattr(app, "set_update_badge"):
        app.set_update_badge(info)


# ---------- периодическая проверка ----------
def _schedule_next_check(app, first=False):
    hours = int(app.config.data["updates"].get("check_interval_hours", 6))
    delay_sec = 4 if first else max(60, hours * 3600)
    app.root.after(delay_sec * 1000, lambda: _do_check(app))


def _do_check(app):
    updater.perform_check(app, silent=True)
    _schedule_next_check(app)