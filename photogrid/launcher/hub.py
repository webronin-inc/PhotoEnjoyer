"""Общее меню: после входа пользователь выбирает «Фото» или «Word».

HubScreen.run() возвращает: "photo" — запускать приложение «Фото»,
"logout" — пользователь вышел из аккаунта, None — окно закрыли.
Модуль Word работает прямо в этом окне и возвращает в меню."""
import tkinter as tk

from PIL import ImageTk

from .. import anim, branding, icons
from ..account import gate
from ..theme import DARK, apply_theme
from ..ui_widgets import _blend_hex, rounded_rect
from .backdrop import NeonBackdrop
from .registry import MODULES
from .word_panel import WordPanel

W, H = 960, 620


class _ModuleCard:
    """Карточка модуля. Рисуется прямо на общем холсте меню (а не отдельным
    виджетом), поэтому вокруг неё видно неоновый фон, а не прямоугольник."""
    CW, CH = 340, 290

    def __init__(self, cv, p, module, cx, cy, on_click, index=0):
        self.cv, self.p, self.module, self.on_click = cv, p, module, on_click
        self.x0, self.y0 = cx - self.CW // 2, cy - self.CH // 2
        self.tag = f"card_{module.id}"
        self.cursor = "hand2" if module.available else "arrow"
        self.hue = icons.NEON[module.hue]
        self._hv, self._rv, self._fl = 0.0, 0.0, 1.0
        self._closed = False
        cv.tag_bind(self.tag, "<Enter>", self._enter)
        cv.tag_bind(self.tag, "<Leave>", self._leave)
        cv.tag_bind(self.tag, "<Button-1>", self._click)
        anim.get(cv).animate(520, self._reveal, delay_ms=140 + 120 * index,
                             easing=anim.ease_out_cubic, key=(id(self), "rv"))

    def _root(self):                      # tween_attr ждёт у «виджета» метод _root()
        return self.cv._root()

    def _enter(self, e=None):
        try:
            self.cv.configure(cursor=self.cursor)
        except tk.TclError:
            return
        anim.tween_attr(self, "_hv", 1.0, 170, redraw=self._redraw)

    def _leave(self, e=None):
        try:
            self.cv.configure(cursor="")
        except tk.TclError:
            return
        anim.tween_attr(self, "_hv", 0.0, 240, redraw=self._redraw)

    def _reveal(self, t):
        self._rv = t
        self._redraw()

    def _click(self, e=None):
        if not self.module.available or self._closed:
            return
        if anim.effects_enabled():
            pts = ((0, 0.2), (0.25, 1.4), (0.5, 0.6), (1, 1.0))

            def upd(t):
                for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
                    if t <= t1:
                        self._fl = v0 + (v1 - v0) * (t - t0) / (t1 - t0)
                        break
                self._redraw()
            anim.get(self.cv).animate(300, upd, easing=anim.linear, key=(id(self), "fl"),
                                      on_done=lambda: (setattr(self, "_fl", 1.0), self._redraw()))
        self.cv.after(120, lambda: None if self._closed else self.on_click())

    def close(self):
        self._closed = True
        a = anim.get(self.cv)
        for k in ("rv", "fl", "_hv"):
            a.cancel((id(self), k))

    def _redraw(self):
        if self._closed:
            return
        cv, tag = self.cv, self.tag
        try:
            cv.delete(tag)
        except tk.TclError:
            return
        p, m = self.p, self.module
        hv, rv = self._hv, self._rv
        ok = m.available
        ox, oy = self.x0, self.y0
        dy = oy + (1 - rv) * 22 - 6 * hv * (1 if ok else 0)
        fade = lambda c: _blend_hex(c, p["bg"], rv)
        edge = _blend_hex(self.hue, p["border"], 0.65 * hv if ok else 0)
        rounded_rect(cv, ox + 4, dy + 10, ox + self.CW - 4, dy + self.CH - 4, radius=22,
                     fill=fade(_blend_hex(p["surface_hi"], p["surface"], hv * 0.7)),
                     outline=fade(edge), width=1 + int(hv * 1.2), tags=tag)
        glow = round(min(1.4, (0.45 + 0.7 * hv) * self._fl * (1 if ok else 0.25)) * 4) / 4.0
        icons.draw_neon(cv, m.icon, ox + self.CW // 2, dy + 98, size=62,
                        color=self.hue if ok else p["text_faint"], glow=glow, tags=tag)
        cv.create_text(ox + self.CW // 2, dy + 178, text=m.title,
                       fill=fade(p["text"] if ok else p["text_dim"]), font=("Segoe UI", 22, "bold"),
                       tags=tag)
        cv.create_text(ox + self.CW // 2, dy + 218, text=m.subtitle, width=self.CW - 60,
                       fill=fade(p["text_dim"]), font=("Segoe UI", 10), justify="center", tags=tag)
        if ok:
            col = _blend_hex(self.hue, p["surface"], 0.20 + 0.20 * hv)
            rounded_rect(cv, ox + self.CW // 2 - 62, dy + 244, ox + self.CW // 2 + 62, dy + 274,
                         radius=15, fill=fade(col), outline="", tags=tag)
            cv.create_text(ox + self.CW // 2, dy + 259, text="Открыть  →", fill=fade(self.hue),
                           font=("Segoe UI", 10, "bold"), tags=tag)
        else:
            cv.create_text(ox + self.CW // 2, dy + 259, text="Только в Windows",
                           fill=fade(icons.NEON["orange"]), font=("Segoe UI", 10, "bold"), tags=tag)


