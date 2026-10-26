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

    # Слоты — это новые виджеты после каждой смены шаблона/раскладки, undo,
    # очистки и смены темы. Поэтому приёмники вешаются заново при КАЖДОЙ
    # пересборке слотов (раньше — один раз при запуске, и после смены
    # шаблона перетаскивание фото переставало работать).
    app.add_slots_rebuilt_hook(lambda: _register_targets(app), call_now=True)
    app.plugin_flags["drag_drop"] = True


def _register_targets(app):
    for idx, container in enumerate(getattr(app, "slot_containers", [])):
        for widget in _walk(container):
            _bind(widget, app, idx)

    # Весь список слотов (промежутки, поля подписей): файлы кладутся с первого
    # пустого слота, чтобы промахнуться мимо квадрата было нельзя.
    grid = getattr(app, "slots_grid", None)
    if grid is not None:
        for widget in _walk(grid):
            if not getattr(widget, "_pe_dnd", False):
                _bind(widget, app, None)


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for ch in children:
        yield from _walk(ch)


def _bind(widget, app, idx):
    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>",      _wrap(_on_drop,  app, idx))
        widget.dnd_bind("<<DropEnter>>", _wrap(_on_enter, app, idx))
        widget.dnd_bind("<<DropLeave>>", _wrap(_on_leave, app, idx))
        widget._pe_dnd = idx is not None
    except Exception:
        pass


def _wrap(fn, app, idx):
    """Оборачивает обработчик, подставляя app и idx."""
    return lambda event: fn(app, event, idx)


def _on_enter(app, _event, idx):
    if idx is None:
        return
    # подсветка через штатную отрисовку слота (раньше менялся bg Canvas,
    # и после перетаскивания слот оставался с «чужим» фоном)
    if idx < len(app.slot_containers):
        slot = app.slot_containers[idx]
        slot.hover = True
        slot._hv = 1.0
        slot._redraw()


def _on_leave(app, _event, idx):
    if idx is None:
        return
    if idx < len(app.slot_containers):
        app.slot_containers[idx].hover = False
        app.slot_containers[idx]._hv = 0.0
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
                    full = os.path.join(item, name)
                    if (os.path.splitext(name)[1].lower() in IMAGE_EXTS
                            and os.path.isfile(full)):
                        files.append(full)
            except Exception:
                pass
        elif os.path.splitext(item)[1].lower() in IMAGE_EXTS:
            files.append(item)

    if not files:
        app.set_status("Перетащены не изображения")
        _on_leave(app, None, idx)
        return

    placed = app.fill_slots(files, start=idx, undo_label="Перетаскивание фото")
    _on_leave(app, None, idx)
    where = f"слот {idx + 1}" if idx is not None else "свободные слоты"
    app.set_status(f"Перетащено файлов: {placed} → {where}")
