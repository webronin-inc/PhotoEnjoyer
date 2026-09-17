"""Водяной знак текстом поверх коллажа."""
import tkinter as tk
from tkinter import colorchooser, ttk
from PIL import Image, ImageDraw, ImageFont

DEFAULT = {
    "enabled": False,
    "text": "© PhotoGrid",
    "position": "bottom-right",
    "size_ratio": 0.035,
    "color": "#ffffff",
    "opacity": 180,
    "margin_ratio": 0.02,
}

POSITIONS = [
    ("Сверху слева",   "top-left"),    ("Сверху центр",  "top-center"),    ("Сверху справа",  "top-right"),
    ("Слева центр",    "middle-left"), ("Центр",         "center"),        ("Справа центр",   "middle-right"),
    ("Снизу слева",    "bottom-left"), ("Снизу центр",   "bottom-center"), ("Снизу справа",   "bottom-right"),
]
NAME_BY_KEY = {k: n for n, k in POSITIONS}
KEY_BY_NAME = dict(POSITIONS)


def register(app):
    wm = app.config.data.setdefault("watermark", dict(DEFAULT))
    for k, v in DEFAULT.items():
        wm.setdefault(k, v)
    app.add_menu_item("Правка", "Водяной знак…", lambda: _WatermarkDialog(app))
    app.register_collage_hook(_apply)
    app.plugin_flags["watermark"] = bool(wm.get("enabled"))


def _apply(img, app, for_preview):
    wm = app.config.data.get("watermark", {})
    if not wm.get("enabled"):
        return img
    text = (wm.get("text") or "").strip()
    if not text:
        return img

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    base = min(img.size)
    font_size = max(10, int(base * float(wm.get("size_ratio", 0.035))))
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

    color = wm.get("color", "#ffffff").lstrip("#")
    rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
    fill = (*rgb, int(wm.get("opacity", 180)))

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = int(base * float(wm.get("margin_ratio", 0.02)))
    W, H = img.size
    pos = wm.get("position", "bottom-right")

    if "left" in pos:    x = margin
    elif "right" in pos: x = W - tw - margin
    else:                x = (W - tw) // 2
    if "top" in pos:     y = margin - bbox[1]
    elif "bottom" in pos: y = H - th - margin - bbox[1]
    else:                y = (H - th) // 2 - bbox[1]

    draw.text((x, y), text, font=font, fill=fill)
    out = img.convert("RGBA")
    out.alpha_composite(overlay)
    return out.convert("RGB")


class _WatermarkDialog:
    def __init__(self, app):
        self.app = app
        self.wm = app.config.data["watermark"]
        p = app.palette

        self.top = tk.Toplevel(app.root)
        self.top.title("Водяной знак")
        self.top.configure(bg=p["surface"])
        self.top.geometry("440x580")
        self.top.transient(app.root)
        self.top.grab_set()

        pad = {"padx": 16, "pady": 6}

        self.enabled_var = tk.BooleanVar(value=bool(self.wm.get("enabled")))
        ttk.Checkbutton(self.top, text="Включить водяной знак",
                        variable=self.enabled_var).pack(anchor="w", **pad)

        tk.Label(self.top, text="Текст:", bg=p["surface"], fg=p["text"]).pack(anchor="w", **pad)
        self.text_var = tk.StringVar(value=self.wm.get("text", ""))
        ttk.Entry(self.top, textvariable=self.text_var).pack(fill=tk.X, padx=16)

        tk.Label(self.top, text="Позиция:", bg=p["surface"], fg=p["text"]).pack(anchor="w", **pad)
        self.pos_var = tk.StringVar(
            value=NAME_BY_KEY.get(self.wm.get("position", "bottom-right"), POSITIONS[-1][0])
        )
        ttk.Combobox(self.top, textvariable=self.pos_var,
                     values=[n for n, _ in POSITIONS],
                     state="readonly").pack(fill=tk.X, padx=16)

        self.size_var = tk.DoubleVar(value=float(self.wm.get("size_ratio", 0.035)))
        self.opacity_var = tk.IntVar(value=int(self.wm.get("opacity", 180)))
        self.margin_var = tk.DoubleVar(value=float(self.wm.get("margin_ratio", 0.02)))

        def slider(label, var, frm, to, fmt):
            tk.Label(self.top, text=label, bg=p["surface"], fg=p["text"]).pack(anchor="w", **pad)
            f = tk.Frame(self.top, bg=p["surface"]); f.pack(fill=tk.X, padx=16)
            ttk.Scale(f, from_=frm, to=to, variable=var,
                      orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True)
            lbl = tk.Label(f, text=fmt(var.get()), bg=p["surface"],
                           fg=p["text_dim"], width=7)
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *_: lbl.config(text=fmt(var.get())))

        slider("Размер (доля от меньшей стороны):", self.size_var, 0.01, 0.15, lambda v: f"{v:.3f}")
        slider("Прозрачность:", self.opacity_var, 20, 255, lambda v: f"{int(v)}")
        slider("Отступ от края:", self.margin_var, 0.0, 0.1, lambda v: f"{v:.3f}")

        tk.Label(self.top, text="Цвет:", bg=p["surface"], fg=p["text"]).pack(anchor="w", **pad)
        cf = tk.Frame(self.top, bg=p["surface"]); cf.pack(fill=tk.X, padx=16)
        self.color_btn = tk.Button(cf, text="", bg=self.wm.get("color", "#ffffff"),
                                   width=6, relief="flat", bd=0, cursor="hand2",
                                   command=self._choose_color)
        self.color_btn.pack(side=tk.LEFT)

        bf = tk.Frame(self.top, bg=p["surface"]); bf.pack(fill=tk.X, padx=16, pady=20)
        ttk.Button(bf, text="OK", style="Accent.TButton", command=self._ok).pack(side=tk.RIGHT)
        ttk.Button(bf, text="Отмена", command=self.top.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(bf, text="Применить", command=self._apply_live).pack(side=tk.LEFT)

    def _choose_color(self):
        c = colorchooser.askcolor(color=self.wm.get("color", "#ffffff"),
                                  parent=self.top)[1]
        if c:
            self.wm["color"] = c
            self.color_btn.config(bg=c)

    def _collect(self):
        self.wm["enabled"] = bool(self.enabled_var.get())
        self.wm["text"] = self.text_var.get()
        self.wm["position"] = KEY_BY_NAME.get(self.pos_var.get(), "bottom-right")
        self.wm["size_ratio"] = float(self.size_var.get())
        self.wm["opacity"] = int(self.opacity_var.get())
        self.wm["margin_ratio"] = float(self.margin_var.get())

    def _apply_live(self):
        self._collect()
        self.app.config.save()
        self.app.plugin_flags["watermark"] = self.wm["enabled"]
        self.app.schedule_preview()
        self.app.update_status()

    def _ok(self):
        self._apply_live()
        self.top.destroy()