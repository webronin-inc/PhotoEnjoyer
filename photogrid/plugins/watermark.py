"""Водяной знак текстом поверх коллажа с живым превью."""
import tkinter as tk
from tkinter import colorchooser
from PIL import Image, ImageDraw, ImageFont, ImageTk

from ..core import build_collage
from ..ui_widgets import GradientSlider


DEFAULT = {
    "enabled": False,
    "text": "© PhotoGrid",
    "position": "bottom-right",
    "size_ratio": 0.035,
    "color": "#ffffff",
    "opacity": 180,
    "margin_ratio": 0.02,
}

# Позиции 3×3 — стрелка + технический ключ
POSITIONS = [
    (0, 0, "top-left",      "↖"),
    (0, 1, "top-center",    "↑"),
    (0, 2, "top-right",     "↗"),
    (1, 0, "middle-left",   "←"),
    (1, 1, "center",        "●"),
    (1, 2, "middle-right",  "→"),
    (2, 0, "bottom-left",   "↙"),
    (2, 1, "bottom-center", "↓"),
    (2, 2, "bottom-right",  "↘"),
]


def register(app):
    wm = app.config.data.setdefault("watermark", dict(DEFAULT))
    for k, v in DEFAULT.items():
        wm.setdefault(k, v)
    app.add_menu_item("Правка", "Водяной знак…", lambda: _open_dialog(app))
    app.register_collage_hook(_apply)
    app.plugin_flags["watermark"] = bool(wm.get("enabled"))


def _open_dialog(app):
    _WatermarkDialog(app)


# ==============================================================
#  Наложение водяного знака
# ==============================================================
def apply_watermark(img, settings):
    """Накладывает водяной знак с указанными настройками."""
    text = (settings.get("text") or "").strip()
    if not text:
        return img

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    base = min(img.size)
    font_size = max(10, int(base * float(settings.get("size_ratio", 0.035))))

    font = None
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    color = settings.get("color", "#ffffff").lstrip("#")
    rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
    fill = (*rgb, int(settings.get("opacity", 180)))

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = int(base * float(settings.get("margin_ratio", 0.02)))
    W, H = img.size
    pos = settings.get("position", "bottom-right")

    if "left" in pos:
        x = margin
    elif "right" in pos:
        x = W - tw - margin
    else:
        x = (W - tw) // 2

    if "top" in pos:
        y = margin - bbox[1]
    elif "bottom" in pos:
        y = H - th - margin - bbox[1]
    else:
        y = (H - th) // 2 - bbox[1]

    draw.text((x, y), text, font=font, fill=fill)
    out = img.convert("RGBA")
    out.alpha_composite(overlay)
    return out.convert("RGB")


def _apply(img, app, for_preview):
    wm = app.config.data.get("watermark", {})
    if not wm.get("enabled"):
        return img
    return apply_watermark(img, wm)


