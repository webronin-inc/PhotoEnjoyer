"""Окно входа перед запуском программы.

Слева — неоновая «витрина» с плавающим светом, справа — карточка со вкладками
«Вход» и «Регистрация по ключу». После отправки формы идёт видимая цепочка
проверок (связь → версия → аккаунт → лицензия → устройство → часы). Ошибки
показываются понятно и с действием: повторить, скачать обновление, отключить
старое устройство, продлить ключом, работать без сети.
"""
import math
import queue
import random
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from .. import anim, branding, fx, icons, legal
from ..account import gate, store
from ..account.api import ApiError, NetworkError
from ..theme import DARK, apply_theme
from ..ui_widgets import (GradientButton, SegmentedControl, _blend_hex,
                          rounded_rect)

W, H = 960, 620
HERO_W = 480


# ============================================================== поле ввода
class _NeonField(tk.Frame):
    """Подпись + поле с иконкой и неоновой линией, растущей из центра при фокусе."""

    def __init__(self, parent, p, label, icon, secret=False, hue="violet", var=None):
        super().__init__(parent, bg=p["surface"])
        self.p, self.hue = p, icons.NEON[hue]
        self._icon = icon
        self.var = var or tk.StringVar()
        self._fv = 0.0
        self._secret = secret
        tk.Label(self, text=label, bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)
        row = tk.Frame(self, bg=p["surface"])
        row.pack(fill=tk.X, pady=(4, 0))
        self._ic = tk.Canvas(row, width=26, height=26, bg=p["surface"], highlightthickness=0)
        self._ic.pack(side=tk.LEFT)
        self.entry = tk.Entry(row, textvariable=self.var, bg=p["surface"], fg=p["text"],
                              insertbackground=self.hue, relief="flat", bd=0,
                              highlightthickness=0, font=("Segoe UI", 11),
                              show="•" if secret else "",
                              selectbackground=p["accent"], selectforeground="#ffffff")
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0), ipady=5)
        self._eye = None
        if secret:
            self._eye = tk.Canvas(row, width=26, height=26, bg=p["surface"],
                                  highlightthickness=0, cursor="hand2")
            self._eye.pack(side=tk.RIGHT)
            self._eye.bind("<Button-1>", lambda e: self._toggle_eye())
        self.line = tk.Canvas(self, height=3, bg=p["surface"], highlightthickness=0)
        self.line.pack(fill=tk.X, pady=(2, 0))
        self.line.bind("<Configure>", lambda e: self._draw())
        self.entry.bind("<FocusIn>", lambda e: anim.tween_attr(self, "_fv", 1.0, 220, redraw=self._draw))
        self.entry.bind("<FocusOut>", lambda e: anim.tween_attr(self, "_fv", 0.0, 260, redraw=self._draw))
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._draw()

    def _toggle_eye(self):
        self._secret = not self._secret
        self.entry.configure(show="•" if self._secret else "")
        self._draw()

    def _draw(self):
        try:
            p = self.p
            self._ic.delete("all")
            col = _blend_hex(self.hue, p["text_faint"], self._fv)
            icons.draw(self._ic, self._icon_kind(), 13, 13, size=18, color=col)
            if self._eye is not None:
                self._eye.delete("all")
                icons.draw(self._eye, "eye_off" if self._secret else "eye", 13, 13, size=18,
                           color=p["text_dim"])
            w = max(1, self.line.winfo_width())
            self.line.delete("all")
            self.line.create_rectangle(0, 1, w, 2, fill=p["border"], outline="")
            half = (w / 2) * self._fv
            if half > 0.5:
                self.line.create_rectangle(w / 2 - half, 0, w / 2 + half, 3,
                                           fill=self.hue, outline="")
        except tk.TclError:
            pass

    def _icon_kind(self):
        return self._icon

    def set_icon(self, kind):
        self._icon = kind
        self._draw()

    def _on_destroy(self, event):
        if event.widget is self:
            anim.get(self).cancel((id(self), "_fv"))

    def get(self):
        return self.var.get()

    def shake_focus(self):
        self.entry.focus_set()


