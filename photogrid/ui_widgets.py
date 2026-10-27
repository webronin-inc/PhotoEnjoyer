"""Кастомные виджеты. Иконки — Segoe MDL2 Assets (Windows 10/11)."""
import tkinter as tk
import math
import random

from . import anim, icons


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
#  Цветовые хелперы (перенесены наверх — используются везде)
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
#  Иконки (собственный векторный набор, см. icons.py)
# ==============================================================
def draw_icon(canvas, kind, cx, cy, size=20, color="#ffffff"):
    """Рисует иконку по центру (cx, cy); не зависит от системных шрифтов."""
    return icons.draw(canvas, kind, cx, cy, size=size, color=color)


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
        # плавное появление (если оконный менеджер поддерживает прозрачность)
        try:
            tip.attributes("-alpha", 0.0)
            anim.get(tip).animate(
                140, lambda t, w=tip: w.attributes("-alpha", t),
                key=("tip", id(self)))
        except Exception:
            pass

    def _hide(self):
        if self._tip is not None:
            try:
                anim.get(self.widget).cancel(("tip", id(self)))
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
#  Кнопка раздела в рельсе (с анимацией пульсации)
# ==============================================================
class RailButton(tk.Canvas):
    """Кнопка раздела в рельсе.

    Наведение и активное состояние плавно анимируются. Если pulse=True —
    у активной кнопки пульсирует ореол (значок обновления); таймер пульсации
    работает ТОЛЬКО пока кнопка активна и видна на экране.
    """

    def __init__(self, master, palette, kind, size=42,
                 command=None, tooltip=None, pulse=False, **kwargs):
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
        self._hv = 0.0          # 0..1 — «насколько наведена»
        self._av = 0.0          # 0..1 — «насколько активна»

        self._pulse_allowed = bool(pulse)
        self._pulse_phase = 0.0
        self._pulse_job = None

        self.bind("<Button-1>", lambda e: command() if command else None)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Destroy>", self._on_destroy)

        self._redraw()
        self._tooltip = Tooltip(self, tooltip, palette) if tooltip else None

    # ---------- tooltip ----------
    def set_tooltip(self, text):
        if self._tooltip is None:
            self._tooltip = Tooltip(self, text, self.palette)
        else:
            self._tooltip.text = text

    # ---------- состояние ----------
    def set_active(self, active):
        active = bool(active)
        changed = active != self._active
        self._active = active
        if changed:
            anim.tween_attr(self, "_av", 1.0 if active else 0.0,
                            duration=260, easing=anim.ease_out_back
                            if active else anim.ease_out_cubic)
        else:
            self._redraw()
        if active and self._pulse_allowed:
            self._start_pulse()
        else:
            self._stop_pulse()

    def _set_hover(self, h):
        self._hover = h
        anim.tween_attr(self, "_hv", 1.0 if h else 0.0, duration=140)

    # ---------- пульсация ----------
    def _start_pulse(self):
        if self._pulse_job is None:
            try:
                self._pulse_job = self.after(60, self._pulse_tick)
            except Exception:
                self._pulse_job = None

    def _stop_pulse(self):
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None

    def _pulse_tick(self):
        self._pulse_job = None
        if not (self._pulse_allowed and self._active):
            return
        try:
            if not self.winfo_exists():
                return
            if not self.winfo_ismapped():
                # скрыта (pack_forget) — не жжём CPU; set_active(True)
                # при следующем показе запустит пульсацию снова
                return
            self._pulse_phase = (self._pulse_phase + 0.04) % 1.0
            self._redraw()
        except tk.TclError:
            return
        except Exception:
            pass
        self._start_pulse()

    def _on_destroy(self, event):
        if event.widget is self:
            self._pulse_allowed = False
            self._stop_pulse()
            try:
                anim.get(self).cancel((id(self), "_hv"))
                anim.get(self).cancel((id(self), "_av"))
            except Exception:
                pass

    # ---------- отрисовка ----------
    def _redraw(self):
        self.delete("all")
        p = self.palette
        s = self.size
        cx = s / 2
        hv = max(0.0, min(1.0, self._hv))
        av = max(0.0, min(1.5, self._av))
        av1 = min(1.0, av)

        if self._pulse_allowed and self._active:
            pulse = 0.5 - 0.5 * math.cos(2 * math.pi * self._pulse_phase)
            for pad, base_alpha in ((3, 0.35), (1, 0.55), (-1, 0.75)):
                a = base_alpha * (0.4 + pulse * 0.6) * av1
                col = _blend_hex(p["accent"], p["bg"], a)
                rounded_rect(self, pad, pad, s - pad, s - pad,
                             radius=11, fill="", outline=col, width=2)

        glow = max(hv, av1)
        if glow > 0.01:
            fill = _blend_hex(p["surface_alt"], p["bg"], glow)
            rounded_rect(self, 4, 4, s - 4, s - 4, radius=11,
                         fill=fill, outline="")

        if av1 > 0.01:
            # акцентная полоска у левого края (раньше рисовалась за границей
            # холста и была невидима); «выезжает» по высоте
            half = s * 0.22 * av
            rounded_rect(self, 0, cx - half, 3, cx + half, radius=1,
                         fill=p["accent"], outline="")

        color = _blend_hex(p["accent_hi"], p["text_dim"], av1) if av1 > hv \
            else _blend_hex(p["text"], p["text_dim"], hv)
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
        self._hv = 0.0
        self._pressed = False

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
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Configure>", lambda e: self._redraw())
        self._redraw()

    def _invoke(self):
        if self._command:
            self._command()

    def _on_press(self, e):
        self._pressed = True
        self._redraw()

    def _on_release(self, e):
        was = self._pressed
        self._pressed = False
        self._redraw()
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if was and inside:
            self._invoke()

    def _set_hover(self, h):
        self._hover = h
        if not h:
            self._pressed = False
        anim.tween_attr(self, "_hv", 1.0 if h else 0.0, duration=160)

    def _redraw(self):
        self.delete("all")
        # при pack(fill=X) холст шире заданной ширины — рисуем по реальной
        w = max(int(self["width"]), self.winfo_width())
        h = int(self["height"])
        p = self.palette

        color = _blend_hex(p["accent_hi"], p["accent"], self._hv)
        inset = 1 if self._pressed else 0       # лёгкое «нажатие»
        rounded_rect(self, inset, inset, w - inset, h - inset, radius=12,
                     fill=color, outline="")

        cx = 18
        cy = h / 2 + inset
        if self.icon:
            draw_icon(self, self.icon, cx + 9, cy, size=18, color="#ffffff")
            cx += 30
        self.create_text(cx, cy, text=self.text, fill="#ffffff",
                         font=("Segoe UI", 10, "bold"), anchor="w")


