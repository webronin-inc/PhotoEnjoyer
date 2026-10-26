"""Всплывающие уведомления («тосты») в правом нижнем углу окна.

Выезжают справа, складываются стопкой, сами исчезают; у тоста может быть
кнопка действия (например, «Вернуть» после массового удаления).
"""
import tkinter as tk

from . import anim

_KIND_COLOR = {
    "info": "accent",
    "success": "success",
    "error": "danger",
    "warn": "warning",
}


class _Toast:
    def __init__(self, frame, height):
        self.frame = frame
        self.height = height
        self.x_off = 60.0        # смещение вправо (выезд)
        self.y_off = 0.0         # смещение вверх от нижнего края
        self.job = None
        self.dead = False


class ToastManager:
    MAX = 4
    GAP = 8
    MARGIN_X = 18
    MARGIN_Y = 44            # над статус-баром

    def __init__(self, root, palette):
        self.root = root
        self.palette = palette
        self._toasts = []

    # ------------------------------------------------------------------ API
    def show(self, text, kind="info", action=None, duration=3800):
        """action = ("Вернуть", callback)."""
        p = self.palette
        accent = p.get(_KIND_COLOR.get(kind, "accent"), p["accent"])

        outer = tk.Frame(self.root, bg=accent, bd=0)
        inner = tk.Frame(outer, bg=p["surface"], bd=0)
        inner.pack(padx=(3, 1), pady=1)
        tk.Label(inner, text=text, bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10), justify="left", wraplength=320,
                 padx=14, pady=10).pack(side=tk.LEFT)

        toast_ref = []

        if action:
            label, cb = action

            def _run():
                try:
                    cb()
                finally:
                    if toast_ref:
                        self._dismiss(toast_ref[0])

            btn = tk.Label(inner, text=label, bg=p["surface"], fg=accent,
                           font=("Segoe UI", 10, "bold"), cursor="hand2",
                           padx=12, pady=10)
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda e: _run())
            btn.bind("<Enter>", lambda e: btn.config(fg=p["text"]))
            btn.bind("<Leave>", lambda e: btn.config(fg=accent))
        else:
            for w in (outer, inner):
                w.bind("<Button-1>", lambda e: self._dismiss(toast_ref[0]))

        outer.update_idletasks()
        t = _Toast(outer, outer.winfo_reqheight())
        toast_ref.append(t)
        self._toasts.append(t)

        # лишние старые убираем сразу
        while len(self._toasts) > self.MAX:
            self._dismiss(self._toasts[0], animate=False)

        self._layout(immediate_for=t)
        self._place(t)
        anim.get(self.root).animate(
            320, lambda v, tt=t: self._set_x(tt, 60.0 * (1 - v)),
            key=(id(t), "in"), easing=anim.ease_out_back)

        if duration:
            t.job = self.root.after(duration, lambda: self._dismiss(t))
        return t

    def clear(self):
        for t in list(self._toasts):
            self._dismiss(t, animate=False)

    # ------------------------------------------------------------ внутреннее
    def _target_y(self, index):
        """Смещение i-го тоста от нижнего края (0 — самый старый, внизу)."""
        y = float(self.MARGIN_Y)
        for t in self._toasts[:index]:
            y += t.height + self.GAP
        return y

    def _layout(self, immediate_for=None):
        for i, t in enumerate(self._toasts):
            target = self._target_y(i)
            if t is immediate_for:
                t.y_off = target
                continue
            start = t.y_off
            anim.get(self.root).animate(
                220,
                lambda v, tt=t, a=start, b=target: self._set_y(tt, a + (b - a) * v),
                key=(id(t), "y"))

    def _set_x(self, t, x):
        t.x_off = x
        self._place(t)

    def _set_y(self, t, y):
        t.y_off = y
        self._place(t)

    def _place(self, t):
        if t.dead:
            return
        t.frame.place(relx=1.0, rely=1.0, anchor="se",
                      x=-self.MARGIN_X + int(t.x_off), y=-int(t.y_off))
        t.frame.lift()

    def _dismiss(self, t, animate=True):
        if t.dead:
            return
        if t.job is not None:
            try:
                self.root.after_cancel(t.job)
            except Exception:
                pass
            t.job = None

        def _finish():
            if t.dead:
                return
            t.dead = True
            try:
                t.frame.destroy()
            except Exception:
                pass
            if t in self._toasts:
                self._toasts.remove(t)
                self._layout()

        a = anim.get(self.root)
        a.cancel((id(t), "in"))
        a.cancel((id(t), "y"))
        if not animate:
            _finish()
            return
        start = t.x_off
        a.animate(200, lambda v: self._set_x(t, start + (90 - start) * v),
                  on_done=_finish, key=(id(t), "out"),
                  easing=anim.ease_in_out_cubic)
