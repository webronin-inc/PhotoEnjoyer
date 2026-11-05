"""Мелкие визуальные эффекты, общие для окон."""
import tkinter as tk

from . import anim


def dialog_in(top, dy=14, duration=240):
    """Плавное появление окна: прозрачность 0→1 и лёгкий подъём снизу.

    Размер окна НЕ трогаем никогда — анимируется только положение (геометрия
    вида «+x+y») и прозрачность. Раньше здесь пересобиралась строка «ШxВ+x+y»
    из ещё не построенного окна (1x1), и диалоги схлопывались в точку.
    Если окно ещё не показано, делаем только прозрачность."""
    def finish():
        try:
            top.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    if not anim.is_enabled():
        finish()
        return
    try:
        top.update_idletasks()
        x, y = top.winfo_x(), top.winfo_y()
        slide = bool(top.winfo_ismapped()) and top.winfo_width() > 50
    except tk.TclError:
        return
    try:
        top.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def upd(t):
        try:
            top.attributes("-alpha", t)
            if slide:
                top.geometry(f"+{x}+{int(y + dy * (1 - t))}")
        except tk.TclError:
            pass

    def done():
        upd(1.0)
        finish()

    anim.get(top).animate(duration, upd, easing=anim.ease_out_cubic, on_done=done,
                          key=(id(top), "dialog_in"))
    # страховка: что бы ни случилось, окно не должно остаться невидимым
    top.after(int(duration) + 1500, finish)


def _pady_of(w):
    """Исходный вертикальный отступ pack-виджета как (верх, низ)."""
    try:
        v = w.pack_info().get("pady", 0)
    except tk.TclError:
        return (0, 0)
    if isinstance(v, (tuple, list)):
        parts = [int(x) for x in v]
    elif isinstance(v, str):
        parts = [int(float(x)) for x in v.split()] or [0]
    else:
        parts = [int(v)]
    return (parts[0], parts[1] if len(parts) > 1 else parts[0])


def stagger_rise(widgets, dy=28, step=90, duration=520):
    """Каскадное появление: блоки по очереди «выезжают» снизу вверх.

    Работает для виджетов, размещённых через pack (меняется только верхний
    отступ; исходные отступы возвращаются в конце)."""
    if not anim.effects_enabled():
        return
    for i, w in enumerate(widgets):
        top0, bottom0 = _pady_of(w)
        try:
            w.pack_configure(pady=(top0 + dy, bottom0))
        except tk.TclError:
            continue

        def upd(t, w=w, top0=top0, bottom0=bottom0):
            try:
                w.pack_configure(pady=(top0 + int(round(dy * (1 - t))), bottom0))
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
        top.after(3000, lambda: _unhide(top))      # на случай сбоя анимации
    return top


def _unhide(top):
    try:
        if top.winfo_exists():
            top.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