# ==============================================================
#  Глобальные привязки колеса мыши (безопасные)
# ==============================================================
# bind_all хранит Tcl-команду виджета-владельца. Если владельца уничтожили,
# пока курсор над ним (<Leave> не приходит), привязка остаётся, а команда
# удалена → «invalid command name ...» на каждый поворот колеса.
# Поэтому помним владельца и снимаем привязку при <Destroy>.
_WHEEL_SEQS = ("<MouseWheel>", "<Button-4>", "<Button-5>")
_wheel_owner = {}


def _wheel_claim(owner, handlers):
    for seq, fn in handlers.items():
        owner.bind_all(seq, fn)
        _wheel_owner[seq] = owner


def _wheel_release(owner):
    for seq in _WHEEL_SEQS:
        if _wheel_owner.get(seq) is owner:
            _wheel_owner.pop(seq, None)
            try:
                owner.unbind_all(seq)
            except Exception:
                pass


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
        self._hv = 0.0
        self.on_press = None      # необязательные хуки жеста: перед первым
        self.on_release = None    # изменением и после отпускания кнопки

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
        # слайдер уничтожили под курсором (<Leave> не придёт) — снять bind_all
        self.bind("<Destroy>", lambda e: _wheel_release(self)
                  if e.widget is self else None, add="+")

        self.bind("<Left>",  lambda e: self._nudge(-1))
        self.bind("<Right>", lambda e: self._nudge(+1))
        self.bind("<Home>",  lambda e: self._set(self.from_))
        self.bind("<End>",   lambda e: self._set(self.to))

        try:
            self.configure(takefocus=1)
        except Exception:
            pass

    def set(self, v, notify=True):
        self._set(v, notify=notify)

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
        anim.tween_attr(self, "_hv", 1.0, duration=130)
        _wheel_claim(self, {
            "<MouseWheel>": self._on_wheel_global,
            "<Button-4>": lambda e: self._nudge(+1),
            "<Button-5>": lambda e: self._nudge(-1),
        })

    def _on_leave(self, event):
        if self._drag:
            return
        self._hover = False
        anim.tween_attr(self, "_hv", 0.0, duration=130)
        _wheel_release(self)

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
        if self.on_press:
            self.on_press()
        try:
            self.focus_set()
        except Exception:
            pass
        self._update_from_x(e.x)

    def _on_drag(self, e):
        self._update_from_x(e.x)

    def _on_release(self, e):
        self._drag = False
        if self.on_release:
            self.on_release()

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

        r = 8 + self._hv + (1 if self._drag else 0)
        cx = progress_x
        self.create_oval(cx - r, y - r + 1, cx + r, y + r + 1,
                         fill=p["shadow"], outline="")
        border_color = _blend_hex(p["accent_hi"], p["accent"], self._hv)
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
        self._hv = 0.0

        self.bind("<Button-1>", lambda e: command() if command else None)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

        if tooltip:
            Tooltip(self, tooltip, palette)

    def _set_hover(self, h):
        self._hover = h
        anim.tween_attr(self, "_hv", 1.0 if h else 0.0, duration=140)

    def _redraw(self):
        self.delete("all")
        p = self.palette
        s = self.size

        if self._hv > 0.01:
            rounded_rect(self, 3, 3, s - 3, s - 3, radius=9,
                         fill=_blend_hex(p["surface_alt"], p["bg"], self._hv),
                         outline="")

        color = _blend_hex(p["text"], p["text_dim"], self._hv)
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
        self.marked = False        # отмечен для массового удаления
        self.thumb = None
        self._hv = 0.0             # плавное наведение 0..1
        self._flash = 0.0          # вспышка при появлении фото 1→0
        self._reveal = 1.0         # проявление миниатюры 0→1

        self.bind("<Button-1>", on_click)
        self.bind("<Button-3>", on_right_click)
        self.bind("<Double-Button-1>", on_double_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._redraw()

    def _on_enter(self, _):
        self.hover = True
        anim.tween_attr(self, "_hv", 1.0, duration=140)

    def _on_leave(self, _):
        self.hover = False
        anim.tween_attr(self, "_hv", 0.0, duration=180)

    def set_thumb(self, photo_image, animate=False):
        had = self.state == "filled"
        self.thumb = photo_image
        self.state = "filled" if photo_image else "empty"
        if photo_image is not None and animate and not had:
            self.play_reveal()
        else:
            self._redraw()

    def play_reveal(self):
        """Миниатюра проявляется, по рамке пробегает вспышка акцентного цвета."""
        self._reveal = 0.0
        self._flash = 1.0
        a = anim.get(self)
        a.animate(320, self._set_reveal, key=(id(self), "reveal"),
                  easing=anim.ease_out_cubic)
        a.animate(520, self._set_flash, key=(id(self), "flash"),
                  easing=anim.linear)

    def _set_reveal(self, t):
        self._reveal = t
        self._redraw()

    def _set_flash(self, t):
        self._flash = 1.0 - t
        self._redraw()

    def update_border(self, selected=False):
        self.selected = selected
        self._redraw()

    def set_marked(self, marked):
        marked = bool(marked)
        if marked != self.marked:
            self.marked = marked
            self._redraw()

    def _redraw(self):
        self.delete("all")
        p = self.palette
        w, h = self.W, self.H
        r = self.RADIUS
        hv = max(0.0, min(1.0, self._hv))

        if self.selected:
            bc, bw, bg = p["accent"], 2, p["accent_soft"]
        elif self.marked:
            bc, bw = p["danger"], 2
            bg = _blend_hex(p["danger"], p["slot_bg"], 0.10)
        else:
            bc = _blend_hex(p["accent_hi"], p["slot_border"], hv)
            bw = 1
            bg = _blend_hex(p["surface_hi"], p["slot_bg"], hv)

        if self._flash > 0.01 and not self.selected and not self.marked:
            bc = _blend_hex(p["accent_hi"], bc, self._flash)
            bw = 2

        rounded_rect(self, 1, 1, w - 1, h - 1, radius=r,
                     fill=bg, outline=bc, width=bw)

        if self.state == "filled" and self.thumb:
            self.create_image(w / 2, h / 2, image=self.thumb, anchor="center")
            if self._reveal < 0.999:
                # fade-in: «завеса» цвета слота с убывающей штриховкой
                stip = ("gray75" if self._reveal < 0.25 else
                        "gray50" if self._reveal < 0.55 else
                        "gray25" if self._reveal < 0.85 else "gray12")
                self.create_rectangle(3, 3, w - 3, h - 3, fill=bg,
                                      outline="", stipple=stip)
        else:
            cx, cy = w / 2, h / 2
            color = _blend_hex(p["accent"], p["text_faint"], hv)
            lift = 3 * hv                               # плюс «подпрыгивает»
            draw_icon(self, "plus", cx, cy - 22 - lift, size=26, color=color)
            tc = _blend_hex(p["text"], p["text_dim"], hv)
            self.create_text(cx, cy + 30, text=f"Фото {self.index + 1}",
                             fill=tc, font=("Segoe UI", 10))

        if self.marked:
            # галочка-бейдж в правом верхнем углу
            bx, by, br = w - 20, 20, 11
            self.create_oval(bx - br, by - br, bx + br, by + br,
                             fill=p["danger"], outline="")
            self.create_line(bx - 5, by, bx - 1, by + 4, bx + 5, by - 4,
                             fill="#ffffff", width=2, capstyle="round",
                             joinstyle="round")


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
        self._hv = 0.0

        self.bind("<Button-1>", lambda e: command() if command else None)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

    def set_color(self, color):
        self.color = color
        self._redraw()

    def _set_hover(self, h):
        self._hover = h
        anim.tween_attr(self, "_hv", 1.0 if h else 0.0, duration=140)

    def _redraw(self):
        self.delete("all")
        p = self.palette
        s = self.size
        border = _blend_hex(p["accent"], p["border"], self._hv)
        bw = 2 if self._hv > 0.5 else 1
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
        _wheel_claim(canvas, {
            "<MouseWheel>": _on_wheel,
            "<Button-4>": _on_wheel_linux_up,
            "<Button-5>": _on_wheel_linux_down,
        })

    def _on_leave(event):
        _wheel_release(canvas)

    def _on_destroy(event):
        if event.widget is canvas:
            _wheel_release(canvas)

    canvas.bind("<Enter>", _on_enter, add="+")
    canvas.bind("<Leave>", _on_leave, add="+")
    canvas.bind("<Destroy>", _on_destroy, add="+")


# ==============================================================
#  Анимированный неоновый статус-бар
# ==============================================================
class _Particle:
    """Частица статус-бара.

    Раньше она возрождалась по истечении «жизни» (≈1–2 с) и успевала пролететь
    максимум ~100 px, поэтому все частицы кучковались у левого края. Теперь
    жизнь влияет только на мерцание, а возрождение — когда частица вылетела
    за правый край.
    """
    __slots__ = ("x", "y", "vx", "vy", "size", "alpha", "phase")

    def __init__(self, w, h, spread=True):
        self._respawn(w, h, spread)

    def _respawn(self, w, h, spread=False):
        self.x = random.uniform(0, w) if spread else -4.0
        self.y = random.uniform(h * 0.2, h * 0.8)
        self.vx = random.uniform(0.4, 1.6)
        self.vy = random.uniform(-0.12, 0.12)
        self.size = random.uniform(1.0, 2.2)
        self.alpha = random.uniform(0.3, 0.7)
        self.phase = random.random()

    def step(self, w, h, dt=1.0):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.phase = (self.phase + 0.02 * dt) % 1.0
        if self.y < h * 0.15 or self.y > h * 0.85:
            self.vy = -self.vy
        if self.x > w + 4:
            self._respawn(w, h)

    @property
    def twinkle(self):
        return 0.6 + 0.4 * math.sin(self.phase * 2 * math.pi)


class _PulseRing:
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

        self._phase = 0.0
        self._wave_pos = 0.0
        self._ripple = 0.0

        self._particles = [_Particle(self._width, self.height) for _ in range(14)]
        self._rings = []

        self._job = None
        self._running = True
        self._error_count = 0

        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)

        self._schedule_tick()

    def set_status(self, text, state="ready"):
        if state != self._state:
            self._prev_state = self._state
            self._ripple = 1.0
            color_key, _ = self._STATE_COLORS.get(state, ("accent", "#7c7cff"))
            color = self.palette.get(color_key, self.palette["accent"])
            self._rings.append(_PulseRing(color, max_r=self.height))

        self._text = text
        self._state = state

    def set_progress(self, value):
        was_none = self._progress is None
        will_be_none = value is None

        if not was_none and will_be_none:
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

            if not self.winfo_ismapped():
                # окно свёрнуто/раздел скрыт — анимацию не считаем
                self._schedule_tick()
                return

            self._phase = (self._phase + 0.035) % 1.0
            if self._state == "busy":
                self._wave_pos = (self._wave_pos + 0.018) % 1.0

            if self._ripple > 0:
                self._ripple = max(0.0, self._ripple - 0.05)

            for pt in self._particles:
                pt.step(self._width, self.height)

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
        for pt in self._particles:
            if pt.x > self._width:
                pt.x = random.uniform(0, self._width)

    def _redraw(self):
        self.delete("all")
        p = self.palette
        w, h = self._width, self.height
        cy = h / 2
        if w <= 0 or h <= 0:
            return

        color_key, _ = self._STATE_COLORS.get(self._state, ("accent", "#7c7cff"))
        state_color = p.get(color_key, p["accent"])

        self.create_rectangle(0, 0, w, h, fill=p["bg"], outline="")

        if self._ripple > 0:
            ripple_alpha = self._ripple * 0.12
            steps = 32
            for i in range(steps):
                t = i / (steps - 1)
                a = ripple_alpha * (1 - t) * self._ripple
                if a <= 0.005:
                    continue
                x1 = int(t * w)
                x2 = int((t + 1/steps) * w) + 1
                mixed = _blend_hex(state_color, p["bg"], a)
                self.create_rectangle(x1, 0, x2, h,
                                      fill=mixed, outline=mixed)

        for pt in self._particles:
            if pt.x < -2 or pt.x > w + 2:
                continue
            alpha = pt.alpha * pt.twinkle
            if alpha <= 0.02:
                continue
            color = _blend_hex(state_color, p["bg"], alpha * 0.85)
            r = pt.size
            self.create_oval(pt.x - r, pt.y - r, pt.x + r, pt.y + r,
                             fill=color, outline="")

        if self._state == "busy":
            marker_w = max(110, w // 5)
            marker_x = int(self._wave_pos * (w + marker_w)) - marker_w

            for mult, height_px, _ in [(1.0, 2, 1.0), (0.5, 4, 1.4), (0.25, 6, 2.0)]:
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

        for ring in self._rings:
            color = _blend_hex(ring.color, p["bg"], ring.alpha)
            self.create_oval(20 - ring.r, cy - ring.r,
                             20 + ring.r, cy + ring.r,
                             outline=color, width=1)

        if self._state == "ready":
            pulse = 4 + abs(math.sin(self._phase * math.pi)) * 1.0
        elif self._state == "busy":
            pulse = 4 + abs(math.sin(self._phase * math.pi)) * 2.2
        elif self._state == "error":
            pulse = 5 + abs(math.sin(self._phase * math.pi * 2)) * 1.5
        else:
            pulse = 6

        for layer, alpha in [(2.4, 0.10), (1.8, 0.18), (1.3, 0.30)]:
            glow = _blend_hex(state_color, p["bg"], alpha)
            r = pulse * layer
            self.create_oval(20 - r, cy - r, 20 + r, cy + r,
                             fill=glow, outline="")
        self.create_oval(20 - pulse, cy - pulse,
                         20 + pulse, cy + pulse,
                         fill=state_color, outline="")
        self.create_oval(20 - pulse * 0.35, cy - pulse * 0.35,
                         20 + pulse * 0.35, cy + pulse * 0.35,
                         fill=_blend_hex("#ffffff", state_color, 0.6),
                         outline="")

        text_x = 40
        self.create_text(
            text_x, cy, text=self._text, anchor="w",
            fill=p["text"], font=("Segoe UI", 9),
        )

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

                rounded_rect(self, bar_left, bar_y,
                             bar_right, bar_y + bar_h, radius=2,
                             fill=p["surface_hi"], outline="")

                if fill_w > 0:
                    glow_color = _blend_hex(p["accent"], p["bg"], 0.3)
                    rounded_rect(self, bar_left, bar_y - 3,
                                 bar_left + fill_w, bar_y + bar_h + 3,
                                 radius=3, fill="", outline=glow_color, width=2)

                    rounded_rect(self, bar_left, bar_y,
                                 bar_left + fill_w, bar_y + bar_h,
                                 radius=2, fill=p["accent"], outline="")

                    if fill_w > 4:
                        rounded_rect(self, bar_left + 1, bar_y + 1,
                                     bar_left + fill_w - 1, bar_y + 2,
                                     radius=1,
                                     fill=_blend_hex("#ffffff", p["accent"], 0.4),
                                     outline="")

                    tip_x = bar_left + fill_w
                    self.create_oval(tip_x - 3, cy - 3, tip_x + 3, cy + 3,
                                     fill="#ffffff", outline="")

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

# ==============================================================
#  SegmentedControl — переключатель «один из N» (вместо радиокнопок)
# ==============================================================
class SegmentedControl(tk.Frame):
    """Сегментированный переключатель.

    options — список (значение, подпись) или (значение, подпись, иконка).
    Можно связать с tk.StringVar (variable) — тогда он синхронизируется в
    обе стороны, в том числе при изменении переменной снаружи.
    """

    def __init__(self, master, palette, options, value=None, variable=None,
                 command=None, font_size=9, padx=12, pady=5, icon_size=15,
                 **kwargs):
        p = palette
        super().__init__(master, bg=p["surface_alt"], padx=2, pady=2, **kwargs)
        self.p = p
        self.command = command
        self.variable = variable
        self._opts = [tuple(o) + (None,) * (3 - len(o)) for o in options]
        self._font = ("Segoe UI", font_size)
        self._icon_size = icon_size
        self._value = None
        self._cells = {}
        self._hover = None
        self._trace_id = None

        for val, label, icon in self._opts:
            cell = tk.Label(self, text=label, font=self._font, cursor="hand2",
                            padx=padx, pady=pady, bd=0)
            if icon:
                cell.configure(compound="left")
            cell.pack(side=tk.LEFT, padx=(0, 2))
            cell.bind("<Button-1>", lambda e, v=val: self._choose(v))
            cell.bind("<Enter>", lambda e, v=val: self._set_hover(v))
            cell.bind("<Leave>", lambda e, v=val: self._set_hover(None))
            self._cells[val] = (cell, icon)

        if variable is not None:
            self._trace_id = variable.trace_add(
                "write", lambda *a: self._from_variable())
            self.bind("<Destroy>", self._on_destroy, add="+")
            self._from_variable()
        else:
            self.set(value if value is not None else self._opts[0][0])

    # ---- публичный API
    def get(self):
        return self._value

    def set(self, value, notify=False):
        if value not in self._cells:
            return
        self._value = value
        self._restyle()
        if notify and self.command:
            self.command(value)

    # ---- внутреннее
    def _choose(self, value):
        if value == self._value:
            return
        self.set(value)
        if self.variable is not None:
            self.variable.set(value)
        if self.command:
            self.command(value)

    def _from_variable(self):
        try:
            v = self.variable.get()
        except Exception:
            return
        if v in self._cells and v != self._value:
            self._value = v
            self._restyle()

    def _set_hover(self, value):
        self._hover = value
        self._restyle()

    def _restyle(self):
        p = self.p
        for val, (cell, icon) in self._cells.items():
            try:
                if val == self._value:
                    bg, fg = p["accent"], "#ffffff"
                elif val == self._hover:
                    bg, fg = p["surface_hi"], p["text"]
                else:
                    bg, fg = p["surface_alt"], p["text_dim"]
                cell.configure(bg=bg, fg=fg)
                if icon:
                    img = icons.tk_icon(icon, self._icon_size, fg)
                    cell.configure(image=img)
                    cell._img = img
            except tk.TclError:
                return

    def _on_destroy(self, event):
        if event.widget is self and self._trace_id is not None:
            try:
                self.variable.trace_remove("write", self._trace_id)
            except Exception:
                pass
            self._trace_id = None


# ==============================================================
#  ChipToggle — кнопка-«чип» с состоянием вкл/выкл (Ж, К, …)
# ==============================================================
class ChipToggle(tk.Label):
    def __init__(self, master, palette, text="", value=False, command=None,
                 font=("Segoe UI", 10, "bold"), width=3, **kwargs):
        super().__init__(master, text=text, font=font, width=width, pady=4,
                         cursor="hand2", bd=0, **kwargs)
        self.p = palette
        self.command = command
        self._on = bool(value)
        self._hv = False
        self.bind("<Button-1>", lambda e: self.toggle())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self._restyle()

    def get(self):
        return self._on

    def set(self, value):
        self._on = bool(value)
        self._restyle()

    def toggle(self):
        self._on = not self._on
        self._restyle()
        if self.command:
            self.command(self._on)

    def _hover(self, v):
        self._hv = v
        self._restyle()

    def _restyle(self):
        p = self.p
        if self._on:
            self.configure(bg=p["accent"], fg="#ffffff")
        elif self._hv:
            self.configure(bg=p["surface_hi"], fg=p["text"])
        else:
            self.configure(bg=p["surface_alt"], fg=p["text_dim"])


# ==============================================================
#  CaptionEntry — поле подписи под слотом (подсказка, подсветка фокуса)
# ==============================================================
class CaptionEntry(tk.Frame):
    def __init__(self, master, palette, textvariable, placeholder="Подпись…",
                 **kwargs):
        p = palette
        super().__init__(master, bg=p["slot_border"], padx=1, pady=1, **kwargs)
        self.p = p
        self.var = textvariable
        inner = tk.Frame(self, bg=p["surface_alt"])
        inner.pack(fill=tk.BOTH, expand=True)
        self.entry = tk.Entry(
            inner, textvariable=textvariable, bg=p["surface_alt"], fg=p["text"],
            insertbackground=p["accent_hi"], relief="flat", bd=0,
            highlightthickness=0, font=("Segoe UI", 9), justify="center",
            selectbackground=p["accent"], selectforeground="#ffffff", width=1)
        self.entry.pack(fill=tk.X, padx=8, pady=6)
        self._ph = tk.Label(inner, text=placeholder, bg=p["surface_alt"],
                            fg=p["text_faint"], font=("Segoe UI", 9),
                            cursor="xterm")
        self._ph.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        self.entry.bind("<Return>", self._next, add="+")
        self._trace_id = textvariable.trace_add(
            "write", lambda *a: self._sync_placeholder())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._sync_placeholder()

    def _sync_placeholder(self):
        try:
            empty = not self.var.get()
            if empty:
                self._ph.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self._ph.place_forget()
        except tk.TclError:
            pass

    def _focus(self, on):
        try:
            self.configure(bg=self.p["accent"] if on else self.p["slot_border"])
        except tk.TclError:
            pass

    def _next(self, event):
        try:
            nxt = self.entry.tk_focusNext()
            if nxt is not None:
                nxt.focus_set()
        except tk.TclError:
            pass
        return "break"

    def _on_destroy(self, event):
        if event.widget is self:
            try:
                self.var.trace_remove("write", self._trace_id)
            except Exception:
                pass
