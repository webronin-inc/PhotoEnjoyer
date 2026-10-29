"""Подписи к фото: стиль, шрифт, размер, цвета и быстрые действия.

Окно открывается из меню «Правка → Подписи…» и кнопкой в шапке списка фото.
Все изменения сразу видны в предпросмотре и в образце внутри окна.
"""
import os
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, ttk

from PIL import Image, ImageDraw, ImageOps, ImageTk

from .. import caption_render as cr
from .. import fx
from .. import icons
from ..ui_widgets import (
    ChipToggle, ColorSwatch, GradientButton, GradientSlider, SegmentedControl,
)

SAMPLE_SIZE = 270
SAMPLE_TEXT = "Пример подписи к фото"


def register(app):
    app._captions_opener = lambda: open_dialog(app)
    app.add_menu_item("Правка", "Подписи…", lambda: open_dialog(app))


def open_dialog(app):
    win = getattr(app, "_caption_dialog", None)
    try:
        if win is not None and win.top.winfo_exists():
            win.top.deiconify()
            win.top.lift()
            win.top.focus_force()
            return win
    except Exception:
        pass
    win = CaptionDialog(app)
    app._caption_dialog = win
    return win


# ==============================================================
#  Быстрые действия над подписями (без UI — удобно тестировать)
# ==============================================================
def captions_from_filenames(photos, captions):
    """Подписи из имён файлов: «IMG_01-sunset.jpg» → «IMG 01 sunset»."""
    out = list(captions)
    for i, path in enumerate(photos):
        if path:
            stem = Path(path).stem
            out[i] = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return out


def captions_numbered(photos, captions, template="{n}"):
    """Нумерация: шаблон с {n}, например «Шаг {n}». Только слоты с фото
    (если фото нет совсем — все слоты)."""
    template = template or "{n}"
    if "{n}" not in template:
        template += " {n}"
    idxs = [i for i, p in enumerate(photos) if p] or list(range(len(photos)))
    out = list(captions)
    for i in idxs:
        out[i] = template.replace("{n}", str(i + 1))
    return out


def captions_same_for_all(photos, captions):
    """Первая непустая подпись → во все слоты с фото."""
    first = next((c.strip() for c in captions if c and c.strip()), "")
    if not first:
        return list(captions)
    idxs = [i for i, p in enumerate(photos) if p] or list(range(len(photos)))
    out = list(captions)
    for i in idxs:
        out[i] = first
    return out