# =========================================================== панель проверок
class _Steps(tk.Canvas):
    """Список проверок: ожидание → вращающийся индикатор → ✓ / ! / ✕."""

    ROW = 34

    def __init__(self, parent, p):
        super().__init__(parent, width=380, height=len(gate.STEPS) * self.ROW + 6,
                         bg=p["surface"], highlightthickness=0)
        self.p = p
        self.state = {k: ("pending", "") for k, _ in gate.STEPS}
        self._t0 = {}
        self._job = None
        self._font = ("Segoe UI", 10)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._redraw()

    def reset(self):
        self.state = {k: ("pending", "") for k, _ in gate.STEPS}
        self._t0 = {}
        self._redraw()

    def set(self, step, state, detail=""):
        if step not in self.state:
            return
        self.state[step] = (state, detail)
        self._t0[step] = time.time()
        self._redraw()
        self._ensure_tick()

    def _ensure_tick(self):
        busy = any(s == "running" for s, _ in self.state.values()) or any(
            time.time() - t < 0.4 for t in self._t0.values())
        if busy and self._job is None:
            self._job = self.after(33, self._tick)

    def _tick(self):
        self._job = None
        try:
            if not self.winfo_exists():
                return
            self._redraw()
            self._ensure_tick()
        except tk.TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _redraw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        p, now = self.p, time.time()
        names = dict(gate.STEPS)
        y = self.ROW // 2 + 2
        for key, _ in gate.STEPS:
            state, detail = self.state[key]
            cx = 16
            dt = now - self._t0.get(key, 0)
            if state == "pending":
                self.create_oval(cx - 4, y - 4, cx + 4, y + 4, outline=p["border"], width=2)
                fg = p["text_faint"]
            elif state == "running":
                a = (now * 360 * 1.4) % 360
                self.create_oval(cx - 9, y - 9, cx + 9, y + 9, outline=p["border"], width=2)
                self.create_arc(cx - 9, y - 9, cx + 9, y + 9, start=-a, extent=100,
                                style="arc", outline=icons.NEON["cyan"], width=3)
                fg = p["text"]
            else:
                kind, hue = {"ok": ("check", "lime"), "warn": ("alert", "orange"),
                             "fail": ("close", "red"), "skip": ("check", "white")}[state]
                scale = min(1.0, 0.55 + dt * 4) if dt < 0.25 else 1.0     # «выпрыгивает»
                size = int(18 * scale)
                icons.draw_neon(self, kind, cx, y, size=max(10, size),
                                color=icons.NEON[hue], glow=0.75 if state != "skip" else 0.25)
                fg = p["text"] if state != "fail" else icons.NEON["red"]
            label = names[key]
            self.create_text(40, y, text=label, anchor="w", fill=fg, font=self._font)
            if detail:
                self.create_text(370, y, text=detail[:34], anchor="e",
                                 fill=p["text_faint"] if state != "fail" else icons.NEON["red"],
                                 font=("Segoe UI", 8))
            y += self.ROW


