"""Вставка изображения или файлов из буфера обмена (Ctrl+V)."""
import os
import tkinter as tk
from tkinter import ttk

from ..config import IMAGE_EXTS

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
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox,
                              ttk.Spinbox))
    except Exception:
        return False


def _focused_widget(app):
    try:
        return app.root.focus_get()
    except Exception:   # KeyError на выпадающих списках Combobox и т.п.
        return None


def _on_paste(app, event):
    if _is_text_widget(_focused_widget(app)):
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
        files = [p for p in data
                 if os.path.splitext(p)[1].lower() in IMAGE_EXTS
                 and os.path.isfile(p)]
        if not files:
            app.set_status("В буфере нет изображений")
            return
        placed = app.fill_slots(files)
        app.set_status(f"Вставлено файлов: {placed}")
        return

    # Одно изображение. Имя файла уникально: раньше оно было одним и тем же
    # для всех вставок, и повторная вставка подменяла картинку в прошлом слоте.
    try:
        tmp = app.new_temp_path("paste")
        data.save(tmp, "PNG")
    except Exception as e:
        app.set_status(f"Ошибка сохранения вставки: {e}")
        return

    app.fill_slots([tmp])
    app.set_status("Изображение вставлено в слот")