class HubScreen:
    def __init__(self, root, session=None):
        self.root, self.session = root, session
        self.p = p = DARK
        apply_theme(root, p)
        self.result = None
        self._done = tk.BooleanVar(value=False)
        self._closed = False
        self._panel = None

        root.title(branding.APP_NAME)
        root.configure(bg=p["bg"])
        root.resizable(False, False)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{max(0, (sw - W) // 2)}+{max(0, (sh - H) // 3)}")
        root.protocol("WM_DELETE_WINDOW", self._close)

        self.frame = tk.Frame(root, bg=p["bg"])
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.cv = tk.Canvas(self.frame, width=W, height=H, bg=p["bg"], highlightthickness=0)
        self.cv.pack()
        self.backdrop = NeonBackdrop(self.cv, W, H, p)
        self._build()
        if anim.effects_enabled():
            self.backdrop.start()
        self._track("hub_open")

    def run(self):
        self.root.wait_variable(self._done)
        return self.result

    def _track(self, event, **data):
        if self.session is not None:
            try:
                self.session.track(event, **data)
            except Exception:
                pass

    def _build(self):
        p, cv = self.p, self.cv
        self._logo = ImageTk.PhotoImage(icons.logo_pil(36, p["accent"], "P", 1.0))
        cv.create_image(56, 48, image=self._logo, tags="hub")
        cv.create_text(94, 40, text=branding.APP_NAME, anchor="w", fill=p["text"],
                       font=("Segoe UI", 16, "bold"), tags="hub")
        cv.create_text(94, 62, text="Меню приложений", anchor="w", fill=p["text_dim"],
                       font=("Segoe UI", 10), tags="hub")

        s = self.session
        self.btn_logout = None
        if s is not None:
            days = s.days_left()
            lic = ("бессрочная лицензия" if days is None and s.license_active
                   else f"лицензия: осталось {days} дн." if s.license_active else "лицензия не активна")
            chip = f"{s.username}  ·  {lic}" + ("  ·  без сети" if s.offline else "")
            cv.create_text(W - 150, 50, text=chip, anchor="e", fill=p["text_dim"],
                           font=("Segoe UI", 10), tags="hub")
            self.btn_logout = tk.Button(self.frame, text="Выйти", command=self._logout, bd=0,
                                        relief="flat", cursor="hand2", bg=p["surface_alt"],
                                        fg=p["text"], activebackground=p["surface_hi"],
                                        activeforeground=p["text"], font=("Segoe UI", 10),
                                        padx=14, pady=6, highlightthickness=0, takefocus=0)
            cv.create_window(W - 70, 50, window=self.btn_logout, tags="hub")

        cv.create_text(W // 2, 142, text="Что запустим?", fill=p["text"],
                       font=("Segoe UI", 30, "bold"), tags="hub")
        cv.create_text(W // 2, 182, text="Выберите приложение", fill=p["text_dim"],
                       font=("Segoe UI", 11), tags="hub")
        from ..version import __version__
        cv.create_text(W // 2, H - 22, text=f"версия {__version__}", fill=p["text_faint"],
                       font=("Segoe UI", 9), tags="hub")

        self.cards = []
        n = len(MODULES)
        gap = 36
        total = n * _ModuleCard.CW + (n - 1) * gap
        x0 = (W - total) // 2 + _ModuleCard.CW // 2
        for i, m in enumerate(MODULES):
            self.cards.append(_ModuleCard(cv, p, m, x0 + i * (_ModuleCard.CW + gap), 400,
                                          lambda m=m: self._open(m), index=i))
        self.root.bind("<Escape>", lambda e: self._escape())

    def _open(self, module):
        self._track("module_open", id=module.id)
        if module.id == "word":
            self._show_word()
            return
        self.result = module.id
        self._finish()

    def _show_word(self, flow_factory=None):
        for c in self.cards:
            self.cv.itemconfigure(c.tag, state="hidden")
        self.cv.itemconfigure("hub", state="hidden")
        self._panel = WordPanel(self.frame, self.p, self.session, self._back_from_word,
                                flow_factory=flow_factory or getattr(self, "flow_factory", None))
        self.cv.create_window(W // 2, H // 2 + 8, window=self._panel, tags="panel")
        self._panel.start()

    def _back_from_word(self):
        if self._panel is not None:
            self._panel.destroy()
            self._panel = None
            self.cv.delete("panel")
        for c in self.cards:
            self.cv.itemconfigure(c.tag, state="normal")
        self.cv.itemconfigure("hub", state="normal")

    def _escape(self):
        if self._panel is not None and not self._panel._running:
            self._back_from_word()

    def _logout(self):
        gate.logout(self.session)
        self.result = "logout"
        self._finish()

    def _close(self):
        self.result = None
        self._finish()

    def _finish(self):
        self._closed = True
        self.backdrop.stop()
        for c in self.cards:
            c.close()
        try:
            self.root.unbind("<Escape>")
        except Exception:
            pass
        if self._panel is not None:
            self._panel.destroy()
            self._panel = None
        self.root.resizable(True, True)
        self.frame.destroy()
        self._done.set(True)
