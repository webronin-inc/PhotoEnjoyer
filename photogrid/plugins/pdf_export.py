"""Экспорт коллажа в PDF: одиночный или многостраничный пакетный."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import IMAGE_EXTS
from ..core import build_collage


def register(app):
    app.add_menu_item("Файл", "Экспорт в PDF…", lambda: _export_single(app))
    app.add_menu_item("Файл", "Пакетный экспорт в PDF…", lambda: _export_batch(app))
    app.plugin_flags["pdf_export"] = True


def _export_single(app):
    if any(p is None for p in app.photos):
        messagebox.showwarning("Внимание", "Сначала выберите все 4 фотографии!")
        return
    path = filedialog.asksaveasfilename(
        title="Экспорт в PDF",
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        initialfile="collage.pdf",
    )
    if not path:
        return
    try:
        img = build_collage(app.photos, app.config, for_preview=False)
        img = app.apply_collage_hooks(img, for_preview=False)
        img.save(path, "PDF", resolution=150)
        app.set_status(f"PDF сохранён: {path}")
        messagebox.showinfo("Готово", f"PDF сохранён:\n{path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{e}")


def _export_batch(app):
    src = filedialog.askdirectory(title="Папка с наборами (подпапки по 4 фото)")
    if not src:
        return
    out = filedialog.asksaveasfilename(
        title="Куда сохранить пакетный PDF",
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        initialfile="batch.pdf",
    )
    if not out:
        return
    try:
        pages, skipped = [], 0
        for name in sorted(os.listdir(src)):
            sub = os.path.join(src, name)
            if not os.path.isdir(sub):
                continue
            files = sorted(
                os.path.join(sub, f) for f in os.listdir(sub)
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS
            )
            if len(files) < 4:
                skipped += 1
                continue
            img = build_collage(files[:4], app.config, for_preview=False)
            img = app.apply_collage_hooks(img, for_preview=False)
            pages.append(img)

        if not pages:
            messagebox.showwarning("Внимание", "Не найдено ни одной папки с 4+ фото")
            return

        pages[0].save(out, "PDF", resolution=150,
                      save_all=True, append_images=pages[1:])
        app.set_status(f"PDF сохранён: {out} ({len(pages)} стр.)")
        messagebox.showinfo(
            "Готово",
            f"PDF сохранён:\n{out}\n\nСтраниц: {len(pages)}"
            + (f"\nПропущено папок: {skipped}" if skipped else "")
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{e}")