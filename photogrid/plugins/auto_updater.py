"""Фоновые авто-проверки обновлений + бейджик 🔔 в шапке.

Создаёт именованный mutex {APP_SLUG}SingleInstance — Inno Setup
(параметр AppMutex в installer.iss) использует его, чтобы не
переустанавливать файлы, пока приложение работает.
"""
import sys
import tkinter as tk

from .. import branding, updater


def register(app):
    _ensure_defaults(app)
    _create_single_instance_mutex()
    _install_badge(app)
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


# ---------- бейджик в шапке ----------
def _install_badge(app):
    p = app.palette
    try:
        parent = app.theme_button.master      # правый блок в header
    except Exception:
        return

    badge = tk.Button(
        parent,
        text="🔔",
        bg=p["accent"], fg="#ffffff",
        activebackground=p["accent_hi"], activeforeground="#ffffff",
        bd=0, relief="flat", highlightthickness=0, cursor="hand2",
        font=("Segoe UI Emoji", 10, "bold"),
        padx=10, pady=2,
        command=lambda: _on_badge_click(app),
    )
    badge.pack_forget()                        # скрыт пока нет обновления
    app._update_badge = badge


def _on_badge_click(app):
    from . import updater_ui
    updater_ui.open_update_dialog(app)


def _on_state_change(app, info):
    badge = getattr(app, "_update_badge", None)
    if badge is None:
        return

    if info:
        badge.config(text=f"🔔 {info['remote']}")
        if not badge.winfo_ismapped():
            badge.pack(side=tk.RIGHT, padx=(0, 6))
        try:
            app.root.title(f"● {branding.window_title()}")
        except Exception:
            pass
    else:
        badge.pack_forget()
        try:
            app.root.title(branding.window_title())
        except Exception:
            pass


# ---------- периодическая проверка ----------
def _schedule_next_check(app, first=False):
    hours = int(app.config.data["updates"].get("check_interval_hours", 6))
    delay_sec = 4 if first else max(60, hours * 3600)
    app.root.after(delay_sec * 1000, lambda: _do_check(app))


def _do_check(app):
    updater.perform_check(app, silent=True)
    _schedule_next_check(app)