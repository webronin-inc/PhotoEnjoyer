"""Кастомные виджеты. Иконки — Segoe MDL2 Assets (Windows 10/11)."""
import tkinter as tk
import math
import random


# ==============================================================
#  Скруглённый прямоугольник
# ==============================================================
def rounded_rect(canvas, x1, y1, x2, y2, radius=8, **kwargs):
    points = [
        x1 + radius, y1, x1 + radius, y1,
        x2 - radius, y1, x2 - radius, y1,
        x2, y1, x2, y1 + radius, x2, y1 + radius,
        x2, y2 - radius, x2, y2 - radius, x2, y2,
        x2 - radius, y2, x2 - radius, y2,
        x1 + radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y2 - radius,
        x1, y1 + radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ==============================================================
#  Иконочный шрифт
# ==============================================================
_ICON_FONT = None
_ICON_AVAILABLE = None


def _detect_icon_font():
    global _ICON_FONT, _ICON_AVAILABLE
    if _ICON_AVAILABLE is not None:
        return _ICON_AVAILABLE
    try:
        import tkinter.font as tkfont
        root = tk._default_root
        if root is None:
            _ICON_AVAILABLE = False
            return False
        families = set(tkfont.families(root))
        for name in ("Segoe MDL2 Assets", "Segoe Fluent Icons"):
            if name in families:
                _ICON_FONT = name
                _ICON_AVAILABLE = True
                return True
        _ICON_AVAILABLE = False
        return False
    except Exception:
        _ICON_AVAILABLE = False
        return False


_ICON_CHARS = {
    "collage":   "\uE91B",
    "plugins":   "\uE71D",
    "batch":     "\uE8F1",
    "cloud":     "\uE753",
    "save":      "\uE74E",
    "folder":    "\uE8B7",
    "refresh":   "\uE72C",
    "download":  "\uE896",
    "upload":    "\uE898",
    "check":     "\uE73E",
    "plus":      "\uE710",
    "delete":    "\uE74D",
    "shuffle":   "\uE8B1",
    "clear":     "\uE894",
    "theme":     "\uE706",
    "theme_alt": "\uE708",
    "settings":  "\uE713",
    "help":      "\uE897",
    "bell":      "\uEA8F",
    "info":      "\uE946",
    "close":     "\uE711",
    "menu":      "\uE700",
    "layers":    "\uE81E",
    "image":     "\uE91B",
}


def draw_icon(canvas, kind, cx, cy, size=20, color="#ffffff"):
    if _detect_icon_font():
        char = _ICON_CHARS.get(kind)
        if char:
            font_size = int(size * 0.92)
            canvas.create_text(cx, cy + 1, text=char, fill=color,
                               font=(_ICON_FONT, font_size))
            return
    _draw_fallback_icon(canvas, kind, cx, cy, size, color)


def _draw_fallback_icon(canvas, kind, cx, cy, size=20, color="#ffffff"):
    s = size
    LW = 1.7
    CAP = "round"

    if kind in ("collage", "image"):
        q = s * 0.32
        gap = s * 0.1
        for dx, dy in [(-q - gap/2, -q - gap/2), (gap/2, -q - gap/2),
                       (-q - gap/2, gap/2), (gap/2, gap/2)]:
            canvas.create_rectangle(cx + dx, cy + dy,
                                    cx + dx + q, cy + dy + q,
                                    outline=color, width=LW)
    elif kind in ("theme", "sun"):
        r = s * 0.22
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=color, width=LW)
        for i in range(8):
            a = i * math.pi / 4
            x1 = cx + (r + s * 0.06) * math.cos(a)
            y1 = cy + (r + s * 0.06) * math.sin(a)
            x2 = cx + (r + s * 0.18) * math.cos(a)
            y2 = cy + (r + s * 0.18) * math.sin(a)
            canvas.create_line(x1, y1, x2, y2, fill=color, width=LW, capstyle=CAP)
    elif kind == "help":
        r = s * 0.44
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=color, width=LW)
        canvas.create_text(cx, cy + 1, text="?", fill=color,
                           font=("Segoe UI", int(s * 0.55), "bold"))
    elif kind == "settings":
        r = s * 0.28
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=color, width=LW)
        for i in range(8):
            a = i * math.pi / 4
            x1 = cx + r * math.cos(a)
            y1 = cy + r * math.sin(a)
            x2 = cx + (r + s * 0.18) * math.cos(a)
            y2 = cy + (r + s * 0.18) * math.sin(a)
            canvas.create_line(x1, y1, x2, y2, fill=color, width=LW, capstyle=CAP)
    else:
        canvas.create_polygon(
            cx, cy - s*0.35, cx + s*0.35, cy,
            cx, cy + s*0.35, cx - s*0.35, cy,
            fill="", outline=color, width=LW,
        )


