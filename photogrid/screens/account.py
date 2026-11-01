"""Личный кабинет: лицензия, устройства, пароль, приватность, новости."""
import subprocess
import sys
import time
import tkinter as tk

from .. import anim, icons, legal
from ..account import gate, store
from ..account.api import ApiError, NetworkError
from ..ui_widgets import (GradientButton, SegmentedControl, _blend_hex,
                          enable_mousewheel, rounded_rect)
from . import dialogs


def _date(ts):
    return time.strftime("%d.%m.%Y", time.localtime(ts)) if ts else "—"


def restart_app(app):
    """Перезапуск программы (после выхода из аккаунта — снова покажется вход)."""
    args = [sys.executable] + (sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
    try:
        subprocess.Popen(args)
    except Exception:
        pass
    app.on_close()


def _card(parent, p, title, kind, hue):
    box = tk.Frame(parent, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
    head = tk.Frame(box, bg=p["surface"])
    head.pack(fill=tk.X, padx=18, pady=(14, 6))
    ic = tk.Canvas(head, width=34, height=34, bg=p["surface"], highlightthickness=0)
    ic.pack(side=tk.LEFT)
    icons.draw_neon(ic, kind, 17, 17, size=18, color=icons.NEON[hue], glow=0.8)
    tk.Label(head, text=title, bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=(4, 0))
    inner = tk.Frame(box, bg=p["surface"])
    inner.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 16))
    return box, inner


def _link_btn(parent, p, text, cmd, danger=False, primary=False):
    fg = "#ff5470" if danger else ("#ffffff" if primary else p["text"])
    bg = p["accent"] if primary else p["surface_alt"]
    b = tk.Button(parent, text=text, command=cmd, bd=0, relief="flat", cursor="hand2",
                  bg=bg, fg=fg, activebackground=p["accent_hi"] if primary else p["surface_hi"],
                  activeforeground="#ffffff" if primary else fg, font=("Segoe UI", 9),
                  padx=12, pady=7, highlightthickness=0, takefocus=0)
    return b


class _LicenseBar(tk.Canvas):
    """Полоска «сколько осталось» с неоновой заливкой."""

    def __init__(self, parent, p, fraction, color):
        super().__init__(parent, height=10, bg=p["surface"], highlightthickness=0)
        self.p, self.color, self.target, self._v = p, color, fraction, 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self.after(120, lambda: anim.tween_attr(self, "_v", self.target, 700,
                                                easing=anim.ease_out_cubic, redraw=self._draw))

    def _draw(self):
        try:
            w = max(10, self.winfo_width())
            self.delete("all")
            rounded_rect(self, 0, 1, w, 9, radius=4, fill=self.p["surface_alt"], outline="")
            fw = max(8, int(w * self._v))
            if self._v > 0:
                rounded_rect(self, 0, 1, fw, 9, radius=4, fill=self.color, outline="")
        except tk.TclError:
            pass