# ================================================================== экран
class LoginScreen:
    def __init__(self, root, resume=True):
        self.root = root
        self.p = p = DARK
        apply_theme(root, p)
        self.api = gate.make_api()
        self.result = None
        self._done = tk.BooleanVar(value=False)
        self._q = None
        self._after = {}
        self._creds = None
        self._countdown = None
        self._closed = False
        self._bg_phase = 0.0
        self._particles = []
        self._busy = False
        self._uiq = queue.Queue()       # безопасная передача из потоков в интерфейс

        root.title(f"{branding.APP_NAME} — вход")
        root.configure(bg=p["bg"])
        root.resizable(False, False)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{max(0, (sw - W) // 2)}+{max(0, (sh - H) // 3)}")
        root.protocol("WM_DELETE_WINDOW", self._cancel)
        try:
            root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

        self.frame = tk.Frame(root, bg=p["bg"])
        self.frame.pack(fill=tk.BOTH, expand=True)
        self._build_hero()
        self._build_card()
        self._pump_ui()
        self._probe_status()
        root.bind("<Return>", self._on_enter)
        if anim.effects_enabled():
            self._intro()
            self._bg_tick()
        if resume and store.load():
            self._later("resume", 600, self._auto_resume)

    # ------------------------------------------------------- служебное
    def run(self):
        """Блокирует до входа/закрытия окна; возвращает Session или None."""
        self.root.wait_variable(self._done)
        return self.result

    def _later(self, key, ms, fn):
        old = self._after.pop(key, None)
        if old:
            try:
                self.root.after_cancel(old)
            except Exception:
                pass
        self._after[key] = self.root.after(ms, fn)

    def _cancel(self):
        self.result = None
        self._teardown()
        self._done.set(True)

    def _teardown(self):
        self._closed = True
        for k, j in list(self._after.items()):
            try:
                self.root.after_cancel(j)
            except Exception:
                pass
        self._after.clear()
        try:
            self.root.unbind("<Return>")
        except Exception:
            pass

    # ------------------------------------------------------- витрина (слева)
    def _build_hero(self):
        p = self.p
        cv = self.hero = tk.Canvas(self.frame, width=HERO_W, height=H, bg=p["bg"],
                                   highlightthickness=0)
        cv.pack(side=tk.LEFT)
        # фон: тёмный градиент
        bg = Image.new("RGB", (HERO_W, H))
        d = ImageDraw.Draw(bg)
        for y in range(H):
            t = y / H
            d.line([(0, y), (HERO_W, y)], fill=(int(10 + 10 * t), int(10 + 6 * t), int(24 + 22 * t)))
        self._bg_img = ImageTk.PhotoImage(bg)
        cv.create_image(0, 0, image=self._bg_img, anchor="nw")
        # неоновые «облака света»
        self._blobs = []
        for i, hue in enumerate(("violet", "cyan", "pink")):
            size = 360
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            col = tuple(int(icons.NEON[hue].lstrip("#")[j:j + 2], 16) for j in (0, 2, 4))
            ImageDraw.Draw(img).ellipse((60, 60, size - 60, size - 60), fill=col + (120,))
            img = img.filter(ImageFilter.GaussianBlur(55))
            ph = ImageTk.PhotoImage(img)
            item = cv.create_image(100 + i * 120, 200 + i * 130, image=ph)
            self._blobs.append([ph, item, random.uniform(0, 6.28), 0.6 + i * 0.25])
        # лёгкие частицы
        self._particles = [[random.uniform(0, HERO_W), random.uniform(0, H),
                            random.uniform(0.15, 0.55), random.uniform(1.2, 2.6),
                            cv.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")]
                           for _ in range(26)]
        # логотип и заголовок
        self._logo = ImageTk.PhotoImage(icons.logo_pil(76, p["accent"], "P", 1.0))
        cv.create_image(HERO_W // 2, 150, image=self._logo)
        self._title = cv.create_text(HERO_W // 2, 262, text=branding.APP_NAME, fill=p["text"],
                                     font=("Segoe UI", 30, "bold"))
        self._tag = cv.create_text(HERO_W // 2, 306, text="Коллажи из фотографий за пару кликов",
                                   fill=p["accent_hi"], font=("Segoe UI", 12))
        self._feats = []
        y = 380
        for kind, text in legal.FEATURES:
            img = icons.tk_neon(kind, 24, icons.NEON["cyan" if kind == "wand" else
                                                    "pink" if kind == "template" else "violet"], 1.0)
            ic = cv.create_image(70, y, image=img)
            tx = cv.create_text(104, y, text=text, anchor="w", fill=p["text_dim"],
                                font=("Segoe UI", 11))
            self._feats.append((img, ic, tx))
            y += 52
        from ..version import __version__
        cv.create_text(HERO_W // 2, H - 26, text=f"версия {__version__}", fill=p["text_faint"],
                       font=("Segoe UI", 9))

    def _intro(self):
        """Заголовок и пункты «проявляются» по очереди."""
        p, cv = self.p, self.hero
        items = [(self._title, p["text"]), (self._tag, p["accent_hi"])] + [
            (tx, p["text_dim"]) for _, _, tx in self._feats]
        for i, (item, final) in enumerate(items):
            cv.itemconfigure(item, fill=p["bg"])

            def upd(t, item=item, final=final):
                try:
                    cv.itemconfigure(item, fill=_blend_hex(final, p["bg"], t))
                except tk.TclError:
                    pass
            anim.get(cv).animate(520, upd, delay_ms=250 + i * 140, key=(id(cv), "intro", i))

    def _bg_tick(self):
        if self._closed:
            return
        try:
            if self.hero.winfo_exists() and anim.effects_enabled():
                self._bg_phase += 0.012
                for ph, item, off, speed in self._blobs:
                    t = self._bg_phase * speed + off
                    self.hero.coords(item, HERO_W / 2 + math.sin(t) * 150,
                                     H / 2 + math.cos(t * 0.8) * 190)
                for pt in self._particles:
                    pt[1] -= pt[2]
                    if pt[1] < -4:
                        pt[1], pt[0] = H + 4, random.uniform(0, HERO_W)
                    r = pt[3]
                    self.hero.coords(pt[4], pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r)
                    self.hero.itemconfigure(pt[4], fill=_blend_hex("#ffffff", self.p["bg"], 0.35 + 0.25 * math.sin(pt[1] / 40)))
            self._later("bg", 40, self._bg_tick)
        except tk.TclError:
            pass

    # ------------------------------------------------------- карточка (справа)
    def _build_card(self):
        p = self.p
        self.card = tk.Frame(self.frame, bg=p["surface"], width=W - HERO_W, height=H)
        self.card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.card.pack_propagate(False)
        body = self.body = tk.Frame(self.card, bg=p["surface"])
        body.pack(fill=tk.BOTH, expand=True, padx=46, pady=(40, 24))

        self.h1 = tk.Label(body, text="Добро пожаловать", bg=p["surface"], fg=p["text"],
                           font=("Segoe UI", 22, "bold"), anchor="w")
        self.h1.pack(fill=tk.X)
        self.h2 = tk.Label(body, text="Войдите, чтобы продолжить", bg=p["surface"],
                           fg=p["text_dim"], font=("Segoe UI", 10), anchor="w")
        self.h2.pack(fill=tk.X, pady=(2, 16))

        self.tab_var = tk.StringVar(value="login")
        self.tabs = SegmentedControl(body, p, [("login", "Вход"), ("register", "Регистрация по ключу")],
                                     variable=self.tab_var, padx=16, pady=6)
        self.tabs.pack(anchor="w", pady=(0, 14))
        self.tab_var.trace_add("write", lambda *a: self._on_tab())

        self.banner = tk.Label(body, text="", bg=p["surface"], fg=icons.NEON["orange"],
                               font=("Segoe UI", 9), anchor="w", justify="left", wraplength=380)
        self.banner.pack(fill=tk.X)

        self.area = tk.Frame(body, bg=p["surface"], height=330)
        self.area.pack(fill=tk.X)
        self.area.pack_propagate(False)

        # --- форма входа
        self.f_login = tk.Frame(self.area, bg=p["surface"])
        self.in_user = _NeonField(self.f_login, p, "Логин", "user", hue="violet")
        self.in_user.set_icon("user")
        self.in_user.pack(fill=tk.X, pady=(0, 12))
        self.in_pass = _NeonField(self.f_login, p, "Пароль", "lock", secret=True, hue="cyan")
        self.in_pass.set_icon("lock")
        self.in_pass.pack(fill=tk.X, pady=(0, 12))
        self.remember = tk.BooleanVar(value=True)
        self._check_row(self.f_login, self.remember, "Запомнить меня на этом компьютере").pack(
            fill=tk.X, pady=(2, 0))

        # --- форма регистрации
        self.f_reg = tk.Frame(self.area, bg=p["surface"])
        self.rg_key = _NeonField(self.f_reg, p, "Ключ лицензии", "key", hue="pink")
        self.rg_key.set_icon("key")
        self.rg_key.pack(fill=tk.X, pady=(0, 9))
        self.rg_key.var.trace_add("write", lambda *a: self._format_key())
        self.rg_user = _NeonField(self.f_reg, p, "Придумайте логин", "user", hue="violet")
        self.rg_user.set_icon("user")
        self.rg_user.pack(fill=tk.X, pady=(0, 9))
        self.rg_pass = _NeonField(self.f_reg, p, "Пароль (минимум 8 символов)", "lock",
                                  secret=True, hue="cyan")
        self.rg_pass.set_icon("lock")
        self.rg_pass.pack(fill=tk.X, pady=(0, 9))
        self.consent = tk.BooleanVar(value=False)
        row = self._check_row(self.f_reg, self.consent, "Согласен с обработкой данных")
        row.pack(fill=tk.X)
        link = tk.Label(row, text="что собирается?", bg=p["surface"], fg=p["accent_hi"],
                        font=("Segoe UI", 9, "underline"), cursor="hand2")
        link.pack(side=tk.LEFT, padx=(8, 0))
        link.bind("<Button-1>", lambda e: self._show_terms())

        # --- панель проверок
        self.f_steps = tk.Frame(self.area, bg=p["surface"])
        self.steps_title = tk.Label(self.f_steps, text="Проверяем…", bg=p["surface"], fg=p["text"],
                                    font=("Segoe UI", 12, "bold"), anchor="w")
        self.steps_title.pack(fill=tk.X, pady=(0, 8))
        self.steps = _Steps(self.f_steps, p)
        self.steps.pack(anchor="w")
        self.err = tk.Label(self.f_steps, text="", bg=p["surface"], fg=icons.NEON["red"],
                            font=("Segoe UI", 10), anchor="w", justify="left", wraplength=380)
        self.err.pack(fill=tk.X, pady=(10, 0))
        self.extra = tk.Frame(self.f_steps, bg=p["surface"])       # доп. элементы ошибки
        self.extra.pack(fill=tk.X, pady=(6, 0))

        # --- активация ключа
        self.f_act = tk.Frame(self.area, bg=p["surface"])
        tk.Label(self.f_act, text="Лицензия не активна", bg=p["surface"], fg=icons.NEON["orange"],
                 font=("Segoe UI", 14, "bold"), anchor="w").pack(fill=tk.X)
        self.act_msg = tk.Label(self.f_act, text="Введите новый ключ, чтобы продолжить.",
                                bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 10),
                                anchor="w", justify="left", wraplength=380)
        self.act_msg.pack(fill=tk.X, pady=(2, 14))
        self.act_key = _NeonField(self.f_act, p, "Ключ лицензии", "key", hue="pink")
        self.act_key.set_icon("key")
        self.act_key.pack(fill=tk.X)
        self.act_key.var.trace_add("write", lambda *a: self._format_key(self.act_key))

        # --- кнопки внизу
        self.btns = tk.Frame(body, bg=p["surface"])
        self.btns.pack(fill=tk.X, pady=(10, 0))
        self.submit = GradientButton(self.btns, p, text="Войти", icon="logout", height=46,
                                     command=self._submit)
        self.submit.pack(fill=tk.X)
        self.foot = tk.Label(body, text=self._support_text(), bg=p["surface"],
                             fg=p["text_faint"], font=("Segoe UI", 9), anchor="w",
                             justify="left", wraplength=380)
        self.foot.pack(fill=tk.X, pady=(12, 0))

        self.mode = "login"
        self._show("login")
        self.in_user.entry.focus_set()
        if anim.effects_enabled():
            fx.stagger_rise([body], dy=24, duration=620)

    def _check_row(self, parent, var, text):
        p = self.p
        row = tk.Frame(parent, bg=p["surface"])
        cv = tk.Canvas(row, width=22, height=22, bg=p["surface"], highlightthickness=0, cursor="hand2")
        cv.pack(side=tk.LEFT)

        def draw(*_):
            cv.delete("all")
            on = var.get()
            rounded_rect(cv, 2, 2, 20, 20, radius=6,
                         fill=icons.NEON["cyan"] if on else p["surface_alt"],
                         outline=icons.NEON["cyan"] if on else p["border"])
            if on:
                icons.draw(cv, "check", 11, 11, size=14, color="#06121a")
        var.trace_add("write", draw)
        draw()
        lbl = tk.Label(row, text=text, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 10),
                       cursor="hand2")
        lbl.pack(side=tk.LEFT, padx=(8, 0))
        for w in (cv, lbl):
            w.bind("<Button-1>", lambda e: var.set(not var.get()))
        return row

    def _support_text(self):
        from .. import server_config
        return server_config.SUPPORT_HINT

    # ------------------------------------------------------- переключение видов
    def _show(self, which):
        for f in (self.f_login, self.f_reg, self.f_steps, self.f_act):
            f.pack_forget()
        frame = {"login": self.f_login, "register": self.f_reg, "steps": self.f_steps,
                 "activate": self.f_act}[which]
        frame.pack(fill=tk.BOTH, expand=True)
        self.area.configure(height={"login": 230, "register": 330, "activate": 280,
                                    "steps": 440}[which])
        self.view = which
        if which in ("login", "register"):
            self.mode = which
            self.tabs.pack(anchor="w", pady=(0, 14), before=self.banner)
            self.submit.pack_forget()
            self.submit = self._remake_submit("Войти" if which == "login" else "Создать аккаунт",
                                              "logout" if which == "login" else "user")
            self.h2.configure(text="Войдите, чтобы продолжить" if which == "login"
                              else "Один ключ — один аккаунт")
        elif which == "activate":
            self.tabs.pack_forget()
            self.submit.pack_forget()
            self.submit = self._remake_submit("Активировать ключ", "key")
            self.h2.configure(text="Осталось продлить доступ")
        else:
            self.tabs.pack_forget()
            self.submit.pack_forget()
        if anim.effects_enabled() and which != "steps":
            fx.stagger_rise([frame], dy=10, duration=260)

    def _remake_submit(self, text, icon):
        try:
            self.submit.destroy()
        except tk.TclError:
            pass
        b = GradientButton(self.btns, self.p, text=text, icon=icon, height=46, command=self._submit)
        b.pack(fill=tk.X)
        return b

    def _on_tab(self):
        if self.view in ("login", "register") and self.tab_var.get() != self.mode:
            self._show(self.tab_var.get())
            (self.in_user if self.mode == "login" else self.rg_key).entry.focus_set()

    def _format_key(self, field=None):
        field = field or self.rg_key
        raw = "".join(ch for ch in field.var.get().upper() if ch.isalnum())
        if raw.startswith("PE"):
            raw = raw[2:]
        raw = raw[:12]
        parts = [raw[i:i + 4] for i in range(0, len(raw), 4)]
        text = ("PE-" + "-".join(parts)) if parts else ""
        if text != field.var.get():
            field.var.set(text)
            field.entry.icursor(tk.END)

    def _on_enter(self, event=None):
        if self.view in ("login", "register", "activate") and not self._busy:
            self._submit()

    # ------------------------------------------------------- фон: статус сервера
    def _probe_status(self):
        def work():
            try:
                st = self.api.status()
            except Exception:
                return
            self._ui(lambda: self._apply_status(st))
        threading.Thread(target=work, daemon=True).start()

    def _apply_status(self, st):
        parts = []
        if st.get("maintenance"):
            parts.append("Идут технические работы: " + st.get("maintenance_text", ""))
        if st.get("motd"):
            parts.append(st["motd"])
        self.banner.configure(text="\n".join(parts))
        sup = st.get("support_contact")
        if sup:
            self.foot.configure(text=f"{self._support_text()} Связь: {sup}")

    def _ui(self, fn):
        """Вызывать из рабочих потоков: функция выполнится в потоке интерфейса."""
        self._uiq.put(fn)

    def _pump_ui(self):
        if self._closed:
            return
        try:
            while True:
                self._uiq.get_nowait()()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self._later("ui", 50, self._pump_ui)

    # ------------------------------------------------------- отправка формы
    def _submit(self):
        if self._busy:
            return
        if self.view == "activate":
            return self._activate()
        if self.mode == "login":
            u, pw = self.in_user.get().strip(), self.in_pass.get()
            if not u or not pw:
                return self._shake("Введите логин и пароль")
            creds = {"username": u, "password": pw}
            self._start("login", creds, self.remember.get())
        else:
            if not self.consent.get():
                return self._shake("Нужно согласиться с обработкой данных")
            key = self.rg_key.get().strip()
            u, pw = self.rg_user.get().strip(), self.rg_pass.get()
            if len(key) < 17:
                return self._shake("Введите ключ полностью: PE-XXXX-XXXX-XXXX")
            if len(u) < 3 or len(pw) < 8:
                return self._shake("Логин — от 3 символов, пароль — от 8")
            self._start("register", {"key": key, "username": u, "password": pw,
                                     "consent": True}, True)

    def _shake(self, message=None):
        """Карточка «трясётся», если что-то не так."""
        if message:
            self.banner.configure(text=message, fg=icons.NEON["red"])
        if not anim.effects_enabled():
            return

        def upd(t):
            off = int(math.sin(t * math.pi * 6) * 9 * (1 - t))
            try:
                self.body.pack_configure(padx=(46 + off, 46 - off))
            except tk.TclError:
                pass
        anim.get(self.body).animate(380, upd, easing=anim.linear,
                                    on_done=lambda: upd(1.0), key=(id(self.body), "shake"))

    def _start(self, mode, creds, remember):
        self._creds = (mode, creds, remember)
        self.banner.configure(text="", fg=icons.NEON["orange"])
        self._begin_checks("Входим…" if mode == "login" else "Создаём аккаунт…")
        self._run(lambda prog: gate.authenticate(self.api, mode, creds, remember, prog))

    def _auto_resume(self):
        if self._closed or self._busy:
            return
        self._creds = None
        self._begin_checks("С возвращением! Проверяем сессию…")
        self._run(lambda prog: gate.resume(self.api, prog))

    def _begin_checks(self, title):
        self._busy = True
        self._show("steps")
        self.steps.reset()
        self.steps_title.configure(text=title)
        self.err.configure(text="")
        for w in self.extra.winfo_children():
            w.destroy()
        self.submit.pack_forget()
        self.h2.configure(text="Это займёт пару секунд")

    def _run(self, job):
        q = self._q = queue.Queue()

        def prog(step, state, detail=""):
            q.put(("step", step, state, detail))

        def work():
            try:
                q.put(("ok", job(prog)))
            except gate.GateError as e:
                q.put(("gate", e))
            except Exception as e:      # непредвиденное — тоже показываем, а не падаем
                q.put(("crash", e))
        threading.Thread(target=work, daemon=True).start()
        self._poll()

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, *rest = self._q.get_nowait()
                if kind == "step":
                    self.steps.set(*rest)
                elif kind == "ok":
                    return self._on_session(rest[0])
                elif kind == "gate":
                    return self._on_gate_error(rest[0])
                elif kind == "crash":
                    return self._on_gate_error(gate.GateError(
                        "crash", f"Что-то пошло не так: {rest[0]}", "account", "retry"))
        except queue.Empty:
            pass
        self._later("poll", 40, self._poll)

    # ------------------------------------------------------- результат
    def _on_session(self, session):
        self._busy = False
        if session is None:             # сохранённой сессии нет → обычная форма
            self._show(self.tab_var.get())
            return
        if session.must_change_pw:
            self._force_password(session)
            return
        if not session.license_active and not session.is_admin:
            self._need_activation(session)
            return
        self._complete(session)

    def _complete(self, session):
        self.steps_title.configure(text="Готово! Запускаем…" if not session.offline
                                   else "Работаем без сети — запускаем…")
        self.h2.configure(text="")
        self.result = session

        def go():
            self._teardown()
            self.root.resizable(True, True)
            self.frame.destroy()
            self._done.set(True)
        self._later("go", 650 if anim.effects_enabled() else 50, go)

    def _on_gate_error(self, e):
        self._busy = False
        self.steps_title.configure(text="Не получилось")
        self.h2.configure(text=e.step == "network" and "Проверьте подключение" or "Проверка не пройдена")
        self.err.configure(text=e.message)
        self._shake()
        for w in self.extra.winfo_children():
            w.destroy()
        p = self.p
        row = tk.Frame(self.extra, bg=p["surface"])
        row.pack(fill=tk.X)

        def btn(text, cmd, primary=False):
            b = tk.Button(row, text=text, command=cmd, bd=0, relief="flat", cursor="hand2",
                          bg=p["accent"] if primary else p["surface_alt"], fg="#ffffff" if primary else p["text"],
                          activebackground=p["accent_hi"] if primary else p["surface_hi"],
                          activeforeground="#ffffff", font=("Segoe UI", 10, "bold" if primary else "normal"),
                          padx=14, pady=8, highlightthickness=0, takefocus=0)
            b.pack(side=tk.LEFT, padx=(0, 8))
            return b

        if e.action == "update":
            url = e.data.get("download_url")
            if url:
                btn("Скачать обновление", lambda: webbrowser.open(url), True)
        if e.action == "devices":
            self._devices_ui(e)
        if e.action == "retry":
            btn("Повторить", self._retry, True)
            if store.load():
                btn("Работать без сети", self._offline)
            # запасной выход: если с сервером беда, свежую версию можно скачать вручную
            btn("Страница загрузки", lambda: webbrowser.open(
                branding.APP_HOMEPAGE + "/releases/latest"))
        elif e.action == "activate":
            btn("Ввести ключ", lambda: self._need_activation(None), True)
        elif e.action == "wait" and e.code == "locked":
            self._lock_countdown(int(e.data.get("retry_after", 60)))
        if e.action not in ("retry", "devices"):
            btn("Назад", self._back)
        if e.code in ("token_invalid", "device_removed", "banned", "clock_rollback"):
            pass

    def _back(self):
        self._busy = False
        self._show(self.tab_var.get())
        self.banner.configure(text="")

    def _retry(self):
        if self._creds:
            mode, creds, remember = self._creds
            self._start(mode, creds, remember)
        else:
            self._auto_resume()

    def _offline(self):
        """Принудительно без сети: быстрый таймаут → ветка офлайн в resume()."""
        self.api.timeout = 1.5
        self._begin_checks("Проверяем сохранённую сессию…")
        self._run(lambda prog: gate.resume(self.api, prog))

    def _lock_countdown(self, seconds):
        end = time.time() + seconds
        lbl = tk.Label(self.extra, text="", bg=self.p["surface"], fg=self.p["text_dim"],
                       font=("Segoe UI", 10))
        lbl.pack(anchor="w")

        def tick():
            left = int(end - time.time())
            try:
                if left <= 0:
                    lbl.configure(text="Можно пробовать снова")
                    return
                lbl.configure(text=f"Повторить можно через {left // 60}:{left % 60:02d}")
                self._later("lock", 500, tick)
            except tk.TclError:
                pass
        tick()

    # ---- лимит устройств: выбрать, какое отключить
    def _devices_ui(self, e):
        p = self.p
        devices = e.data.get("devices", [])
        tk.Label(self.extra, text="Отключите одно из устройств:", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)
        sel = tk.IntVar(value=devices[0]["id"] if devices else 0)
        for d in devices[:5]:
            when = time.strftime("%d.%m.%Y", time.localtime(d.get("last_seen", 0)))
            tk.Radiobutton(self.extra, text=f"{d['name']}  ·  был {when}", variable=sel,
                           value=d["id"], bg=p["surface"], fg=p["text"], selectcolor=p["surface_alt"],
                           activebackground=p["surface"], activeforeground=p["text"],
                           font=("Segoe UI", 10), anchor="w", highlightthickness=0,
                           bd=0).pack(fill=tk.X)

        def release():
            if not self._creds:
                return
            _, creds, _ = self._creds
            try:
                self.api.release_device(creds["username"], creds["password"], sel.get())
            except (ApiError, NetworkError) as ex:
                self.err.configure(text=str(ex))
                return
            self._retry()
        tk.Button(self.extra, text="Отключить и войти", command=release, bd=0, relief="flat",
                  cursor="hand2", bg=p["accent"], fg="#ffffff", activebackground=p["accent_hi"],
                  activeforeground="#ffffff", font=("Segoe UI", 10, "bold"), padx=14, pady=8,
                  highlightthickness=0, takefocus=0).pack(anchor="w", pady=(8, 0))
        tk.Button(self.extra, text="Назад", command=self._back, bd=0, relief="flat", cursor="hand2",
                  bg=p["surface"], fg=p["text_dim"], activebackground=p["surface"],
                  font=("Segoe UI", 9), highlightthickness=0).pack(anchor="w")

    # ---- лицензия не активна
    def _need_activation(self, session):
        if session is not None:
            self._pending = session
        self._busy = False
        self._show("activate")
        state = self._pending.license_state if getattr(self, "_pending", None) else "expired"
        self.act_msg.configure(text={
            "expired": "Срок лицензии истёк. Введите новый ключ — доступ продлится.",
            "revoked": "Лицензия отозвана администратором. Если это ошибка — напишите ему "
                       "или введите новый ключ.",
        }.get(state, "К аккаунту не привязана лицензия. Введите ключ."))
        self.act_key.entry.focus_set()

    def _activate(self):
        key = self.act_key.get().strip()
        if len(key) < 17:
            return self._shake("Введите ключ полностью: PE-XXXX-XXXX-XXXX")
        s = self._pending
        self._busy = True

        def work():
            try:
                resp = s.api.activate_key(key)
                self._ui(lambda: self._activated(s, resp))
            except ApiError as e:
                self._ui(lambda: self._act_fail(e.message))
            except NetworkError:
                self._ui(lambda: self._act_fail("Нет связи с сервером"))
        threading.Thread(target=work, daemon=True).start()

    def _act_fail(self, msg):
        self._busy = False
        self._shake(msg)
        self.act_msg.configure(text=msg, fg=icons.NEON["red"])

    def _activated(self, session, resp):
        self._busy = False
        session.apply(resp)
        if session.license_active:
            store.save(session.token, session.username, True)
            self._show("steps")
            self.submit.pack_forget()
            self._complete(session)
        else:
            self._act_fail("Ключ принят, но лицензия не стала активной")

    # ---- временный пароль → обязательная смена
    def _force_password(self, session):
        p = self.p
        top = tk.Toplevel(self.root)
        top.title("Смена пароля")
        top.configure(bg=p["surface"])
        top.transient(self.root)
        top.grab_set()
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", lambda: None)
        wrap = tk.Frame(top, bg=p["surface"])
        wrap.pack(padx=30, pady=24)
        tk.Label(wrap, text="Задайте новый пароль", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(wrap, text="Администратор выдал временный пароль — замените его своим.",
                 bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9),
                 wraplength=320, justify="left").pack(anchor="w", pady=(2, 12))
        old = _NeonField(wrap, p, "Временный пароль", "lock", secret=True); old.set_icon("lock")
        old.pack(fill=tk.X, pady=(0, 8))
        new = _NeonField(wrap, p, "Новый пароль (от 8 символов)", "lock", secret=True, hue="cyan")
        new.set_icon("lock"); new.pack(fill=tk.X, pady=(0, 8))
        msg = tk.Label(wrap, text="", bg=p["surface"], fg=icons.NEON["red"], font=("Segoe UI", 9),
                       wraplength=320, justify="left")
        msg.pack(fill=tk.X)

        def save():
            try:
                session.api.change_password(old.get(), new.get())
            except ApiError as e:
                msg.configure(text=e.message)
                return
            except NetworkError:
                msg.configure(text="Нет связи с сервером")
                return
            top.destroy()
            session.info["user"]["must_change_pw"] = False
            self._on_session(session)
        GradientButton(wrap, p, text="Сохранить пароль", icon="check", height=42,
                       command=save).pack(fill=tk.X, pady=(12, 0))
        fx.dialog_in(top)
        old.entry.focus_set()

    def _show_terms(self):
        p = self.p
        top = tk.Toplevel(self.root)
        top.title(legal.PRIVACY_TITLE)
        top.configure(bg=p["surface"])
        top.transient(self.root)
        top.bind("<Escape>", lambda e: top.destroy())
        tk.Label(top, text=legal.PRIVACY_TITLE, bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=28, pady=(22, 8))
        tk.Label(top, text=legal.PRIVACY_TEXT, bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 10), justify="left", wraplength=520, anchor="w").pack(
            padx=28, pady=(0, 14))
        GradientButton(top, p, text="Понятно", icon="check", height=40,
                       command=top.destroy).pack(padx=28, pady=(0, 22), anchor="e")
        fx.dialog_in(top)