# ==============================================================
#  Tooltip
# ==============================================================
class Tooltip:
    def __init__(self, widget, text, palette, delay=450):
        self.widget = widget
        self.text = text
        self.palette = palette
        self.delay = delay
        self._after_id = None
        self._tip = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button-1>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
            y = self.widget.winfo_rooty() + (self.widget.winfo_height() // 2)
        except Exception:
            return

        p = self.palette
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.configure(bg=p["border"])
        try:
            tip.attributes("-topmost", True)
        except Exception:
            pass

        frame = tk.Frame(tip, bg=p["surface"], bd=0)
        frame.pack(padx=1, pady=1)
        tk.Label(frame, text=self.text, bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 9), padx=10, pady=5).pack()

        tip.update_idletasks()
        w = tip.winfo_width()
        h = tip.winfo_height()
        screen_w = tip.winfo_screenwidth()
        if x + w > screen_w - 8:
            x = self.widget.winfo_rootx() - w - 8
        tip.wm_geometry(f"+{x}+{y - h // 2}")
        self._tip = tip

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


# ==============================================================
#  Кнопка меню
# ==============================================================
class ModernMenuButton(tk.Button):
    def __init__(self, master, text, palette, menu, **kwargs):
        super().__init__(
            master, text=text,
            bg=palette["bg"], fg=palette["text_dim"],
            activebackground=palette["surface_alt"],
            activeforeground=palette["text"],
            bd=0, relief="flat", highlightthickness=0,
            padx=14, pady=6, cursor="hand2",
            font=("Segoe UI", 10),
            command=self._open_menu, **kwargs,
        )
        self._palette = palette
        self._menu = menu
        self.bind("<Enter>", lambda e: self.config(
            bg=palette["surface_alt"], fg=palette["text"]))
        self.bind("<Leave>", lambda e: self.config(
            bg=palette["bg"], fg=palette["text_dim"]))

    def _open_menu(self):
        try:
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height() + 4
            self._menu.tk_popup(x, y)
        finally:
            self._menu.grab_release()


def style_dropdown(menu, palette):
    try:
        menu.configure(
            bg=palette["surface"], fg=palette["text"],
            activebackground=palette["accent"],
            activeforeground="#ffffff",
            bd=0, relief="flat", activeborderwidth=0,
            font=("Segoe UI", 10),
        )
    except tk.TclError:
        pass


# ==============================================================
#  Логотип
# ==============================================================
class LogoMark(tk.Canvas):
    def __init__(self, master, palette, size=40, letter="P", **kwargs):
        super().__init__(
            master, width=size, height=size,
            bg=palette["bg"], highlightthickness=0, **kwargs,
        )
        s = size
        rounded_rect(self, 0, 0, s, s, radius=int(s * 0.28),
                     fill=palette["accent"], outline="")
        self.create_text(s / 2, s / 2 + 1, text=letter, fill="#ffffff",
                         font=("Segoe UI", int(s * 0.46), "bold"))


# ==============================================================
#  Кнопка раздела в рельсе
# ==============================================================
class RailButton(tk.Canvas):
    def __init__(self, master, palette, kind, size=42,
                 command=None, tooltip=None, **kwargs):
        super().__init__(
            master, width=size, height=size,
            bg=palette["bg"], highlightthickness=0,
            cursor="hand2", **kwargs,
        )
        self.palette = palette
        self.kind = kind
        self.size = size
        self._command = command
        self._hover = False
        self._active = False

        self.bind("<Button-1>", lambda e: command() if command else None)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

        if tooltip:
            Tooltip(self, tooltip, palette)

    def set_active(self, active):
        self._active = active
        self._redraw()

    def _set_hover(self, h):
        self._hover = h
        self._redraw()

    def _redraw(self):
        self.delete("all")
        p = self.palette
        s = self.size
        cx = s / 2

        if self._active:
            rounded_rect(self, 4, 4, s - 4, s - 4, radius=11,
                         fill=p["surface_alt"], outline="")
            rounded_rect(self, -8, s * 0.28, -4, s * 0.72, radius=2,
                         fill=p["accent"], outline="")
            color = p["accent_hi"]
        elif self._hover:
            rounded_rect(self, 4, 4, s - 4, s - 4, radius=11,
                         fill=p["surface_alt"], outline="")
            color = p["text"]
        else:
            color = p["text_dim"]

        draw_icon(self, self.kind, cx, cx, size=22, color=color)