# ==============================================================
#  Окно настроек
# ==============================================================
class CaptionDialog:
    def __init__(self, app):
        self.app = app
        p = self.p = app.palette
        self.s = cr.caption_settings(app.config)
        self._save_job = None
        self._sample_job = None
        self._sample_img = None
        self._base = self._make_base()

        top = self.top = tk.Toplevel(app.root)
        top.title("Подписи")
        top.configure(bg=p["bg"])
        top.transient(app.root)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self._close)
        top.bind("<Escape>", lambda e: self._close())
        top.bind("<Destroy>", self._on_destroy, add="+")

        wrap = tk.Frame(top, bg=p["surface"], highlightthickness=1,
                        highlightbackground=p["border"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        body = tk.Frame(wrap, bg=p["surface"])
        body.pack(fill=tk.BOTH, expand=True, padx=22, pady=(18, 10))
        left = tk.Frame(body, bg=p["surface"])
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = tk.Frame(body, bg=p["surface"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(26, 0))

        self._build_left(left)
        self._build_right(right)
        self._build_footer(wrap)

        self._update_visibility()
        self._refresh_sample()
        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        rx, ry = app.root.winfo_rootx(), app.root.winfo_rooty()
        rw, rh = app.root.winfo_width(), app.root.winfo_height()
        top.geometry(f"+{max(0, rx + (rw - w) // 2)}+{max(0, ry + (rh - h) // 3)}")
        fx.dialog_in(top)

    # ------------------------------------------------------------ левая часть
    def _build_left(self, parent):
        p = self.p
        self._title(parent, "ОБРАЗЕЦ")
        frame = tk.Frame(parent, bg=p["border"], padx=1, pady=1)
        frame.pack(anchor="w")
        self.sample = tk.Canvas(frame, width=SAMPLE_SIZE, height=SAMPLE_SIZE,
                                bg=p["surface_alt"], highlightthickness=0)
        self.sample.pack()

        self._title(parent, "БЫСТРЫЕ ДЕЙСТВИЯ", top=16)
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill=tk.X)
        self.tpl_var = tk.StringVar(value="Шаг {n}")
        ent = tk.Entry(row, textvariable=self.tpl_var, width=11,
                       bg=p["surface_alt"], fg=p["text"],
                       insertbackground=p["accent_hi"], relief="flat", bd=0,
                       highlightthickness=1, highlightbackground=p["border"],
                       highlightcolor=p["accent"], font=("Segoe UI", 10))
        ent.pack(side=tk.LEFT, ipady=6, padx=(0, 6))
        self._action_btn(row, "Нумерация", "hash", self._act_number,
                         pack=dict(side=tk.LEFT, fill=tk.X, expand=True))
        tk.Label(parent, text="{n} — номер фото", bg=p["surface"],
                 fg=p["text_faint"], font=("Segoe UI", 8)
                 ).pack(anchor="w", pady=(2, 6))
        self._action_btn(parent, "Из имён файлов", "wand",
                         self._act_filenames, pack=dict(fill=tk.X, pady=2))
        self._action_btn(parent, "Одна подпись для всех", "copy",
                         self._act_same, pack=dict(fill=tk.X, pady=2))
        self._action_btn(parent, "Очистить подписи", "clear",
                         self._act_clear, danger=True,
                         pack=dict(fill=tk.X, pady=2))

    def _action_btn(self, parent, text, icon, command, danger=False, pack=None):
        p = self.p
        fg = p["danger"] if danger else p["text"]
        btn = tk.Button(
            parent, text=text, command=command,
            image=icons.tk_icon(icon, 16, fg if danger else p["text_dim"], 8),
            compound="left", bg=p["surface_alt"], fg=fg,
            activebackground=p["surface_hi"], activeforeground=fg,
            bd=0, relief="flat", cursor="hand2", highlightthickness=0,
            font=("Segoe UI", 9), anchor="w", padx=10, pady=7)
        btn.bind("<Enter>", lambda e: btn.config(bg=p["surface_hi"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=p["surface_alt"]))
        btn.pack(**(pack or {}))
        return btn

    # ------------------------------------------------------------ правая часть
    def _build_right(self, parent):
        p = self.p
        s = self.s
        parent.columnconfigure(1, weight=1)
        self._rows = {}
        r = 0

        def label(text, row):
            tk.Label(parent, text=text, bg=p["surface"], fg=p["text"],
                     font=("Segoe UI", 10)).grid(row=row, column=0,
                                                 sticky="w", pady=7)

        def cell(row):
            f = tk.Frame(parent, bg=p["surface"])
            f.grid(row=row, column=1, sticky="w", padx=(18, 0), pady=7)
            return f

        label("Стиль", r)
        SegmentedControl(
            cell(r), p, [(k, v) for k, v in cr.STYLES], value=s["caption_style"],
            command=lambda v: self._set("caption_style", v)).pack()
        r += 1
        label("Положение", r)
        SegmentedControl(
            cell(r), p, [(k, v) for k, v in cr.POSITIONS],
            value=s["caption_position"],
            command=lambda v: self._set("caption_position", v)).pack()
        r += 1
        label("Выравнивание", r)
        SegmentedControl(
            cell(r), p, [("left", "", "align_left"), ("center", "", "align_center"),
                         ("right", "", "align_right")],
            value=s["caption_align"], padx=18, pady=4, icon_size=17,
            command=lambda v: self._set("caption_align", v)).pack()
        r += 1

        label("Шрифт", r)
        fr = cell(r)
        fonts = cr.available_fonts()
        self.font_var = tk.StringVar(
            value=s["caption_font"] if s["caption_font"] in fonts else fonts[0])
        cb = ttk.Combobox(fr, textvariable=self.font_var, values=fonts,
                          state="readonly", width=16)
        cb.pack(side=tk.LEFT)
        cb.bind("<<ComboboxSelected>>",
                lambda e: self._set("caption_font", self.font_var.get()))
        ChipToggle(fr, p, "Ж", value=s["caption_bold"],
                   command=lambda v: self._set("caption_bold", v)
                   ).pack(side=tk.LEFT, padx=(8, 0))
        ChipToggle(fr, p, "К", value=s["caption_italic"],
                   font=("Segoe UI", 10, "bold italic"),
                   command=lambda v: self._set("caption_italic", v)
                   ).pack(side=tk.LEFT, padx=(4, 0))
        r += 1

        label("Размер", r)
        self.size_lbl = None
        self._slider(cell(r), 2.0, 12.0, s["caption_size_ratio"] * 100,
                     lambda v: f"{v:.1f}%",
                     lambda v: self._set("caption_size_ratio", round(v / 100, 4)))
        r += 1
        label("Строк", r)
        SegmentedControl(
            cell(r), p, [(n, str(n)) for n in (1, 2, 3, 4)],
            value=s["caption_max_lines"], padx=14,
            command=lambda v: self._set("caption_max_lines", int(v))).pack()
        r += 1

        label("Цвет текста", r)
        self.text_sw = ColorSwatch(
            cell(r), p, color=s["caption_color"], size=34,
            command=lambda: self._pick("caption_color", self.text_sw,
                                       "Цвет текста подписи"))
        self.text_sw.pack()
        r += 1

        # строки, которые скрываются для стиля «Контур»
        self._rows["bg"] = []
        label("Подложка", r)
        self.bg_sw = ColorSwatch(
            cell(r), p, color=s["caption_bg_color"], size=34,
            command=lambda: self._pick("caption_bg_color", self.bg_sw,
                                       "Цвет подложки подписи"))
        self.bg_sw.pack()
        self._rows["bg"].append(r)
        r += 1
        label("Прозрачность", r)
        self._slider(cell(r), 0, 100,
                     100 - s["caption_bg_opacity"] * 100 / 255,
                     lambda v: f"{v:.0f}%",
                     lambda v: self._set("caption_bg_opacity",
                                         int(round((100 - v) * 255 / 100))))
        self._rows["bg"].append(r)
        r += 1
        label("Тень текста", r)
        SegmentedControl(
            cell(r), p, [(True, "Вкл"), (False, "Выкл")],
            value=bool(s["caption_shadow"]), padx=14,
            command=lambda v: self._set("caption_shadow", bool(v))).pack()
        self._rows["bg"].append(r)
        self._right = parent

    def _slider(self, parent, lo, hi, value, fmt, on_change):
        p = self.p
        lbl = tk.Label(parent, text=fmt(value), bg=p["surface"], fg=p["text"],
                       font=("Segoe UI", 9, "bold"), width=5, anchor="e")
        lbl.pack(side=tk.RIGHT, padx=(8, 0))

        def cb(v):
            lbl.config(text=fmt(v))
            on_change(v)

        sl = GradientSlider(parent, p, from_=lo, to=hi, value=value,
                            command=cb, height=22, width=170)
        sl.pack(side=tk.LEFT)
        return sl

    def _title(self, parent, text, top=0):
        tk.Label(parent, text=text, bg=self.p["surface"],
                 fg=self.p["text_faint"], font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill=tk.X, pady=(top, 6))

    # ------------------------------------------------------------ нижняя панель
    def _build_footer(self, parent):
        p = self.p
        tk.Frame(parent, bg=p["border_soft"], height=1).pack(fill=tk.X, padx=22)
        bar = tk.Frame(parent, bg=p["surface"])
        bar.pack(fill=tk.X, padx=22, pady=(12, 16))
        reset = tk.Button(bar, text="Сбросить", command=self._reset,
                          bg=p["surface"], fg=p["text_dim"],
                          activebackground=p["surface_alt"],
                          activeforeground=p["text"], bd=0, relief="flat",
                          cursor="hand2", font=("Segoe UI", 9), padx=10, pady=6,
                          highlightthickness=0, takefocus=0)
        reset.pack(side=tk.LEFT)
        GradientButton(bar, p, text="Готово", icon="check", height=38,
                       command=self._close).pack(side=tk.RIGHT)

    # ------------------------------------------------------------ изменение
    def _set(self, key, value):
        self.s[key] = value
        self.app.config[key] = value
        if key == "caption_style":
            self._update_visibility()
        self._schedule_sample()
        self.app.schedule_preview()
        self._schedule_save()

    def _pick(self, key, swatch, title):
        c = colorchooser.askcolor(color=self.s[key], parent=self.top,
                                  title=title)[1]
        if c:
            swatch.set_color(c)
            self._set(key, c)

    def _reset(self):
        for k, v in cr.CAPTION_DEFAULTS.items():
            self.s[k] = v
            self.app.config[k] = v
        self.app.config.save()
        self.app.schedule_preview()
        # проще и надёжнее пересоздать окно с настройками по умолчанию
        pos = self.top.geometry().split("+", 1)[1]
        self.top.destroy()
        win = CaptionDialog(self.app)
        win.top.geometry("+" + pos)
        self.app._caption_dialog = win

    def _update_visibility(self):
        outline = self.s["caption_style"] == "outline"
        for r in self._rows.get("bg", []):
            for w in self._right.grid_slaves(row=r):
                if outline:
                    w.grid_remove()
                else:
                    w.grid()

    # ------------------------------------------------------------ образец
    def _make_base(self):
        """Основа образца: первое фото из коллажа, иначе градиент."""
        for path in self.app.photos:
            if path and os.path.exists(path):
                try:
                    with Image.open(path) as im:
                        im = ImageOps.exif_transpose(im).convert("RGB")
                        return ImageOps.fit(im, (SAMPLE_SIZE, SAMPLE_SIZE),
                                            Image.LANCZOS)
                except Exception:
                    break
        im = Image.new("RGB", (SAMPLE_SIZE, SAMPLE_SIZE))
        d = ImageDraw.Draw(im)
        for y in range(SAMPLE_SIZE):
            t = y / SAMPLE_SIZE
            d.line([(0, y), (SAMPLE_SIZE, y)],
                   fill=(int(52 + 120 * t), int(96 + 70 * t), int(170 - 60 * t)))
        d.ellipse((85, 60, 185, 160), fill=(250, 214, 96))
        return im

    def _sample_text(self):
        for c in self.app.captions:
            if c and c.strip():
                return c.strip()
        return SAMPLE_TEXT

    def _schedule_sample(self):
        if self._sample_job is None:
            self._sample_job = self.top.after(40, self._refresh_sample)

    def _refresh_sample(self):
        self._sample_job = None
        try:
            img = cr.draw_caption(self._base.copy(), self._sample_text(),
                                  self.app.config, SAMPLE_SIZE)
            self._sample_img = ImageTk.PhotoImage(img)
            self.sample.delete("all")
            self.sample.create_image(0, 0, image=self._sample_img, anchor="nw")
        except tk.TclError:
            pass

    # ------------------------------------------------------------ действия
    def _apply_captions(self, new, label, toast):
        app = self.app
        if list(new) == list(app.captions):
            app.set_status("Подписи не изменились")
            return
        app._push_undo(label)
        app.captions = list(new)
        app._build_slots()
        app.schedule_preview()
        self._schedule_sample()
        try:
            app.toasts.show(toast, kind="info", action=("Вернуть", app.undo))
        except Exception:
            pass

    def _act_number(self):
        a = self.app
        self._apply_captions(
            captions_numbered(a.photos, self._padded(), self.tpl_var.get()),
            "Нумерация подписей", "Подписи пронумерованы")

    def _act_filenames(self):
        a = self.app
        self._apply_captions(captions_from_filenames(a.photos, self._padded()),
                             "Подписи из имён файлов",
                             "Подписи взяты из имён файлов")

    def _act_same(self):
        a = self.app
        self._apply_captions(captions_same_for_all(a.photos, self._padded()),
                             "Одна подпись для всех", "Подпись скопирована во все фото")

    def _act_clear(self):
        a = self.app
        self._apply_captions([""] * len(a.photos), "Очистка подписей",
                             "Подписи очищены")

    def _padded(self):
        a = self.app
        caps = list(a.captions)
        caps += [""] * (len(a.photos) - len(caps))
        return caps[:len(a.photos)]

    # ------------------------------------------------------------ служебное
    def _schedule_save(self):
        if self._save_job is not None:
            try:
                self.top.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.top.after(500, self._save_now)

    def _save_now(self):
        self._save_job = None
        self.app.config.save()

    def _close(self):
        self._flush()
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def _flush(self):
        # отложенное сохранение не должно потеряться при закрытии окна
        if self._save_job is not None:
            try:
                self.top.after_cancel(self._save_job)
            except Exception:
                pass
            self._save_job = None
            self.app.config.save()

    def _on_destroy(self, event):
        if event.widget is self.top:
            self._flush()
            for job in (self._sample_job,):
                if job is not None:
                    try:
                        self.top.after_cancel(job)
                    except Exception:
                        pass
