"""Плагин «Редактор фото».

Правка фото в реальном времени: кадр (ближе/дальше, поворот, отражение),
цвет, фильтры, рисование как в Paint (кисть, ластик, линия, стрелка,
рамка, овал, текст) и скрытие областей (мозаика / размытие).

Открыть: ПКМ по слоту → «Редактировать фото…», Ctrl+E или меню «Правка».
Вся логика — в photogrid/editor_session.py (без Tk); здесь только окно.
"""
import os
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from .. import anim
from .. import editor_core as ec
from ..core import load_rgb
from ..editor_session import EditorSession
from ..ui_widgets import (ColorSwatch, GradientButton, GradientSlider,
                          rounded_rect)

QUICK_COLORS = ("#ff3b30", "#ff9500", "#ffcc00", "#34c759",
                "#0a84ff", "#af52de", "#ffffff", "#000000")

PAINT_LABELS = (("brush", "Кисть"), ("eraser", "Ластик"), ("line", "Линия"),
                ("arrow", "Стрелка"), ("rect", "Рамка"), ("ellipse", "Овал"),
                ("text", "Текст"))
AREA_LABELS = (("mosaic", "Мозаика"), ("blur", "Размытие"))


def register(app):
    app.add_slot_action("Редактировать фото…",
                        lambda idx: open_editor(app, idx))
    app.add_menu_item("Правка", "Редактор фото…",
                      lambda: _open_for_current(app), accelerator="Ctrl+E")
    app.root.bind("<Control-e>", lambda e: _open_for_current(app))
    app.root.bind("<Control-E>", lambda e: _open_for_current(app))
    app.plugin_flags["photo_editor"] = True


def _open_for_current(app):
    """Слот для Ctrl+E: выделенный → единственный отмеченный → первый с фото."""
    idx = app.selected_slot
    if idx is None and len(app.marked) == 1:
        idx = next(iter(app.marked))
    if idx is None:
        idx = next((i for i, p in enumerate(app.photos) if p), None)
    if idx is None or app.photos[idx] is None:
        app.set_status("Сначала добавьте фото в слот")
        return
    open_editor(app, idx)


def open_editor(app, idx):
    win = getattr(app, "_photo_editor_win", None)
    try:
        if win is not None and win.top.winfo_exists():
            win.top.lift()
            win.top.focus_force()
            return win
    except Exception:
        pass
    if idx >= len(app.photos) or not app.photos[idx]:
        return None
    try:
        win = EditorWindow(app, idx)
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть фото в редакторе:\n{e}")
        return None
    app._photo_editor_win = win
    return win