# ==============================================================
#  Акцентная кнопка
# ==============================================================
class GradientButton(tk.Canvas):
    def __init__(self, master, palette, text, icon=None,
                 height=44, padx=18, command=None, **kwargs):
        self.palette = palette
        self.text = text
        self.icon = icon
        self._command = command
        self._hover = False

        import tkinter.font as tkfont
        try:
            f = tkfont.Font(font=("Segoe UI", 10, "bold"))
            text_w = f.measure(text)
        except Exception:
            text_w = len(text) * 8

        icon_w = 22 if icon else 0
        icon_gap = 10 if icon else 0
        w = padx * 2 + icon_w + icon_gap + text_w
        h = height

        super().__init__(
            master, width=w, height=h,
            bg=palette["surface"], highlightthickness=0,
            cursor="hand2", **kwargs,
        )
        self.bind("<Button-1>", lambda e: self._invoke())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

    def _invoke(self):
        if self._command:
            self._command()

    def _set_hover(self, h):
        self._hover = h
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w = int(self["width"])
        h = int(self["height"])
        p = self.palette

        color = p["accent_hi"] if self._hover else p["accent"]
        rounded_rect(self, 0, 0, w, h, radius=12,
                     fill=color, outline="")

        cx = 18
        cy = h / 2
        if self.icon:
            draw_icon(self, self.icon, cx + 9, cy, size=18, color="#ffffff")
            cx += 30
        self.create_text(cx, cy, text=self.text, fill="#ffffff",
                         font=("Segoe UI", 10, "bold"), anchor="w")


# ==============================================================
#  Слайдер
# ==============================================================
class GradientSlider(tk.Canvas):
    def __init__(self, master, palette, from_=0, to=100, value=50,
                 command=None, height=28, step=None, **kwargs):
        super().__init__(
            master, height=height,
            bg=palette["surface"], highlightthickness=0,
            cursor="hand2", **kwargs,
        )
        self.palette = palette
        self.from_ = float(from_)
        self.to = float(to)
        self.value = float(value)
        self._command = command
        self._track_y = height / 2
        self._width = 100
        self._hover = False
        self._drag = False

        if step is None:
            self._step = max(1.0, (self.to - self.from_) / 100.0)
        else:
            self._step = float(step)

        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        self.bind("<Left>",  lambda e: self._nudge(-1))
        self.bind("<Right>", lambda e: self._nudge(+1))
        self.bind("<Home>",  lambda e: self._set(self.from_))
        self.bind("<End>",   lambda e: self._set(self.to))

        try:
            self.configure(takefocus=1)
        except Exception:
            pass

    def set(self, v):
        self._set(v)

    def get(self):
        return self.value

    def _set(self, v, notify=True):
        v = max(self.from_, min(self.to, float(v)))
        self.value = v
        self._redraw()
        if notify and self._command:
            self._command(self.value)

    def _nudge(self, direction):
        self._set(self.value + direction * self._step)
        return "break"

    def _on_enter(self, event):
        self._hover = True
        self._redraw()
        self.bind_all("<MouseWheel>", self._on_wheel_global)
        self.bind_all("<Button-4>", lambda e: self._nudge(+1))
        self.bind_all("<Button-5>", lambda e: self._nudge(-1))

    def _on_leave(self, event):
        if self._drag:
            return
        self._hover = False
        self._redraw()
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_wheel_global(self, event):
        if event.delta > 0:
            self._nudge(+1)
        elif event.delta < 0:
            self._nudge(-1)
        return "break"

    def _on_resize(self, e):
        self._width = e.width
        self._redraw()

    def _on_press(self, e):
        self._drag = True
        try:
            self.focus_set()
        except Exception:
            pass
        self._update_from_x(e.x)

    def _on_drag(self, e):
        self._update_from_x(e.x)

    def _on_release(self, e):
        self._drag = False

    def _update_from_x(self, x):
        pad = 14
        w = max(1, self._width - pad * 2)
        t = max(0.0, min(1.0, (x - pad) / w))
        new_val = self.from_ + t * (self.to - self.from_)
        self._set(new_val)

    def _redraw(self):
        self.delete("all")
        p = self.palette
        w = max(1, self._width)
        y = self._track_y
        pad = 14

        rounded_rect(self, pad, y - 2, w - pad, y + 2, radius=2,
                     fill=p["surface_hi"], outline="")

        t = (self.value - self.from_) / (self.to - self.from_) \
            if self.to != self.from_ else 0
        progress_x = pad + (w - pad * 2) * t

        if progress_x > pad:
            rounded_rect(self, pad, y - 2, progress_x, y + 2, radius=2,
                         fill=p["accent"], outline="")

        r = 9 if self._hover else 8
        cx = progress_x
        self.create_oval(cx - r, y - r + 1, cx + r, y + r + 1,
                         fill=p["shadow"], outline="")
        border_color = p["accent_hi"] if self._hover else p["accent"]
        self.create_oval(cx - r, y - r, cx + r, y + r,
                         fill="#ffffff", outline=border_color, width=2)


