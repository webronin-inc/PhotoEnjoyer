"""Плагин drag & drop. Автоматически активируется, если установлен tkinterdnd2.

Работает через публичное API приложения: app.root, app.slot_containers,
app.photos, app.update_slot, app.schedule_preview и т.д.
"""
import os
import tkinter as tk

from ..config import IMAGE_EXTS

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False


def register(app):
    if not HAS_DND:
        print("ℹ drag_drop: tkinterdnd2 не установлен, плагин пропущен")
        return

    if not hasattr(app.root, "drop_target_register"):
        print("ℹ drag_drop: root не поддерживает DnD (нужен TkinterDnD.Tk)")
        return

    for idx, container in enumerate(app.slot_containers):
        targets = [container]
        if hasattr(container, "winfo_children"):
            targets.extend(container.winfo_children())

        for widget in targets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>",      _wrap(_on_drop,      app, idx))
                widget.dnd_bind("<<DropEnter>>", _wrap(_on_enter,     app, idx))
                widget.dnd_bind("<<DropLeave>>", _wrap(_on_leave,     app, idx))
            except tk.TclError:
                pass

    app.plugin_flags["drag_drop"] = True


def _wrap(fn, app, idx):
    """Оборачивает обработчик, подставляя app и idx."""
    return lambda event: fn(app, event, idx)


def _on_enter(app, _event, idx):
    p = app.palette
    slot = app.slot_containers[idx]
    slot.config(highlightbackground=p["accent"],
                highlightcolor=p["accent"],
                bg=p["surface_hi"])
    for w in slot.winfo_children():
        if isinstance(w, tk.Label) and not w.cget("image"):
            w.config(bg=p["surface_hi"])


def _on_leave(app, _event, idx):
    app.update_slot(idx)


def _on_drop(app, event, idx):
    try:
        raw = app.root.tk.splitlist(event.data)
    except Exception:
        raw = [event.data]

    files = []
    for item in raw:
        if os.path.isdir(item):
            try:
                for name in sorted(os.listdir(item)):
                    if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                        files.append(os.path.join(item, name))
            except Exception:
                pass
        elif os.path.splitext(item)[1].lower() in IMAGE_EXTS:
            files.append(item)

    if not files:
        app.set_status("Перетащены не изображения")
        _on_leave(app, None, idx)
        return

    files = files[:4]
    for k, path in enumerate(files):
        target = (idx + k) % 4
        app.photos[target] = path
        app.update_slot(target)

    app.selected_slot = None
    app.schedule_preview()
    app.update_status()
    app.set_status(f"Перетащено файлов: {len(files)} → слот {idx + 1}")