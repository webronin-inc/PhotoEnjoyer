"""Ручная обрезка каждого фото перед сборкой коллажа."""
import os
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from ..core import load_rgb

_state = {"originals": {}, "crops": {}, "tempdir": None}


def register(app):
    app.add_menu_item("Правка", "Редактор обрезки…", lambda: _open(app))
    app.plugin_flags["crop_editor"] = True


def _tempdir():
    if _state["tempdir"] is None:
        _state["tempdir"] = _state["tempdir"] = tempfile.mkdtemp(prefix=f"{branding.APP_SLUG.lower()}_crop_")
    return _state["tempdir"]


def _open(app):
    if not any(app.photos):
        messagebox.showinfo("Обрезка", "Сначала выберите хотя бы одно фото")
        return
    _CropDialog(app)


class _CropDialog:
    def __init__(self, app):
        self.app = app
        self.current_idx = None
        self.img_original = None
        self.tk_img = None
        self.rect = None
        self.sel_start = None
        self.sel_box = None

        p = app.palette
        self.top = tk.Toplevel(app.root)
        self.top.title("Редактор обрезки")
        self.top.configure(bg=p["surface"])
        self.top.geometry("960x720")
        self.top.transient(app.root)
        self.top.grab_set()

        bar = tk.Frame(self.top, bg=p["surface"]); bar.pack(fill=tk.X, padx=12, pady=10)
        tk.Label(bar, text="Слот:", bg=p["surface"], fg=p["text"]).pack(side=tk.LEFT)
        self.slot_var = tk.StringVar()
        self.slot_cb = ttk.Combobox(bar, textvariable=self.slot_var,
                                     state="readonly", width=18)
        self.slot_cb.pack(side=tk.LEFT, padx=8)
        tk.Label(bar, text="Тяните мышью по фото, чтобы выделить область обрезки",
                 bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9)
                 ).pack(side=tk.LEFT, padx=16)

        self.canvas = tk.Canvas(self.top, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        bot = tk.Frame(self.top, bg=p["surface"]); bot.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(bot, text="Применить обрезку", style="Accent.TButton",
                   command=self._apply).pack(side=tk.RIGHT)
        ttk.Button(bot, text="Сбросить для слота",
                   command=self._reset_slot).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(bot, text="Закрыть", command=self.top.destroy
                   ).pack(side=tk.RIGHT, padx=(0, 8))

        self.slot_cb.bind("<<ComboboxSelected>>", lambda e: self._load_current())
        self._refresh_slot_list()

    def _refresh_slot_list(self):
        items = [f"Фото {i+1}" for i, p in enumerate(self.app.photos) if p]
        self.slot_cb["values"] = items
        if items:
            self.slot_cb.current(0)
            self._load_current()

    def _current_index(self):
        try:
            return int(self.slot_var.get().split()[-1]) - 1
        except Exception:
            return None

    def _load_current(self):
        idx = self._current_index()
        if idx is None:
            return
        self.current_idx = idx

        current = self.app.photos[idx]
        tracked = _state["crops"].get(idx)
        if tracked is None or current != tracked:
            # пользователь заменил фото вручную — начинаем отслеживание заново
            _state["originals"][idx] = current
            _state["crops"].pop(idx, None)

        src = _state["originals"][idx]
        try:
            self.img_original = load_rgb(src, self.app.config["bg_color"])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть изображение:\n{e}")
            return
        self.top.after(50, self._render)

    def _render(self):
        self.canvas.delete("all")
        self.sel_box = None
        self.sel_start = None
        cw = self.canvas.winfo_width() or 900
        ch = self.canvas.winfo_height() or 500
        img = self.img_original.copy()
        img.thumbnail((cw - 20, ch - 20), Image.LANCZOS)
        self._disp_img = img
        self._disp_pos = ((cw - img.width) // 2, (ch - img.height) // 2)
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(*self._disp_pos, anchor="nw", image=self.tk_img)
        self.canvas.create_rectangle(
            self._disp_pos[0], self._disp_pos[1],
            self._disp_pos[0] + img.width, self._disp_pos[1] + img.height,
            outline="#7c5cff", dash=(4, 4)
        )

    def _in_bounds(self, x, y):
        x0, y0 = self._disp_pos
        return (x0 <= x <= x0 + self._disp_img.width
                and y0 <= y <= y0 + self._disp_img.height)

    def _on_press(self, e):
        if self._in_bounds(e.x, e.y):
            self.sel_start = (e.x, e.y)
            if self.rect:
                self.canvas.delete(self.rect)
                self.rect = None

    def _on_drag(self, e):
        if not self.sel_start:
            return
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.sel_start[0], self.sel_start[1], e.x, e.y,
            outline="#7c5cff", width=2
        )
        self.sel_box = (self.sel_start[0], self.sel_start[1], e.x, e.y)

    def _on_release(self, e):
        if not self.sel_start or not self.sel_box:
            return
        x1, y1, x2, y2 = self.sel_box
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        if x2 - x1 < 10 or y2 - y1 < 10:
            if self.rect:
                self.canvas.delete(self.rect)
                self.rect = None
            self.sel_box = None
            return
        self.sel_box = (x1, y1, x2, y2)

    def _apply(self):
        if not self.sel_box:
            messagebox.showinfo("Обрезка", "Сначала выделите область на фото", parent=self.top)
            return
        x1, y1, x2, y2 = self.sel_box
        dx, dy = self._disp_pos
        x1 -= dx; x2 -= dx; y1 -= dy; y2 -= dy
        sx = self.img_original.width / self._disp_img.width
        sy = self.img_original.height / self._disp_img.height
        box = (
            max(0, int(x1 * sx)), max(0, int(y1 * sy)),
            min(self.img_original.width, int(x2 * sx)),
            min(self.img_original.height, int(y2 * sy)),
        )
        if box[2] - box[0] < 5 or box[3] - box[1] < 5:
            messagebox.showwarning("Обрезка", "Слишком маленькая область", parent=self.top)
            return

        cropped = self.img_original.crop(box)
        idx = self.current_idx
        out = os.path.join(_tempdir(), f"crop_{idx}.png")
        cropped.save(out, "PNG")

        _state["crops"][idx] = out
        self.app.photos[idx] = out
        self.app.update_slot(idx)
        self.app.schedule_preview()
        self.app.set_status(f"Слот {idx + 1} обрезан ({box[2]-box[0]}×{box[3]-box[1]})")
        self._load_current()

    def _reset_slot(self):
        idx = self.current_idx
        if idx is None:
            return
        orig = _state["originals"].get(idx)
        if orig:
            self.app.photos[idx] = orig
            self.app.update_slot(idx)
            self.app.schedule_preview()
            _state["crops"].pop(idx, None)
            self._load_current()
            self.app.set_status(f"Слот {idx + 1}: обрезка сброшена")