# ==============================================================
#  IconButton
# ==============================================================
class IconButton(tk.Canvas):
    def __init__(self, master, palette, kind="theme", size=36,
                 command=None, tooltip=None, **kwargs):
        super().__init__(
            master, width=size, height=size,
            bg=palette["bg"], highlightthickness=0,
            cursor="hand2", **kwargs,
        )
        self.palette = palette
        self.size = size
        self.kind = kind
        self._command = command
        self._hover = False

        self.bind("<Button-1>", lambda e: command() if command else None)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

        if tooltip:
            Tooltip(self, tooltip, palette)

    def _set_hover(self, h):
        self._hover = h
        self._redraw()

    def _redraw(self):
        self.delete("all")
        p = self.palette
        s = self.size

        if self._hover:
            rounded_rect(self, 3, 3, s - 3, s - 3, radius=9,
                         fill=p["surface_alt"], outline="")

        color = p["text"] if self._hover else p["text_dim"]
        draw_icon(self, self.kind, s / 2, s / 2, size=18, color=color)


# ==============================================================
#  Слот под фото
# ==============================================================
class Slot(tk.Canvas):
    W = 168
    H = 168
    RADIUS = 14

    def __init__(self, master, palette, index,
                 on_click, on_right_click, on_double_click):
        super().__init__(
            master, width=self.W, height=self.H,
            bg=palette["surface"], highlightthickness=0,
            cursor="hand2",
        )
        self.palette = palette
        self.index = index
        self.state = "empty"
        self.hover = False
        self.selected = False
        self.thumb = None

        self.bind("<Button-1>", on_click)
        self.bind("<Button-3>", on_right_click)
        self.bind("<Double-Button-1>", on_double_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._redraw()

    def _on_enter(self, _):
        self.hover = True
        self._redraw()

    def _on_leave(self, _):
        self.hover = False
        self._redraw()

    def set_thumb(self, photo_image):
        self.thumb = photo_image
        self.state = "filled" if photo_image else "empty"
        self._redraw()

    def update_border(self, selected=False):
        self.selected = selected
        self._redraw()

    def _redraw(self):
        self.delete("all")
        p = self.palette
        w, h = self.W, self.H
        r = self.RADIUS

        if self.selected:
            bc, bw, bg = p["accent"], 2, p["accent_soft"]
        elif self.hover:
            bc, bw, bg = p["accent_hi"], 1, p["surface_hi"]
        else:
            bc, bw, bg = p["slot_border"], 1, p["slot_bg"]

        rounded_rect(self, 1, 1, w - 1, h - 1, radius=r,
                     fill=bg, outline=bc, width=bw)

        if self.state == "filled" and self.thumb:
            self.create_image(w / 2, h / 2, image=self.thumb, anchor="center")
        else:
            cx, cy = w / 2, h / 2
            color = p["accent"] if self.hover else p["text_faint"]
            if _detect_icon_font():
                self.create_text(cx, cy - 20, text=_ICON_CHARS["plus"],
                                 fill=color, font=(_ICON_FONT, 22))
            else:
                ps = 22
                self.create_line(cx - ps/2, cy - 22, cx + ps/2, cy - 22,
                                 fill=color, width=2, capstyle="round")
                self.create_line(cx, cy - 22 - ps/2, cx, cy - 22 + ps/2,
                                 fill=color, width=2, capstyle="round")
            tc = p["text"] if self.hover else p["text_dim"]
            self.create_text(cx, cy + 30, text=f"Фото {self.index + 1}",
                             fill=tc, font=("Segoe UI", 10))


# ==============================================================
#  ColorSwatch
# ==============================================================
class ColorSwatch(tk.Canvas):
    def __init__(self, master, palette, color="#ffffff", size=40,
                 command=None, **kwargs):
        super().__init__(
            master, width=size, height=size,
            bg=palette["surface"], highlightthickness=0,
            cursor="hand2", **kwargs,
        )
        self.palette = palette
        self.size = size
        self.color = color
        self._command = command
        self._hover = False

        self.bind("<Button-1>", lambda e: command() if command else None)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

    def set_color(self, color):
        self.color = color
        self._redraw()

    def _set_hover(self, h):
        self._hover = h
        self._redraw()

    def _redraw(self):
        self.delete("all")
        p = self.palette
        s = self.size
        border = p["accent"] if self._hover else p["border"]
        bw = 2 if self._hover else 1
        rounded_rect(self, 1, 1, s - 1, s - 1, radius=8,
                     fill="", outline=border, width=bw)
        pad = 5
        rounded_rect(self, pad, pad, s - pad, s - pad, radius=5,
                     fill=self.color, outline="")
        try:
            h = self.color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            if r + g + b > 600:
                rounded_rect(self, pad, pad, s - pad, s - pad, radius=5,
                             fill="", outline=p["border"], width=1)
        except Exception:
            pass


# ==============================================================
#  HoverButton
# ==============================================================
class HoverButton(tk.Button):
    def __init__(self, master, normal_bg, hover_bg,
                 normal_fg=None, hover_fg=None, **kwargs):
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(
            master, bg=normal_bg,
            fg=normal_fg or kwargs.pop("fg", "#ffffff"),
            activebackground=hover_bg,
            activeforeground=hover_fg or kwargs.pop("activeforeground", "#ffffff"),
            **kwargs,
        )
        self._normal_bg = normal_bg
        self._hover_bg = hover_bg
        self._normal_fg = normal_fg
        self._hover_fg = hover_fg
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        self.config(bg=self._hover_bg)
        if self._hover_fg:
            self.config(fg=self._hover_fg)

    def _on_leave(self, _):
        self.config(bg=self._normal_bg)
        if self._normal_fg:
            self.config(fg=self._normal_fg)


# ==============================================================
#  Колесо мыши для прокручиваемых Canvas
# ==============================================================
def enable_mousewheel(canvas):
    def _on_wheel(event):
        if event.delta:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _on_wheel_linux_up(event):
        canvas.yview_scroll(-1, "units")
        return "break"

    def _on_wheel_linux_down(event):
        canvas.yview_scroll(1, "units")
        return "break"

    def _on_enter(event):
        canvas.bind_all("<MouseWheel>", _on_wheel)
        canvas.bind_all("<Button-4>", _on_wheel_linux_up)
        canvas.bind_all("<Button-5>", _on_wheel_linux_down)

    def _on_leave(event):
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    canvas.bind("<Enter>", _on_enter, add="+")
    canvas.bind("<Leave>", _on_leave, add="+")


# ==============================================================
#  Цветовые хелперы
# ==============================================================
def _blend_hex(c1, c2, alpha):
    """Смешивает c1 (foreground) и c2 (background) с весом alpha 0..1."""
    alpha = max(0.0, min(1.0, float(alpha)))

    def to_rgb(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    r1, g1, b1 = to_rgb(c1)
    r2, g2, b2 = to_rgb(c2)
    r = int(r1 * alpha + r2 * (1 - alpha))
    g = int(g1 * alpha + g2 * (1 - alpha))
    b = int(b1 * alpha + b2 * (1 - alpha))
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ==============================================================
#  Анимированный неоновый статус-бар
# ==============================================================
class _Particle:
    """Маленькая частица, дрейфующая по бару."""
    __slots__ = ("x", "y", "vx", "vy", "size", "alpha", "life")

    def __init__(self, w, h):
        self.x = random.uniform(0, w)
        self.y = random.uniform(h * 0.2, h * 0.8)
        self.vx = random.uniform(0.4, 1.6)
        self.vy = random.uniform(-0.15, 0.15)
        self.size = random.uniform(1.0, 2.2)
        self.alpha = random.uniform(0.25, 0.7)
        self.life = random.uniform(0.3, 1.0)

    def step(self, w, h):
        self.x += self.vx
        self.y += self.vy
        self.life -= 0.012
        if self.x > w + 4 or self.life <= 0:
            self.x = -4
            self.y = random.uniform(h * 0.2, h * 0.8)
            self.vx = random.uniform(0.4, 1.6)
            self.vy = random.uniform(-0.15, 0.15)
            self.size = random.uniform(1.0, 2.2)
            self.alpha = random.uniform(0.25, 0.7)
            self.life = random.uniform(0.3, 1.0)


class _PulseRing:
    """Расширяющееся кольцо от индикатора."""
    __slots__ = ("r", "max_r", "alpha", "color")

    def __init__(self, color, max_r=22):
        self.r = 6.0
        self.max_r = max_r
        self.alpha = 0.9
        self.color = color

    def step(self):
        self.r += 1.4
        self.alpha -= 0.045

    @property
    def dead(self):
        return self.alpha <= 0 or self.r >= self.max_r


class AnimatedStatusBar(tk.Canvas):
    """Неоновый статус-бар с частицами, пульсовыми кольцами,
    бегущей волной и ripple-эффектами при смене состояния."""

    _STATE_COLORS = {
        "ready":   ("success", "#4ade80"),
        "busy":    ("accent",  "#7c7cff"),
        "error":   ("danger",  "#f87171"),
        "success": ("success", "#4ade80"),
    }

    def __init__(self, master, palette, height=34, **kwargs):
        super().__init__(
            master, height=height, bg=palette["bg"],
            highlightthickness=0, **kwargs,
        )
        self.palette = palette
        self.height = height
        self._width = 800

        self._text = "Готово"
        self._state = "ready"
        self._prev_state = "ready"
        self._progress = None
        self._pre_progress_state = "ready"
        self._metrics = []

        # анимационные счётчики
        self._phase = 0.0
        self._wave_pos = 0.0
        self._ripple = 0.0          # 0..1 — расширяющийся ripple при смене state

        # частицы и кольца
        self._particles = [_Particle(self._width, self.height) for _ in range(14)]
        self._rings = []

        self._job = None
        self._running = True
        self._error_count = 0

        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)

        self._schedule_tick()

    # ---------------- API ----------------
    def set_status(self, text, state="ready"):
        if state != self._state:
            self._prev_state = self._state
            self._ripple = 1.0
            # пусковой ripple: большое кольцо в цвете нового состояния
            color_key, _ = self._STATE_COLORS.get(state, ("accent", "#7c7cff"))
            color = self.palette.get(color_key, self.palette["accent"])
            self._rings.append(_PulseRing(color, max_r=self.height))

        self._text = text
        self._state = state

    def set_progress(self, value):
        """Авто-режим busy: появление прогресса включает busy,
        исчезновение — возвращает предыдущее состояние."""
        was_none = self._progress is None
        will_be_none = value is None

        if not was_none and will_be_none:
            # прогресс завершился — возвращаемся к прежнему состоянию
            prev = self._pre_progress_state
            if prev != self._state:
                self._prev_state = self._state
                self._ripple = 1.0
                color_key, _ = self._STATE_COLORS.get(prev, ("accent", "#7c7cff"))
                color = self.palette.get(color_key, self.palette["accent"])
                self._rings.append(_PulseRing(color, max_r=self.height))
            self._state = prev
            self._progress = None
        elif was_none and not will_be_none:
            # прогресс появился — уходим в busy
            if self._state != "busy":
                self._pre_progress_state = self._state
                self._prev_state = self._state
                self._ripple = 1.0
                color = self.palette.get("accent", "#7c7cff")
                self._rings.append(_PulseRing(color, max_r=self.height))
            self._state = "busy"
            self._progress = value
        else:
            self._progress = value

    def set_metrics(self, metrics):
        self._metrics = list(metrics)

    def stop(self):
        self._running = False
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    # ---------------- цикл ----------------
    def _schedule_tick(self):
        if not self._running:
            return
        try:
            self._job = self.after(50, self._tick)
        except Exception:
            self._job = None

    def _tick(self):
        self._job = None
        if not self._running:
            return

        try:
            if not self.winfo_exists():
                self.stop()
                return

            self._phase = (self._phase + 0.035) % 1.0
            if self._state == "busy":
                self._wave_pos = (self._wave_pos + 0.018) % 1.0

            # ripple затухает
            if self._ripple > 0:
                self._ripple = max(0.0, self._ripple - 0.05)

            # частицы двигаются
            for pt in self._particles:
                pt.step(self._width, self.height)

            # кольца расширяются
            for ring in self._rings:
                ring.step()
            self._rings = [r for r in self._rings if not r.dead]

            self._redraw()
            self._error_count = 0

        except tk.TclError:
            self.stop()
            return
        except Exception as e:
            self._error_count += 1
            if self._error_count <= 3:
                print(f"[statusbar] tick error: {e}")
            if self._error_count > 100:
                self.stop()
                return

        self._schedule_tick()

    def _on_destroy(self, event):
        if event.widget is self:
            self.stop()

    def _on_resize(self, e):
        self._width = e.width
        # перераспределяем частицы под новую ширину
        for pt in self._particles:
            if pt.x > self._width:
                pt.x = random.uniform(0, self._width)

    # ---------------- отрисовка ----------------
    def _redraw(self):
        self.delete("all")
        p = self.palette
        w, h = self._width, self.height
        cy = h / 2
        if w <= 0 or h <= 0:
            return

        # основной цвет состояния
        color_key, _ = self._STATE_COLORS.get(self._state, ("accent", "#7c7cff"))
        state_color = p.get(color_key, p["accent"])

        # ---------- фон ----------
        self.create_rectangle(0, 0, w, h, fill=p["bg"], outline="")

        # ---------- ripple на весь бар ----------
        if self._ripple > 0:
            ripple_alpha = self._ripple * 0.12
            # горизонтальная полоса-градиент от левого края
            steps = 32
            for i in range(steps):
                t = i / (steps - 1)
                # затухает к правому краю
                a = ripple_alpha * (1 - t) * self._ripple
                if a <= 0.005:
                    continue
                x1 = int(t * w)
                x2 = int((t + 1/steps) * w) + 1
                mixed = _blend_hex(state_color, p["bg"], a)
                self.create_rectangle(x1, 0, x2, h,
                                      fill=mixed, outline=mixed)

        # ---------- плавающие частицы ----------
        for pt in self._particles:
            if pt.x < -2 or pt.x > w + 2:
                continue
            alpha = pt.alpha * min(1.0, pt.life * 2)
            if alpha <= 0.02:
                continue
            color = _blend_hex(state_color, p["bg"], alpha * 0.85)
            r = pt.size
            self.create_oval(pt.x - r, pt.y - r, pt.x + r, pt.y + r,
                             fill=color, outline="")

        # ---------- бегущая неоновая волна при busy ----------
        if self._state == "busy":
            marker_w = max(110, w // 5)
            marker_x = int(self._wave_pos * (w + marker_w)) - marker_w

            # три слоя: яркое ядро, средний ореол, мягкий хвост
            for layer, (mult, height_px, width_px) in enumerate([
                (1.0, 2, 1.0),
                (0.5, 4, 1.4),
                (0.25, 6, 2.0),
            ]):
                segments = 32
                for i in range(segments):
                    t = i / (segments - 1)
                    fall = 1 - abs(t - 0.5) * 2
                    alpha = max(0.0, min(1.0, fall * fall * 0.7 * mult))
                    if alpha <= 0.02:
                        continue
                    seg_w = marker_w / segments
                    x1 = marker_x + i * seg_w
                    x2 = x1 + seg_w + 1
                    if x2 < 0 or x1 > w:
                        continue
                    mixed = _blend_hex(p["accent"], p["bg"], alpha)
                    self.create_rectangle(x1, 0, x2, height_px,
                                          fill=mixed, outline=mixed)

            # яркая белая точка-голова волны
            head_x = marker_x + marker_w * 0.5
            if 0 <= head_x <= w:
                glow_r = 8
                for gr in range(glow_r, 0, -2):
                    a = 0.08 + 0.06 * (glow_r - gr) / glow_r
                    g_col = _blend_hex("#ffffff", p["bg"], a)
                    self.create_oval(head_x - gr, cy - gr,
                                     head_x + gr, cy + gr,
                                     fill=g_col, outline="")
                self.create_oval(head_x - 2, cy - 2, head_x + 2, cy + 2,
                                 fill="#ffffff", outline="")

        # ---------- пульсовые кольца от индикатора ----------
        for ring in self._rings:
            color = _blend_hex(ring.color, p["bg"], ring.alpha)
            self.create_oval(20 - ring.r, cy - ring.r,
                             20 + ring.r, cy + ring.r,
                             outline=color, width=1)

        # ---------- индикатор слева ----------
        if self._state == "ready":
            pulse = 4 + abs(math.sin(self._phase * math.pi)) * 1.0
        elif self._state == "busy":
            pulse = 4 + abs(math.sin(self._phase * math.pi)) * 2.2
        elif self._state == "error":
            pulse = 5 + abs(math.sin(self._phase * math.pi * 2)) * 1.5
        else:  # success
            pulse = 6

        # многослойное свечение
        for layer, alpha in [(2.4, 0.10), (1.8, 0.18), (1.3, 0.30)]:
            glow = _blend_hex(state_color, p["bg"], alpha)
            r = pulse * layer
            self.create_oval(20 - r, cy - r, 20 + r, cy + r,
                             fill=glow, outline="")
        # ядро
        self.create_oval(20 - pulse, cy - pulse,
                         20 + pulse, cy + pulse,
                         fill=state_color, outline="")
        # точечный блик
        self.create_oval(20 - pulse * 0.35, cy - pulse * 0.35,
                         20 + pulse * 0.35, cy + pulse * 0.35,
                         fill=_blend_hex("#ffffff", state_color, 0.6),
                         outline="")

        # ---------- текст ----------
        text_x = 40
        self.create_text(
            text_x, cy, text=self._text, anchor="w",
            fill=p["text"], font=("Segoe UI", 9),
        )

        # ---------- прогресс с неоновым свечением ----------
        if self._progress is not None and self._progress > 0:
            approx_text_w = len(self._text) * 7 + 40
            bar_left = text_x + approx_text_w
            bar_right = w - 12

            if self._metrics:
                metrics_w = sum(
                    max(70, len(str(v)) * 7 + len(str(k)) * 6 + 30)
                    for k, v in self._metrics
                )
                bar_right -= metrics_w

            if bar_right - bar_left > 60:
                bar_h = 4
                bar_y = cy - bar_h / 2
                fill_w = int((bar_right - bar_left) * self._progress)

                # фон трека
                rounded_rect(self, bar_left, bar_y,
                             bar_right, bar_y + bar_h, radius=2,
                             fill=p["surface_hi"], outline="")

                # ореол вокруг прогресса
                if fill_w > 0:
                    glow_color = _blend_hex(p["accent"], p["bg"], 0.3)
                    rounded_rect(self, bar_left, bar_y - 3,
                                 bar_left + fill_w, bar_y + bar_h + 3,
                                 radius=3,
                                 fill="", outline=glow_color, width=2)

                    # основной прогресс
                    rounded_rect(self, bar_left, bar_y,
                                 bar_left + fill_w, bar_y + bar_h,
                                 radius=2,
                                 fill=p["accent"], outline="")

                    # блик на прогрессе
                    if fill_w > 4:
                        rounded_rect(self, bar_left + 1, bar_y + 1,
                                     bar_left + fill_w - 1, bar_y + 2,
                                     radius=1,
                                     fill=_blend_hex("#ffffff", p["accent"], 0.4),
                                     outline="")

                    # яркая точка на острие
                    tip_x = bar_left + fill_w
                    self.create_oval(tip_x - 3, cy - 3,
                                     tip_x + 3, cy + 3,
                                     fill="#ffffff", outline="")

        # ---------- метрики справа ----------
        if self._metrics:
            x = w - 16
            for label, value in reversed(self._metrics):
                self.create_text(
                    x, cy, text=str(value), anchor="e",
                    fill=p["text"], font=("Segoe UI", 9, "bold"),
                )
                value_w = max(20, len(str(value)) * 7 + 4)
                self.create_text(
                    x - value_w - 4, cy, text=label, anchor="e",
                    fill=p["text_faint"], font=("Segoe UI", 8),
                )
                label_w = len(label) * 6 + 8
                x -= (value_w + label_w + 22)