def build_account_view(parent, app):
    p = app.palette
    s = app.session
    root = tk.Frame(parent, bg=p["bg"])

    if s is None:
        box = tk.Frame(root, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
        box.pack(expand=True)
        tk.Label(box, text="Вход не настроен", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 16, "bold")).pack(padx=50, pady=(34, 6))
        tk.Label(box, text="Личный кабинет появится, когда в программе будет указан "
                           "адрес сервера лицензий.", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 10), wraplength=380, justify="center").pack(padx=50, pady=(0, 34))
        return root

    # ---------------------------------------------------------- шапка
    head = tk.Frame(root, bg=p["bg"])
    head.pack(fill=tk.X, padx=8, pady=(6, 12))
    ic = tk.Canvas(head, width=52, height=52, bg=p["bg"], highlightthickness=0)
    ic.pack(side=tk.LEFT)
    icons.draw_neon(ic, "user", 26, 26, size=28, color=icons.NEON["violet"])
    box = tk.Frame(head, bg=p["bg"])
    box.pack(side=tk.LEFT, padx=(10, 0))
    tk.Label(box, text="Личный кабинет", bg=p["bg"], fg=p["text"],
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    sub = tk.Frame(box, bg=p["bg"])
    sub.pack(anchor="w")
    tk.Label(sub, text=s.username, bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 10)).pack(side=tk.LEFT)
    role_txt = "администратор" if s.is_admin else "пользователь"
    tk.Label(sub, text=f" {role_txt} ", bg=_blend_hex(p["accent"], p["bg"], 0.25), fg=p["accent_hi"],
             font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(8, 0))
    if s.offline:
        tk.Label(sub, text=" без сети ", bg=_blend_hex(icons.NEON["orange"], p["bg"], 0.25),
                 fg=icons.NEON["orange"], font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(6, 0))

    canvas = tk.Canvas(root, bg=p["bg"], highlightthickness=0)
    inner = tk.Frame(canvas, bg=p["bg"])
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.pack(fill=tk.BOTH, expand=True)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    enable_mousewheel(canvas)
    inner.columnconfigure((0, 1), weight=1, uniform="col")

    state = {"cards": {}}

    # ---------------------------------------------------------- лицензия
    lic_box, lic = _card(inner, p, "Лицензия", "key", "pink")
    lic_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    # ---------------------------------------------------------- устройства
    dev_box, dev = _card(inner, p, "Устройства", "server", "cyan")
    dev_box.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
    # ---------------------------------------------------------- безопасность
    sec_box, sec = _card(inner, p, "Безопасность", "lock", "lime")
    sec_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
    # ---------------------------------------------------------- приватность
    prv_box, prv = _card(inner, p, "Данные и приватность", "shield", "orange")
    prv_box.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)
    # ---------------------------------------------------------- новости
    news_box, news = _card(inner, p, "Новости", "megaphone", "pink")
    news_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)

    def clear(f):
        for w in f.winfo_children():
            w.destroy()

    # ---- лицензия
    def draw_license():
        clear(lic)
        st, exp, plan = s.license_state, s.license.get("expires"), s.license.get("plan") or "—"
        days = s.days_left()
        if st != "active":
            col, chip = icons.NEON["red"], {"expired": "Истекла", "revoked": "Отозвана"}.get(st, "Нет лицензии")
        elif days is not None and days <= 7:
            col, chip = icons.NEON["orange"], f"Осталось {days} дн."
        else:
            col, chip = icons.NEON["lime"], "Активна"
        top = tk.Frame(lic, bg=p["surface"])
        top.pack(fill=tk.X)
        tk.Label(top, text=plan, bg=p["surface"], fg=p["text"], font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text=f"  {chip}  ", bg=_blend_hex(col, p["surface"], 0.2), fg=col,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 0))
        if st == "active" and exp is None:
            line, frac = "Бессрочная лицензия", 1.0
        elif st == "active":
            line, frac = f"Действует до {_date(exp)}  ·  осталось {days} дн.", min(1.0, max(0.04, days / 90.0))
        else:
            line, frac = f"Срок истёк {_date(exp)}" if exp else "Лицензия не активна", 0.0
        tk.Label(lic, text=line, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 10)).pack(
            anchor="w", pady=(8, 8))
        _LicenseBar(lic, p, frac, col).pack(fill=tk.X)
        tk.Label(lic, text=f"Устройств по лицензии: {s.license.get('max_devices', 1)}",
                 bg=p["surface"], fg=p["text_faint"], font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 10))
        _link_btn(lic, p, "Активировать ключ", activate_key, primary=True).pack(anchor="w")

    def activate_key():
        if s.offline:
            return app.set_status("Нужна связь с сервером")

        def submit(v):
            try:
                resp = s.api.activate_key(v["key"])
            except ApiError as e:
                return e.message
            except NetworkError:
                return "Нет связи с сервером"
            s.apply(resp)
            store.save(s.token, s.username, True)
            draw_all()
            app.toasts.show("Лицензия обновлена", kind="success")
        dialogs.ask(app, "Активация ключа", [("key", "Ключ PE-XXXX-XXXX-XXXX", "", False)],
                    submit, ok_text="Активировать", ok_icon="key",
                    text="Новый ключ продлит текущую лицензию.")

    # ---- устройства
    def draw_devices():
        clear(dev)
        if not s.devices:
            tk.Label(dev, text="Список устройств загрузится при подключении к серверу.",
                     bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9), wraplength=300,
                     justify="left").pack(anchor="w")
            return
        from ..account import device
        me_name = device.device_name()
        for d in s.devices:
            row = tk.Frame(dev, bg=p["surface"])
            row.pack(fill=tk.X, pady=3)
            cur = d["name"] == me_name
            tk.Label(row, text=d["name"] + ("  · это устройство" if cur else ""), bg=p["surface"],
                     fg=p["text"] if cur else p["text_dim"], font=("Segoe UI", 10)).pack(side=tk.LEFT)
            tk.Label(row, text=f"был {_date(d.get('last_seen'))}", bg=p["surface"],
                     fg=p["text_faint"], font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(8, 0))
            if not cur:
                _link_btn(row, p, "Отключить", lambda i=d["id"]: remove_device(i), danger=True).pack(side=tk.RIGHT)

    def remove_device(dev_id):
        def go():
            try:
                s.api.remove_device(dev_id)
                refresh()
            except (ApiError, NetworkError) as e:
                app.set_status(str(e))
        dialogs.confirm(app, "Отключить устройство?",
                        "Программа на нём перестанет запускаться, пока вы не войдёте снова.", go,
                        danger=True, ok_text="Отключить")

    # ---- безопасность
    def draw_security():
        clear(sec)
        tk.Label(sec, text="Сменить пароль или выйти из аккаунта на этом компьютере.",
                 bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9), wraplength=300,
                 justify="left").pack(anchor="w", pady=(0, 10))
        row = tk.Frame(sec, bg=p["surface"])
        row.pack(anchor="w")
        _link_btn(row, p, "Сменить пароль", change_password).pack(side=tk.LEFT)
        _link_btn(row, p, "Выйти", logout).pack(side=tk.LEFT, padx=(8, 0))

    def change_password():
        def submit(v):
            if len(v["new"]) < 8:
                return "Новый пароль — минимум 8 символов"
            if v["new"] != v["new2"]:
                return "Пароли не совпадают"
            try:
                s.api.change_password(v["old"], v["new"])
            except ApiError as e:
                return e.message
            except NetworkError:
                return "Нет связи с сервером"
            app.toasts.show("Пароль изменён", kind="success")
        dialogs.ask(app, "Смена пароля", [("old", "Текущий пароль", "", True),
                                          ("new", "Новый пароль", "", True),
                                          ("new2", "Повторите новый пароль", "", True)], submit)

    def logout():
        def go():
            gate.logout(s)
            restart_app(app)
        dialogs.confirm(app, "Выйти из аккаунта?",
                        "Программа перезапустится и попросит войти снова.", go, ok_text="Выйти")

    # ---- приватность
    def draw_privacy():
        clear(prv)
        row = tk.Frame(prv, bg=p["surface"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Статистика использования", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)
        var = tk.StringVar(value="on" if s.usage_stats else "off")
        SegmentedControl(row, p, [("on", "Вкл"), ("off", "Выкл")], variable=var).pack(side=tk.RIGHT)

        def changed(*_):
            on = var.get() == "on"
            s.info["user"]["usage_stats"] = on
            try:
                s.api.set_usage_stats(on)
            except (ApiError, NetworkError):
                app.set_status("Не удалось сохранить настройку — нет связи")
        var.trace_add("write", changed)
        tk.Label(prv, text="Вход, запуск/выход и ошибки отправляются всегда — они нужны для "
                           "работы лицензии. Содержимое фото не собирается никогда.",
                 bg=p["surface"], fg=p["text_faint"], font=("Segoe UI", 8), wraplength=320,
                 justify="left").pack(anchor="w", pady=(8, 10))
        row2 = tk.Frame(prv, bg=p["surface"])
        row2.pack(anchor="w")
        _link_btn(row2, p, "Что собирается", lambda: dialogs.show_text(
            app, legal.PRIVACY_TITLE, legal.PRIVACY_TEXT)).pack(side=tk.LEFT)
        _link_btn(row2, p, "Удалить аккаунт", delete_account, danger=True).pack(side=tk.LEFT, padx=(8, 0))

    def delete_account():
        def submit(v):
            try:
                s.api.delete_account(v["pw"])
            except ApiError as e:
                return e.message
            except NetworkError:
                return "Нет связи с сервером"
            gate.logout(s)
            restart_app(app)
        dialogs.ask(app, "Удалить аккаунт?", [("pw", "Пароль для подтверждения", "", True)], submit,
                    ok_text="Удалить навсегда", ok_icon="delete",
                    text="Аккаунт и все связанные с ним данные на сервере будут удалены без "
                         "возможности восстановления. Лицензия сгорит.")

    # ---- новости
    def draw_news(items):
        clear(news)
        if not items:
            tk.Label(news, text="Пока новостей нет.", bg=p["surface"], fg=p["text_dim"],
                     font=("Segoe UI", 10)).pack(anchor="w")
            return
        for it in items[:6]:
            col = {"warn": icons.NEON["orange"], "success": icons.NEON["lime"]}.get(
                it.get("level"), icons.NEON["cyan"])
            row = tk.Frame(news, bg=p["surface"])
            row.pack(fill=tk.X, pady=5)
            tk.Frame(row, bg=col, width=3).pack(side=tk.LEFT, fill=tk.Y)
            col_f = tk.Frame(row, bg=p["surface"])
            col_f.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X)
            tk.Label(col_f, text=f"{it['title']}   {_date(it['ts'])}", bg=p["surface"], fg=p["text"],
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X)
            if it.get("body"):
                tk.Label(col_f, text=it["body"], bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9),
                         justify="left", wraplength=760, anchor="w").pack(fill=tk.X)

    def draw_all():
        draw_license(); draw_devices(); draw_security(); draw_privacy()

    def refresh():
        if s.offline:
            draw_all()
            draw_news([])
            return

        def work():
            me = s.api.me()
            try:
                items = s.api.announcements()
            except (ApiError, NetworkError):
                items = []
            return me, items

        def done(res):
            me, items = res
            s.apply(me)
            try:
                draw_all()
                draw_news(items)
            except tk.TclError:
                pass

        app.run_task(work, done, lambda e: (draw_all(), draw_news([])))

    draw_all()
    draw_news([])
    root.refresh = refresh
    root.after(50, refresh)
    return root
