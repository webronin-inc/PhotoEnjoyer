"""Мелкие визуальные эффекты, общие для окон."""
import tkinter as tk

from . import anim


def dialog_in(top, dy=14, duration=240):
    """Плавное появление окна: прозрачность 0→1 и лёгкий подъём снизу.

    Вызывать после того, как окно построено и ему задан geometry("+x+y").
    При отключённых анимациях окно просто показывается.
    """
    try:
        top.update_idletasks()
        geo = top.geometry()                       # "WxH+X+Y"
        size, _, rest = geo.partition("+")
        x, _, y = rest.partition("+")
        x, y = int(x), int(y)
    except Exception:
        x = y = None
    if not anim.is_enabled():
        return
    try:
        top.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def upd(t):
        try:
            top.attributes("-alpha", t)
            if x is not None:
                top.geometry(f"{size}+{x}+{int(y + dy * (1 - t))}")
        except tk.TclError:
            pass

    anim.get(top).animate(duration, upd, easing=anim.ease_out_cubic,
                          on_done=lambda: upd(1.0), key=(id(top), "dialog_in"))


def stagger_rise(widgets, dy=28, step=90, duration=520):
    """Каскадное появление: блоки по очереди «выезжают» снизу вверх.

    Работает для виджетов, размещённых через pack (меняет только верхний
    отступ), поэтому раскладка остальных не страдает.
    """
    if not anim.effects_enabled():
        return
    for i, w in enumerate(widgets):
        try:
            w.pack_configure(pady=(dy, 0))
        except tk.TclError:
            continue

        def upd(t, w=w):
            try:
                w.pack_configure(pady=(int(round(dy * (1 - t))), 0))
            except tk.TclError:
                pass

        anim.get(w).animate(duration, upd, delay_ms=i * step,
                            easing=anim.ease_out_cubic,
                            on_done=lambda w=w, u=upd: u(1.0),
                            key=(id(w), "rise"))


def toplevel(master, **kw):
    """tk.Toplevel, который плавно появляется, когда конструктор закончил
    строить окно (fade-in запускается в idle)."""
    top = tk.Toplevel(master, **kw)
    if anim.is_enabled():
        try:
            top.attributes("-alpha", 0.0)
        except tk.TclError:
            return top
        top.after_idle(lambda: dialog_in(top))
    return top