# ==============================================================
#  Диалог с двумя панелями
# ==============================================================
class _WatermarkDialog:
    def __init__(self, app):
        self.app = app
        self.wm = dict(app.config.data.get("watermark", DEFAULT))
        self.palette = app.palette
        self._preview_ref = None

        # Кэш базового коллажа (без водяного знака) + throttle
        self._base_img = None          # PIL.Image
        self._base_key = None          # «отпечаток» входных данных
        self._preview_job = None       # отложенная задача обновления

        p = self.palette
        self.top = tk.Toplevel(app.root)
        self.top.title("Водяной знак")
        self.top.configure(bg=p["surface"])
        self.top.geometry("980x660")
        self.top.minsize(880, 600)
        self.top.transient(app.root)
        self.top.grab_set()

        # Основная область — настройки слева, превью справа
        wrap = tk.Frame(self.top, bg=p["surface"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=20, pady=(20, 0))

        # Левая колонка — настройки
        left = tk.Frame(wrap, bg=p["surface"], width=340)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        # Правая колонка — превью
        right = tk.Frame(wrap, bg=p["bg"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0))

        self._build_controls(left)
        self._build_preview(right)

        # Кнопки внизу
        bottom = tk.Frame(self.top, bg=p["surface"])
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=(14, 20))
        tk.Frame(bottom, bg=p["border_soft"], height=1).pack(
            fill=tk.X, pady=(0, 14))

        tk.Button(bottom, text="Отмена",
                  bg=p["surface_alt"], fg=p["text"],
                  activebackground=p["surface_hi"],
                  activeforeground=p["text"],
                  bd=0, relief="flat", cursor="hand2",
                  font=("Segoe UI", 10), padx=18, pady=8,
                  command=self.top.destroy
                  ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(bottom, text="Сохранить",
                  bg=p["accent"], fg="#ffffff",
                  activebackground=p["accent_hi"],
                  activeforeground="#ffffff",
                  bd=0, relief="flat", cursor="hand2",
                  font=("Segoe UI", 10, "bold"), padx=18, pady=8,
                  command=self._save
                  ).pack(side=tk.RIGHT)

        self._refresh_preview()

    # =====================================================
    def _build_controls(self, parent):
        p = self.palette

        tk.Label(parent, text="Водяной знак",
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 16, "bold"),
                 anchor="w").pack(fill=tk.X, pady=(0, 2))

        tk.Label(parent, text="Изменения сразу видны в превью →",
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), anchor="w"
                 ).pack(fill=tk.X, pady=(0, 14))

        # Включение
        self.enabled_var = tk.BooleanVar(value=bool(self.wm.get("enabled")))
        tk.Checkbutton(parent, text="Включить водяной знак",
                       variable=self.enabled_var,
                       bg=p["surface"], fg=p["text"],
                       activebackground=p["surface"],
                       activeforeground=p["text"],
                       selectcolor=p["surface_alt"],
                       font=("Segoe UI", 10),
                       bd=0, highlightthickness=0,
                       command=self._refresh_preview
                       ).pack(anchor="w", pady=(0, 14))

        # Текст
        self._label(parent, "Текст")
        self.text_var = tk.StringVar(value=self.wm.get("text", ""))
        entry = tk.Entry(parent, textvariable=self.text_var,
                         bg=p["surface_alt"], fg=p["text"],
                         insertbackground=p["text"],
                         bd=0, relief="flat",
                         font=("Segoe UI", 10))
        entry.pack(fill=tk.X, ipady=7, ipadx=8, pady=(0, 14))
        entry.bind("<KeyRelease>", lambda e: self._refresh_preview())

        # Позиция — сетка 3×3
        self._label(parent, "Положение")
        grid = tk.Frame(parent, bg=p["surface"])
        grid.pack(pady=(0, 14))

        self.pos_var = tk.StringVar(value=self.wm.get("position", "bottom-right"))
        self._pos_buttons = {}
        for row, col, key, arrow in POSITIONS:
            btn = tk.Label(grid, text=arrow,
                           bg=p["surface_alt"], fg=p["text_dim"],
                           font=("Segoe UI", 14),
                           width=3, height=1,
                           cursor="hand2")
            btn.grid(row=row, column=col, padx=3, pady=3)
            btn.bind("<Button-1>", lambda e, k=key: self._select_position(k))
            self._pos_buttons[key] = btn

        self._update_position_buttons()

        # Размер
        self._label(parent, "Размер, % от меньшей стороны")
        self.size_var = tk.DoubleVar(
            value=float(self.wm.get("size_ratio", 0.035)) * 100)
        self._slider_row(parent, self.size_var, 1, 15,
                         fmt=lambda v: f"{v:.1f}%")

        # Прозрачность
        self._label(parent, "Прозрачность")
        self.opacity_var = tk.IntVar(value=int(self.wm.get("opacity", 180)))
        self._slider_row(parent, self.opacity_var, 20, 255,
                         fmt=lambda v: f"{int(v)}")

        # Отступ
        self._label(parent, "Отступ от края, %")
        self.margin_var = tk.DoubleVar(
            value=float(self.wm.get("margin_ratio", 0.02)) * 100)
        self._slider_row(parent, self.margin_var, 0, 10,
                         fmt=lambda v: f"{v:.1f}%")

        # Цвет
        self._label(parent, "Цвет")
        color_row = tk.Frame(parent, bg=p["surface"])
        color_row.pack(fill=tk.X, pady=(0, 6))
        self.color_btn = tk.Button(color_row, text="",
                                   bg=self.wm.get("color", "#ffffff"),
                                   bd=0, relief="flat", cursor="hand2",
                                   width=5, height=1,
                                   command=self._choose_color)
        self.color_btn.pack(side=tk.LEFT)

    # =====================================================
    def _label(self, parent, text):
        p = self.palette
        tk.Label(parent, text=text.upper(),
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill=tk.X, pady=(4, 4))

    def _slider_row(self, parent, var, min_, max_, fmt):
        p = self.palette
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill=tk.X, pady=(0, 10))

        val_lbl = tk.Label(row, text=fmt(var.get()),
                           bg=p["surface"], fg=p["text"],
                           font=("Segoe UI", 9, "bold"),
                           width=6, anchor="e")
        val_lbl.pack(side=tk.RIGHT, padx=(8, 0))

        def _sync(v):
            var.set(v)
            val_lbl.config(text=fmt(v))
            self._refresh_preview()   # throttled внутри

        slider = GradientSlider(row, p, from_=min_, to=max_,
                                value=var.get(), command=_sync,
                                height=22)
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return slider

    def _build_preview(self, parent):
        p = self.palette

        head = tk.Frame(parent, bg=p["bg"])
        head.pack(fill=tk.X, pady=(0, 8))
        tk.Label(head, text="ПРЕДПРОСМОТР",
                 bg=p["bg"], fg=p["text_faint"],
                 font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(side=tk.LEFT)
        tk.Label(head, text="Живое превью · настройте всё сразу",
                 bg=p["bg"], fg=p["text_faint"],
                 font=("Segoe UI", 8),
                 anchor="w").pack(side=tk.RIGHT)

        self.preview_label = tk.Label(
            parent, text="Загрузите 4 фото для превью",
            bg=p["bg"], fg=p["text_dim"],
            font=("Segoe UI", 11), justify="center",
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    # =====================================================
    #  Логика
    # =====================================================
    def _refresh_preview(self):
        """Отложенный вызов — не чаще раза в 80 мс."""
        if self._preview_job:
            try:
                self.top.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.top.after(80, self._do_refresh_preview)

    def _do_refresh_preview(self):
        self._preview_job = None
        if not any(self.app.photos):
            self.preview_label.config(image="",
                                      text="Загрузите 4 фото для превью")
            self._preview_ref = None
            return

        try:
            base = self._get_base_image()
            # Копируем, чтобы водяной знак не «наслаивался» на кэш
            img = base.copy()

            settings = self._collect_settings()
            if settings["enabled"]:
                img = apply_watermark(img, settings)

            img.thumbnail((560, 560), Image.LANCZOS)
            self._preview_ref = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self._preview_ref, text="")
        except Exception as e:
            self.preview_label.config(image="", text=f"Ошибка:\n{e}")
            self._preview_ref = None

    def _get_base_image(self):
        """Возвращает кэшированный коллаж без водяного знака."""
        # Отпечаток входных данных: пути фото + настройки раскладки
        key = (
            tuple(self.app.photos),
            self.app.config.get("layout"),
            self.app.config.get("mode"),
            self.app.config.get("cell_size"),
            self.app.config.get("border"),
            self.app.config.get("border_color"),
            self.app.config.get("bg_color"),
        )
        if self._base_img is not None and self._base_key == key:
            return self._base_img

        # Кэш устарел — пересобираем
        wm_store = self.app.config.data.get("watermark", {})
        old_enabled = wm_store.get("enabled")
        wm_store["enabled"] = False
        try:
            img = build_collage(self.app.photos, self.app.config,
                                for_preview=True)
            img = self.app.apply_collage_hooks(img, for_preview=True)
        finally:
            wm_store["enabled"] = old_enabled

        self._base_img = img
        self._base_key = key
        return img

    def _collect_settings(self):
        return {
            "enabled": bool(self.enabled_var.get()),
            "text": self.text_var.get(),
            "position": self.pos_var.get(),
            "size_ratio": float(self.size_var.get()) / 100.0,
            "color": self.wm.get("color", "#ffffff"),
            "opacity": int(self.opacity_var.get()),
            "margin_ratio": float(self.margin_var.get()) / 100.0,
        }

    def _select_position(self, key):
        self.pos_var.set(key)
        self._update_position_buttons()
        self._refresh_preview()

    def _update_position_buttons(self):
        p = self.palette
        cur = self.pos_var.get()
        for key, btn in self._pos_buttons.items():
            if key == cur:
                btn.config(bg=p["accent"], fg="#ffffff")
            else:
                btn.config(bg=p["surface_alt"], fg=p["text_dim"])

    def _choose_color(self):
        c = colorchooser.askcolor(color=self.wm.get("color", "#ffffff"),
                                  parent=self.top)[1]
        if c:
            self.wm["color"] = c
            self.color_btn.config(bg=c)
            self._refresh_preview()

    def _save(self):
        settings = self._collect_settings()
        self.wm.update(settings)
        self.app.config.data["watermark"] = self.wm
        self.app.config.save()
        self.app.plugin_flags["watermark"] = settings["enabled"]
        self.app.schedule_preview()
        self.top.destroy()