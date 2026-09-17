"""Вставка изображения или файлов из буфера обмена (Ctrl+V)."""
import os
import tempfile
import tkinter as tk
from tkinter import ttk

from ..config import IMAGE_EXTS
from .. import branding

try:
    from PIL import ImageGrab
    HAS_GRAB = True
except ImportError:
    HAS_GRAB = False


def register(app):
    app.root.bind_all("<Control-v>", lambda e: _on_paste(app, e))
    app.add_menu_item("Правка", "Вставить из буфера", lambda: _on_paste(app, None),
                      accelerator="Ctrl+V")
    app.plugin_flags["clipboard"] = True


def _is_text_widget(w):
    """Не перехватываем Ctrl+V, если фокус в поле ввода."""
    if w is None:
        return False
    try:
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))
    except Exception:
        return False


def _on_paste(app, event):
    if _is_text_widget(app.root.focus_get()):
        return
    if not HAS_GRAB:
        app.set_status("Pillow.ImageGrab недоступен")
        return

    try:
        data = ImageGrab.grabclipboard()
    except Exception as e:
        app.set_status(f"Буфер обмена недоступен: {e}")
        return

    if data is None:
        app.set_status("Буфер обмена пуст или содержит не поддерживаемые данные")
        return

    # Windows-стиль: список путей к файлам
    if isinstance(data, list):
        files = [p for p in data if os.path.splitext(p)[1].lower() in IMAGE_EXTS]
        if not files:
            app.set_status("В буфере нет изображений")
            return
        files = files[:4]
        _fill_slots(app, files)
        app.set_status(f"Вставлено файлов: {len(files)}")
        return

    # Одно изображение
    try:
        tmp = os.path.join(tempfile.gettempdir(),
                            f"{branding.APP_SLUG.lower()}_paste_{id(app)}.png")
        data.save(tmp, "PNG")
    except Exception as e:
        app.set_status(f"Ошибка сохранения вставки: {e}")
        return

    _fill_slots(app, [tmp])
    app.set_status("Изображение вставлено в слот")


def _fill_slots(app, files):
    start = app.selected_slot
    if start is None:
        for i, p in enumerate(app.photos):
            if p is None:
                start = i
                break
    if start is None:
        start = 0
    for k, path in enumerate(files):
        idx = (start + k) % 4
        app.photos[idx] = path
        app.update_slot(idx)
    app.selected_slot = None
    app.schedule_preview()
    app.update_status()