# ======================================================================
#  Вкладки с «едущим» подчёркиванием
# ======================================================================
class _TabBar(tk.Canvas):
    def __init__(self, master, palette, tabs, command, height=40):
        super().__init__(master, height=height, bg=palette["surface"],
                         highlightthickness=0, cursor="hand2")
        self.p = palette
        self.tabs = list(tabs)
        self.command = command
        self.current = self.tabs[0][0]
        self._w = 330
        self._ux = 0.0
        self._uw = 0.0
        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_click)
        self._place_underline(animate=False)

    def _seg(self, key):
        n = max(1, len(self.tabs))
        i = [k for k, _ in self.tabs].index(key)
        w = self._w / n
        return i * w, w

    def _place_underline(self, animate=True):
        x, w = self._seg(self.current)
        if animate:
            anim.tween_attr(self, "_ux", x, duration=240,
                            easing=anim.ease_out_cubic)
            anim.tween_attr(self, "_uw", w, duration=240,
                            easing=anim.ease_out_cubic)
        else:
            self._ux, self._uw = x, w
            self._redraw()

    def select(self, key, animate=True):
        if key == self.current and self._uw:
            return
        self.current = key
        self._place_underline(animate)
        self._redraw()

    def _on_resize(self, e):
        self._w = max(100, e.width)
        self._place_underline(animate=False)

    def _on_click(self, e):
        n = max(1, len(self.tabs))
        i = max(0, min(n - 1, int(e.x // (self._w / n))))
        self.command(self.tabs[i][0])

    def _redraw(self):
        self.delete("all")
        p = self.p
        h = int(self["height"])
        seg = self._w / max(1, len(self.tabs))
        self.create_line(0, h - 1, self._w, h - 1, fill=p["border_soft"])
        for i, (key, label) in enumerate(self.tabs):
            cur = key == self.current
            self.create_text(
                i * seg + seg / 2, h / 2 - 2, text=label,
                fill=p["text"] if cur else p["text_dim"],
                font=("Segoe UI", 9, "bold" if cur else "normal"))
        rounded_rect(self, self._ux + 12, h - 4, self._ux + self._uw - 12,
                     h - 1, radius=1, fill=p["accent"], outline="")


# ======================================================================
#  Окно редактора
# ======================================================================
class EditorWindow:
    PAGES = (("frame", "Кадр"), ("color", "Цвет"), ("filters", "Фильтры"),
             ("draw", "Кисть"), ("areas", "Области"))

    def __init__(self, app, idx):
        self.app = app
        self.idx = idx
        self.p = app.palette
        self._src_path = app.photos[idx]

        full = load_rgb(self._src_path, app.config["bg_color"])
        self.session = EditorSession(full, bg=app.config["bg_color"])

        self.page = "frame"
        self.draw_tool = tk.StringVar(value="brush")
        self.area_tool = tk.StringVar(value="mosaic")
        self.draw_color = "#ff3b30"
        self.draw_size = 10.0
        self.draw_alpha = 100.0
        self.fill_var = tk.BooleanVar(value=False)

        self._render_job = None
        self._wheel_job = None
        self._compare = False
        self._busy = False
        self._rect = (0, 0, 1, 1)         # где на холсте нарисована картинка
        self._tk_img = None
        self._state_sliders = {}
        self._filter_btns = {}
        self._filter_imgs = {}

        self._build_window()
        self._select_page("frame", animate=False)
        self.top.update_idletasks()
        self._schedule_render()

    # ------------------------------------------------------------ окно
    def _build_window(self):
        p = self.p
        name = os.path.basename(self._src_path or "")
        self.top = tk.Toplevel(self.app.root)
        self.top.title(f"Редактор фото — {name}")
        self.top.configure(bg=p["bg"])
        self.top.geometry("1180x780")
        self.top.minsize(980, 660)
        self.top.transient(self.app.root)
        self.top.protocol("WM_DELETE_WINDOW", self._close_request)
        self.top.bind("<Escape>", lambda e: self._close_request())
        self.top.bind("<Control-z>", lambda e: self._undo())
        self.top.bind("<Control-y>", lambda e: self._redo())
        self.top.bind("<Control-Z>", lambda e: self._redo())

        # --- нижняя панель (создаём первой, чтобы не пропадала при сжатии)
        bottom = tk.Frame(self.top, bg=p["surface"])
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(bottom, bg=p["border_soft"], height=1).pack(fill=tk.X)
        bar = tk.Frame(bottom, bg=p["surface"])
        bar.pack(fill=tk.X, padx=16, pady=10)

        self.undo_btn = self._button(bar, "Отменить", self._undo)
        self.undo_btn.pack(side=tk.LEFT)
        self.redo_btn = self._button(bar, "Повторить", self._redo)
        self.redo_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._button(bar, "Сбросить всё", self._reset_all).pack(
            side=tk.LEFT, padx=(14, 0))
        cmp_btn = self._button(bar, "Удерживайте: оригинал", None)
        cmp_btn.pack(side=tk.LEFT, padx=(14, 0))
        cmp_btn.bind("<ButtonPress-1>", lambda e: self._set_compare(True))
        cmp_btn.bind("<ButtonRelease-1>", lambda e: self._set_compare(False))

        self.apply_btn = GradientButton(
            bar, p, text="Применить к фото", icon="save", height=38,
            command=self._apply)
        self.apply_btn.pack(side=tk.RIGHT)
        self._button(bar, "Отмена", self._close_request).pack(
            side=tk.RIGHT, padx=(0, 8))
        self.status = tk.Label(bar, text="", bg=p["surface"], fg=p["text_dim"],
                               font=("Segoe UI", 9))
        self.status.pack(side=tk.RIGHT, padx=(0, 16))

        # --- правая панель
        side_outer = tk.Frame(self.top, bg=p["border"], width=332)
        side_outer.pack(side=tk.RIGHT, fill=tk.Y)
        side_outer.pack_propagate(False)
        side = tk.Frame(side_outer, bg=p["surface"])
        side.pack(fill=tk.BOTH, expand=True, padx=(1, 0))

        self.tabbar = _TabBar(side, p, self.PAGES, self._select_page)
        self.tabbar.pack(fill=tk.X)
        self.hint = tk.Label(side, text="", bg=p["surface"], fg=p["text_dim"],
                             font=("Segoe UI", 9), justify="left",
                             anchor="w", wraplength=292)
        self.hint.pack(fill=tk.X, padx=18, pady=(12, 2))
        self.host = tk.Frame(side, bg=p["surface"])
        self.host.pack(fill=tk.BOTH, expand=True)

        self.pages = {}
        for key, builder in (("frame", self._build_frame_page),
                             ("color", self._build_color_page),
                             ("filters", self._build_filters_page),
                             ("draw", self._build_draw_page),
                             ("areas", self._build_areas_page)):
            f = tk.Frame(self.host, bg=p["surface"])
            builder(f)
            self.pages[key] = f

        # --- холст
        stage = tk.Frame(self.top, bg=p["bg"])
        stage.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(stage, bg=p["bg"], highlightthickness=0,
                                cursor="fleur")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        self.canvas.bind("<Configure>", lambda e: self._schedule_render())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", lambda e: self.canvas.delete("ring"))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._wheel_zoom(1.1))
        self.canvas.bind("<Button-5>", lambda e: self._wheel_zoom(1 / 1.1))

        try:                                # плавное появление окна
            self.top.attributes("-alpha", 0.0)
            anim.get(self.top).animate(
                200, lambda t: self.top.attributes("-alpha", t),
                on_done=lambda: self.top.attributes("-alpha", 1.0),
                key="editor-fade")
        except Exception:
            pass

    # ----------------------------------------------------- мелкие виджеты
    def _button(self, parent, text, command, accent=False, width=None):
        p = self.p
        bg = p["accent"] if accent else p["surface_alt"]
        fg = "#ffffff" if accent else p["text"]
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                        activebackground=p["surface_hi"], activeforeground=fg,
                        disabledforeground=p["text_faint"], bd=0,
                        relief="flat", cursor="hand2", highlightthickness=0,
                        font=("Segoe UI", 9), padx=12, pady=7,
                        **({"width": width} if width else {}))
        btn.bind("<Enter>", lambda e: btn.cget("state") == "normal"
                 and btn.config(bg=p["accent_hi"] if accent else p["surface_hi"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def _slider(self, parent, label, lo, hi, value, on_change, fmt="{:.0f}",
                unit="", step=1, checkpoint=True):
        p = self.p
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill=tk.X, padx=18, pady=(8, 0))
        head = tk.Frame(row, bg=p["surface"])
        head.pack(fill=tk.X)
        tk.Label(head, text=label, bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)
        val = tk.Label(head, text=fmt.format(value) + unit, bg=p["surface"],
                       fg=p["text_dim"], font=("Segoe UI", 9, "bold"))
        val.pack(side=tk.RIGHT)
        sl = GradientSlider(row, p, from_=lo, to=hi, value=value, height=22,
                            step=step,
                            command=lambda v: (val.config(
                                text=fmt.format(v) + unit), on_change(v)))
        sl.pack(fill=tk.X)
        if checkpoint:
            sl.on_press = self.session.checkpoint
        return sl, val

    def _state_slider(self, parent, label, key, scale=1.0, **kw):
        lo, hi, default = ec.RANGES[key]
        fmt, unit = kw.pop("fmt", "{:.0f}"), kw.pop("unit", "")

        def changed(ui):
            self.session.set_value(key, ui / scale)
            self._schedule_render()
            self._update_buttons()

        sl, val = self._slider(parent, label, lo * scale, hi * scale,
                               self.session.state.v[key] * scale, changed,
                               fmt=fmt, unit=unit, **kw)
        self._state_sliders[key] = (sl, val, scale, fmt, unit)
        return sl

    def _section(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=self.p["surface"],
                 fg=self.p["text_faint"], font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill=tk.X, padx=18, pady=(16, 0))

    def _row(self, parent):
        row = tk.Frame(parent, bg=self.p["surface"])
        row.pack(fill=tk.X, padx=18, pady=(8, 0))
        return row

    # ----------------------------------------------------------- страницы
    def _build_frame_page(self, f):
        self._section(f, "Положение")
        r = self._row(f)
        self._button(r, "Влево 90°", lambda: self._do(self.session.rotate90, -1)
                     ).pack(side=tk.LEFT)
        self._button(r, "Вправо 90°", lambda: self._do(self.session.rotate90, 1)
                     ).pack(side=tk.LEFT, padx=(6, 0))
        r = self._row(f)
        self._button(r, "Отразить ↔", lambda: self._do(self.session.flip, True)
                     ).pack(side=tk.LEFT)
        self._button(r, "Отразить ↕", lambda: self._do(self.session.flip, False)
                     ).pack(side=tk.LEFT, padx=(6, 0))

        self._section(f, "Масштаб")
        r = self._row(f)
        self._button(r, "Дальше", lambda: self._zoom_step(1 / 1.2)).pack(side=tk.LEFT)
        self._button(r, "Ближе", lambda: self._zoom_step(1.2)).pack(
            side=tk.LEFT, padx=(6, 0))
        self._button(r, "По центру", self._center).pack(side=tk.LEFT, padx=(6, 0))
        self._state_slider(f, "Масштаб", "zoom", scale=100.0, unit="%")
        self._state_slider(f, "Наклон", "angle", unit="°")
        r = self._row(f)
        self._button(r, "Сбросить кадр",
                     lambda: self._do(self.session.reset_frame)).pack(side=tk.LEFT)

    def _build_color_page(self, f):
        self._section(f, "Цвет и свет")
        self._state_slider(f, "Яркость", "brightness")
        self._state_slider(f, "Контраст", "contrast")
        self._state_slider(f, "Насыщенность", "saturation")
        self._state_slider(f, "Резкость", "sharpness")
        self._state_slider(f, "Тепло", "warmth")
        r = self._row(f)
        self._button(r, "Авто-улучшение",
                     lambda: self._do(self.session.auto_enhance),
                     accent=True).pack(side=tk.LEFT)
        self._button(r, "Сбросить",
                     lambda: self._do(self.session.reset_color)
                     ).pack(side=tk.LEFT, padx=(6, 0))

    def _build_filters_page(self, f):
        p = self.p
        self._section(f, "Фильтры")
        grid = tk.Frame(f, bg=p["surface"])
        grid.pack(fill=tk.X, padx=14, pady=(8, 0))
        previews = self.session.filter_previews(84)
        for i, (name, label) in enumerate(ec.FILTERS.items()):
            img = ImageTk.PhotoImage(previews[name])
            self._filter_imgs[name] = img
            b = tk.Button(grid, image=img, text=label, compound="top",
                          bg=p["surface_alt"], fg=p["text"],
                          activebackground=p["surface_hi"],
                          activeforeground=p["text"], bd=0, relief="flat",
                          cursor="hand2", highlightthickness=0,
                          font=("Segoe UI", 8), padx=4, pady=4,
                          command=lambda n=name: self._pick_filter(n))
            b.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="nsew")
            self._filter_btns[name] = b
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="flt")
        self._section(f, "Эффекты")
        self._state_slider(f, "Размытие", "blur", fmt="{:.1f}", step=0.1)
        self._state_slider(f, "Виньетка", "vignette")

    def _tool_buttons(self, parent, labels, var, columns=4):
        p = self.p
        box = tk.Frame(parent, bg=p["surface"])
        box.pack(fill=tk.X, padx=14, pady=(8, 0))
        btns = {}

        def refresh(*_):
            for key, b in btns.items():
                sel = var.get() == key
                b.config(bg=p["accent"] if sel else p["surface_alt"],
                         fg="#ffffff" if sel else p["text"])

        for i, (key, label) in enumerate(labels):
            b = tk.Button(box, text=label, bd=0, relief="flat",
                          cursor="hand2", highlightthickness=0,
                          font=("Segoe UI", 9), padx=6, pady=7,
                          activebackground=p["surface_hi"],
                          command=lambda k=key: (var.set(k), refresh(),
                                                 self._tool_changed()))
            b.grid(row=i // columns, column=i % columns, padx=3, pady=3,
                   sticky="nsew")
            btns[key] = b
        for c in range(columns):
            box.columnconfigure(c, weight=1, uniform="tool")
        refresh()
        return refresh

    def _build_draw_page(self, f):
        p = self.p
        self._section(f, "Инструмент")
        self._tool_buttons(f, PAINT_LABELS, self.draw_tool)

        self._section(f, "Цвет")
        r = self._row(f)
        self.color_swatch = ColorSwatch(r, p, color=self.draw_color, size=34,
                                        command=self._choose_color)
        self.color_swatch.pack(side=tk.LEFT)
        pal = tk.Frame(r, bg=p["surface"])
        pal.pack(side=tk.LEFT, padx=(10, 0))
        for i, c in enumerate(QUICK_COLORS):
            sw = tk.Canvas(pal, width=20, height=20, bg=p["surface"],
                           highlightthickness=0, cursor="hand2")
            rounded_rect(sw, 1, 1, 19, 19, radius=5, fill=c,
                         outline=p["border"])
            sw.grid(row=i // 4, column=i % 4, padx=2, pady=2)
            sw.bind("<Button-1>", lambda e, col=c: self._set_color(col))

        self._slider(f, "Толщина / размер", 1, 40, self.draw_size,
                     lambda v: setattr(self, "draw_size", v), checkpoint=False)
        self._slider(f, "Непрозрачность", 10, 100, self.draw_alpha,
                     lambda v: setattr(self, "draw_alpha", v), unit="%",
                     checkpoint=False)
        r = self._row(f)
        ttk.Checkbutton(r, text="Заливка для рамки и овала",
                        variable=self.fill_var).pack(side=tk.LEFT)
        r = self._row(f)
        self._button(r, "Убрать все рисунки", self._clear_drawing
                     ).pack(side=tk.LEFT)

    def _build_areas_page(self, f):
        self._section(f, "Скрыть область")
        self._tool_buttons(f, AREA_LABELS, self.area_tool, columns=2)
        tk.Label(f, text="Выделите прямоугольник мышью: номера, лица, "
                         "адреса и другое, что не должно быть видно.",
                 bg=self.p["surface"], fg=self.p["text_dim"],
                 font=("Segoe UI", 9), justify="left", anchor="w",
                 wraplength=292).pack(fill=tk.X, padx=18, pady=(12, 0))
        r = self._row(f)
        self._button(r, "Убрать все области и рисунки", self._clear_drawing
                     ).pack(side=tk.LEFT)

    # ---------------------------------------------------------- страницы
    HINTS = {
        "frame": "Колесо мыши — ближе/дальше, перетаскивание — сдвиг кадра.",
        "color": "Изменения видны сразу. «Удерживайте: оригинал» — сравнить.",
        "filters": "Выберите фильтр, затем подстройте размытие и виньетку.",
        "draw": "Рисуйте прямо на фото. Рисунок привязан к кадру.",
        "areas": "Протягивайте рамку по фото, чтобы скрыть область.",
    }

    def _select_page(self, key, animate=True):
        self.page = key
        for k, fr in self.pages.items():
            fr.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)
        self.tabbar.select(key, animate=animate)
        self.hint.config(text=self.HINTS.get(key, ""))
        self._tool_changed()

    def _current_tool(self):
        return {"frame": "pan", "draw": self.draw_tool.get(),
                "areas": self.area_tool.get()}.get(self.page)

    def _tool_changed(self):
        tool = self._current_tool()
        cursor = {"pan": "fleur", None: "arrow", "text": "xterm"}.get(
            tool, "crosshair")
        try:
            self.canvas.config(cursor=cursor)
        except tk.TclError:
            pass
        self.canvas.delete("ring")

    # ------------------------------------------------------- действия
    def _do(self, fn, *args):
        fn(*args)
        self._after_change()

    def _after_change(self):
        self._sync_controls()
        self._schedule_render()
        self._update_buttons()

    def _undo(self):
        if self.session.undo():
            self._after_change()

    def _redo(self):
        if self.session.redo():
            self._after_change()

    def _reset_all(self):
        self.session.reset_all()
        self._after_change()

    def _clear_drawing(self):
        if self.session.clear_drawing():
            self._after_change()

    def _center(self):
        self.session.checkpoint()
        self.session.state.set("pan_x", 0.0)
        self.session.state.set("pan_y", 0.0)
        self._after_change()

    def _zoom_step(self, factor):
        self.session.zoom_by(factor)
        self._after_change()

    def _pick_filter(self, name):
        self.session.set_filter(name)
        self._after_change()

    def _set_compare(self, on):
        self._compare = on
        self._schedule_render()

    def _choose_color(self):
        c = colorchooser.askcolor(color=self.draw_color, parent=self.top,
                                  title="Цвет")[1]
        if c:
            self._set_color(c)

    def _set_color(self, c):
        self.draw_color = c
        self.color_swatch.set_color(c)

    def _style(self):
        return {"color": self.draw_color, "size": self.draw_size,
                "alpha": self.draw_alpha / 100.0, "fill": self.fill_var.get()}

    def _sync_controls(self):
        v = self.session.state.v
        for key, (sl, val, scale, fmt, unit) in self._state_sliders.items():
            ui = v[key] * scale
            sl.set(ui, notify=False)
            val.config(text=fmt.format(ui) + unit)
        for name, b in self._filter_btns.items():
            sel = v["filter"] == name
            b.config(bg=self.p["accent"] if sel else self.p["surface_alt"],
                     fg="#ffffff" if sel else self.p["text"])

    def _update_buttons(self):
        try:
            self.undo_btn.config(
                state="normal" if self.session.can_undo else "disabled")
            self.redo_btn.config(
                state="normal" if self.session.can_redo else "disabled")
        except tk.TclError:
            pass

    # ------------------------------------------------------------ рендер
    def _schedule_render(self):
        if self._render_job is None:
            try:
                self._render_job = self.top.after(12, self._render_now)
            except tk.TclError:
                self._render_job = None

    def _render_now(self):
        self._render_job = None
        try:
            if not self.top.winfo_exists():
                return
            img = self.session.render_view(compare=self._compare)
            self._show(img)
        except tk.TclError:
            return
        except Exception as e:
            self.status.config(text=f"Ошибка: {e}")

    def _show(self, img):
        cw = max(60, self.canvas.winfo_width())
        ch = max(60, self.canvas.winfo_height())
        scale = min((cw - 8) / img.width, (ch - 8) / img.height, 2.0)
        dw, dh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
        disp = img if (dw, dh) == img.size else img.resize(
            (dw, dh), Image.BILINEAR)
        self._tk_img = ImageTk.PhotoImage(disp)
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        self._rect = (ox, oy, dw, dh)
        self.canvas.delete("img")
        self.canvas.create_rectangle(ox - 1, oy - 1, ox + dw, oy + dh,
                                     outline=self.p["border"], tags="img")
        self.canvas.create_image(ox, oy, image=self._tk_img, anchor="nw",
                                 tags="img")
        self.canvas.tag_lower("img")
        self._draw_overlay()
        self._update_buttons()

    def _draw_overlay(self):
        self.canvas.delete("ov")
        rect = self.session.area_rect()
        if rect:
            ox, oy, dw, dh = self._rect
            x0, y0, x1, y1 = rect
            self.canvas.create_rectangle(
                ox + x0 * dw, oy + y0 * dh, ox + x1 * dw, oy + y1 * dh,
                outline=self.p["accent_hi"], dash=(5, 3), width=2, tags="ov")

    # ------------------------------------------------------------- мышь
    def _to_norm(self, x, y):
        ox, oy, dw, dh = self._rect
        return (x - ox) / max(1, dw), (y - oy) / max(1, dh)

    def _on_press(self, e):
        tool = self._current_tool()
        if tool is None:
            return
        nx, ny = self._to_norm(e.x, e.y)
        if tool == "text":
            self._ask_text(nx, ny)
            return
        if self.session.pointer_down(tool, nx, ny, self._style()):
            self._schedule_render()

    def _on_move(self, e):
        if not self.session.drawing:
            return
        nx, ny = self._to_norm(e.x, e.y)
        if self.session.pointer_move(nx, ny):
            self._schedule_render()
        self._draw_overlay()
        self._draw_ring(e.x, e.y)

    def _on_release(self, e):
        if not self.session.drawing:
            return
        nx, ny = self._to_norm(e.x, e.y)
        self.session.pointer_up(nx, ny)
        self._after_change()
        self._draw_overlay()

    def _on_hover(self, e):
        if not self.session.drawing:
            self._draw_ring(e.x, e.y)

    def _draw_ring(self, x, y):
        """Кружок размера кисти под курсором."""
        self.canvas.delete("ring")
        tool = self._current_tool()
        if tool not in ("brush", "eraser"):
            return
        from ..editor_session import BRUSH_UNIT
        _, _, dw, dh = self._rect
        r = max(2.0, self.draw_size * BRUSH_UNIT * max(dw, dh)
                * (1.6 if tool == "eraser" else 1.0) / 2)
        self.canvas.create_oval(x - r, y - r, x + r, y + r, outline="#ffffff",
                                tags="ring")
        self.canvas.create_oval(x - r - 1, y - r - 1, x + r + 1, y + r + 1,
                                outline="#000000", tags="ring")

    def _on_wheel(self, e):
        self._wheel_zoom(1.1 if e.delta > 0 else 1 / 1.1)

    def _wheel_zoom(self, factor):
        if self.page != "frame":
            return
        if self._wheel_job is None:
            self.session.checkpoint()          # серия щелчков = одна отмена
        else:
            try:
                self.top.after_cancel(self._wheel_job)
            except Exception:
                pass
        self._wheel_job = self.top.after(700, self._wheel_done)
        self.session.zoom_by(factor, checkpoint=False)
        self._sync_controls()
        self._schedule_render()

    def _wheel_done(self):
        self._wheel_job = None

    def _ask_text(self, nx, ny):
        text = simpledialog.askstring("Надпись", "Текст надписи:",
                                      parent=self.top)
        if text and self.session.add_text(nx, ny, text, self._style()):
            self._after_change()

    # ------------------------------------------------------ применить/выход
    def _apply(self):
        if self._busy:
            return
        if not self.session.changed:
            self._close()
            return
        self._busy = True
        self.status.config(text="Применяю…")
        self.apply_btn.config(cursor="watch")
        app, idx, src, session = (self.app, self.idx, self._src_path,
                                  self.session)
        out = app.new_temp_path("pe_edit")

        def work():
            img = session.render_full()          # полное разрешение
            img.save(out, "PNG", compress_level=3)
            return out

        def done(path):
            self._busy = False
            if (idx < len(app.photos) and app.photos[idx] == src):
                app._push_undo("Редактор фото")
                app.photos[idx] = path
                app.update_slot(idx, animate=True)
                app.schedule_preview()
                app.update_status()
                app.toasts.show("Фото обработано", kind="success",
                                action=("Вернуть", app.undo))
            else:
                app.toasts.show("Фото в слоте уже заменено — "
                                "результат не применён", kind="warn")
            self._close()

        def fail(e):
            self._busy = False
            self.status.config(text="")
            messagebox.showerror("Ошибка",
                                 f"Не удалось применить правки:\n{e}",
                                 parent=self.top)

        app.run_task(work, done, fail)

    def _close_request(self):
        if self._busy:
            return
        if self.session.changed and not messagebox.askyesno(
                "Закрыть редактор",
                "Закрыть без применения изменений?", parent=self.top):
            return
        self._close()

    def _close(self):
        for job in (self._render_job, self._wheel_job):
            if job is not None:
                try:
                    self.top.after_cancel(job)
                except Exception:
                    pass
        self._render_job = self._wheel_job = None
        try:
            anim.get(self.top).cancel("editor-fade")
        except Exception:
            pass
        if getattr(self.app, "_photo_editor_win", None) is self:
            self.app._photo_editor_win = None
        try:
            self.top.destroy()
        except Exception:
            pass
