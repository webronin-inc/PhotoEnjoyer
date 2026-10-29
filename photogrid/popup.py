"""Стильное всплывающее меню вместо серого системного tk.Menu.

Пункты — словари: label, command, icon (имя из icons.py), shortcut (текст),
enabled, danger; строка "-" — разделитель; {"title": "…"} — заголовок группы.
Меню плавно «всплывает», подсвечивает пункт под курсором, управляется
стрелками/Enter/Escape и закрывается кликом вне меню.
"""
import tkinter as tk

from . import anim, icons
from .ui_widgets import _blend_hex

_current = None


def close_current():
    global _current
    if _current is not None:
        _current.close()


def show(root, palette, items, x, y, min_width=230):
    """Показывает меню в экранных координатах (x, y) и возвращает объект меню."""
    close_current()
    return PopupMenu(root, palette, items, x, y, min_width)


class PopupMenu:
    def __init__(self, root, palette, items, x, y, min_width=230):
        global _current
        self.root = root
        self.p = p = palette
        self._rows = []            # (frame, widgets, item, state)
        self._index = None
        self._closed = False
        self._binds = []

        top = self.top = tk.Toplevel(root)
        top.withdraw()
        top.overrideredirect(True)
        top.configure(bg=p["border"])
        try:
            top.attributes("-topmost", True)
        except tk.TclError:
            pass

        body = tk.Frame(top, bg=p["surface"])
        body.pack(padx=1, pady=1)
        tk.Frame(body, bg=p["surface"], height=5).pack(fill=tk.X)
        for it in items:
            self._add(body, it)
        tk.Frame(body, bg=p["surface"], height=5).pack(fill=tk.X)
        body.update_idletasks()

        w = max(min_width, body.winfo_reqwidth() + 2)
        h = body.winfo_reqheight() + 2
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(4, min(x, sw - w - 4))
        y = max(4, min(y, sh - h - 4))
        self._geom = (w, h, x, y)
        top.geometry(f"{w}x{h}+{x}+{y}")
        for fr, *_ in self._rows:
            fr.pack_configure(fill=tk.X)

        top.bind("<Escape>", lambda e: self.close())
        top.bind("<Up>", lambda e: self._move(-1))
        top.bind("<Down>", lambda e: self._move(1))
        top.bind("<Return>", lambda e: self._activate(self._index))
        top.bind("<Destroy>", self._on_destroy, add="+")
        # закрытие по клику вне меню / при сдвиге окна — подписываемся чуть позже,
        # чтобы не поймать тот самый клик, который меню открыл
        root.after(30, self._arm)
        _current = self
        self._show_animated()

    # ---------------------------------------------------------------- пункты
    def _add(self, parent, it):
        p = self.p
        if it == "-":
            tk.Frame(parent, bg=p["border_soft"], height=1).pack(
                fill=tk.X, padx=12, pady=5)
            return
        if "title" in it:
            tk.Label(parent, text=it["title"].upper(), bg=p["surface"],
                     fg=p["text_faint"], font=("Segoe UI", 8, "bold"),
                     anchor="w").pack(fill=tk.X, padx=14, pady=(6, 2))
            return
        enabled = it.get("enabled", True)
        danger = it.get("danger", False)
        fg = p["text"] if enabled else p["text_faint"]
        if danger and enabled:
            fg = p["danger"]
        icon_col = fg if (danger and enabled) else (
            p["text_dim"] if enabled else p["text_faint"])

        fr = tk.Frame(parent, bg=p["surface"], cursor="hand2" if enabled else "arrow")
        fr.pack(fill=tk.X, padx=5)
        widgets = []
        if it.get("icon"):
            img = icons.tk_icon(it["icon"], 16, icon_col, 10)
            lb = tk.Label(fr, image=img, bg=p["surface"])
            lb.image = img
            lb.pack(side=tk.LEFT, padx=(9, 0), pady=7)
            widgets.append(lb)
        else:
            tk.Frame(fr, width=16, bg=p["surface"]).pack(side=tk.LEFT, padx=(9, 10))
        tl = tk.Label(fr, text=it["label"], bg=p["surface"], fg=fg,
                      font=("Segoe UI", 10), anchor="w")
        tl.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=7)
        widgets.append(tl)
        if it.get("shortcut"):
            sc = tk.Label(fr, text=it["shortcut"], bg=p["surface"],
                          fg=p["text_faint"], font=("Segoe UI", 8))
            sc.pack(side=tk.RIGHT, padx=(24, 10))
            widgets.append(sc)

        state = {"hv": 0.0}
        row = (fr, widgets, it, state)
        self._rows.append(row)
        i = len(self._rows) - 1
        if enabled:
            for w in [fr] + widgets:
                w.bind("<Enter>", lambda e, i=i: self._hover(i, True))
                w.bind("<Leave>", lambda e, i=i: self._hover(i, False))
                w.bind("<Button-1>", lambda e, i=i: self._activate(i))

    def _paint(self, i):
        fr, widgets, it, st = self._rows[i]
        col = _blend_hex(self.p["surface_hi"], self.p["surface"], st["hv"])
        try:
            fr.configure(bg=col)
            for w in widgets:
                w.configure(bg=col)
            for ch in fr.winfo_children():
                if isinstance(ch, tk.Frame):
                    ch.configure(bg=col)
        except tk.TclError:
            pass

    def _hover(self, i, on):
        if self._closed:
            return
        if on:
            self._index = i
            for j in range(len(self._rows)):          # убираем подсветку у других
                if j != i and self._rows[j][3]["hv"] > 0:
                    self._tween(j, 0.0)
        self._tween(i, 1.0 if on else 0.0)

    def _tween(self, i, target):
        st = self._rows[i][3]
        start = st["hv"]

        def upd(t):
            st["hv"] = start + (target - start) * t
            if not self._closed:
                self._paint(i)

        anim.get(self.root).animate(110, upd, key=(id(self), i))

    def _enabled_indexes(self):
        return [i for i, r in enumerate(self._rows) if r[2].get("enabled", True)]

    def _move(self, step):
        idx = self._enabled_indexes()
        if not idx:
            return
        if self._index not in idx:
            nxt = idx[0] if step > 0 else idx[-1]
        else:
            nxt = idx[(idx.index(self._index) + step) % len(idx)]
        self._hover(nxt, True)

    def _activate(self, i):
        if i is None or self._closed:
            return
        it = self._rows[i][2]
        if not it.get("enabled", True):
            return
        cmd = it.get("command")
        self.close()
        if cmd:
            self.root.after(10, cmd)       # дать меню исчезнуть до команды

    # ----------------------------------------------------------- показ/закрытие
    def _show_animated(self):
        w, h, x, y = self._geom
        top = self.top
        top.deiconify()
        top.lift()
        try:
            top.focus_force()
        except tk.TclError:
            pass
        if not anim.is_enabled():
            return

        def upd(t):
            if self._closed:
                return
            try:
                top.attributes("-alpha", t)
                top.geometry(f"{w}x{h}+{x}+{int(y - 8 * (1 - t))}")
            except tk.TclError:
                pass

        try:
            top.attributes("-alpha", 0.0)
        except tk.TclError:
            return
        anim.get(self.root).animate(150, upd, easing=anim.ease_out_cubic,
                                    on_done=lambda: upd(1.0),
                                    key=(id(self), "show"))

    def _arm(self):
        if self._closed:
            return
        for seq in ("<Button-1>", "<Button-3>"):
            fid = self.root.bind(seq, self._outside, add="+")
            self._binds.append((seq, fid))
        # клик в другое окно/приложение — меню теряет фокус и закрывается
        self.top.bind("<FocusOut>", lambda e: self.root.after(80, self._focus_lost))

    def _focus_lost(self):
        if self._closed:
            return
        try:
            if self.top.focus_get() is None:
                self.close()
        except (tk.TclError, KeyError):
            self.close()

    def _outside(self, event):
        try:
            w = event.widget
            if str(w).startswith(str(self.top)):
                return
        except Exception:
            pass
        self.close()

    def close(self):
        global _current
        if self._closed:
            return
        self._closed = True
        if _current is self:
            _current = None
        for seq, fid in self._binds:
            try:
                self.root.unbind(seq, fid)
            except Exception:
                pass
        self._binds = []
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is self.top:
            self._closed = True
