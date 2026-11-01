"""Админка внутри программы (видна только администратору).

Вкладки: Обзор · Пользователи · Ключи · Логи · Библиотека · Новости · Сервер.
Все данные берутся с сервера; действия записываются там же в журнал аудита.
"""
import time
import tkinter as tk
from tkinter import filedialog, ttk

from .. import icons
from ..account import library as lib
from ..account.api import ApiError, NetworkError
from ..ui_widgets import SegmentedControl, _blend_hex, enable_mousewheel, rounded_rect
from . import dialogs

EVENT_TYPES = ["", "app_start", "app_exit", "login", "register", "key_activated", "error",
               "export_save", "export_copy", "template_apply", "library_install",
               "batch_run", "editor_open", "pdf_export", "watermark_apply", "caption_style"]
EVENT_NAMES = {"app_start": "запуск", "app_exit": "выход", "login": "вход", "register": "регистрация",
               "key_activated": "активация ключа", "error": "ошибка", "export_save": "сохранение",
               "export_copy": "копирование", "template_apply": "шаблон", "library_install": "из библиотеки",
               "batch_run": "пакетная", "editor_open": "редактор", "pdf_export": "PDF",
               "watermark_apply": "водяной знак", "caption_style": "подписи"}
LIC_NAMES = {"active": "активна", "expired": "истекла", "revoked": "отозвана", "none": "нет"}


def _ts(ts, fmt="%d.%m.%Y %H:%M"):
    return time.strftime(fmt, time.localtime(ts)) if ts else "—"


def _btn(parent, p, text, cmd, danger=False, primary=False):
    fg = "#ff5470" if danger else ("#ffffff" if primary else p["text"])
    return tk.Button(parent, text=text, command=cmd, bd=0, relief="flat", cursor="hand2",
                     bg=p["accent"] if primary else p["surface_alt"], fg=fg,
                     activebackground=p["accent_hi"] if primary else p["surface_hi"],
                     activeforeground="#ffffff" if primary else fg, font=("Segoe UI", 9),
                     padx=12, pady=7, highlightthickness=0, takefocus=0)


def _entry(parent, p, width=16, var=None):
    return tk.Entry(parent, textvariable=var, width=width, bg=p["surface_alt"], fg=p["text"],
                    insertbackground=p["accent_hi"], relief="flat", bd=0, font=("Segoe UI", 10),
                    highlightthickness=1, highlightbackground=p["border"],
                    highlightcolor=p["accent"])


class _Table(tk.Frame):
    def __init__(self, parent, p, columns, widths, height=12):
        super().__init__(parent, bg=p["bg"])
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings",
                                 height=height, selectmode="browse")
        for (key, title), w in zip(columns, widths):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=w, anchor="w", stretch=(w >= 120))
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.rows = {}

    def set(self, rows):
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for key, values, data in rows:
            iid = self.tree.insert("", "end", values=values)
            self.rows[iid] = data
        return self

    def selected(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None


def build_admin_view(parent, app):
    p = app.palette
    s = app.session
    root = tk.Frame(parent, bg=p["bg"])
    if s is None or not s.is_admin:
        tk.Label(root, text="Раздел доступен только администратору", bg=p["bg"], fg=p["text_dim"],
                 font=("Segoe UI", 12)).pack(expand=True)
        return root
    api = s.api

    def call(method, path, data=None, query=None, raw=None, done=None, toast=None):
        def work():
            return api.admin(method, path, data=data, query=query, raw=raw)

        def ok(res):
            if toast:
                app.toasts.show(toast, kind="success")
            if done:
                done(res)

        def fail(e):
            msg = e.message if isinstance(e, ApiError) else (
                "Нет связи с сервером" if isinstance(e, NetworkError) else str(e))
            app.toasts.show(msg, kind="error")
        app.run_task(work, ok, fail)

    # ------------------------------------------------------------ шапка
    head = tk.Frame(root, bg=p["bg"])
    head.pack(fill=tk.X, padx=8, pady=(6, 10))
    ic = tk.Canvas(head, width=52, height=52, bg=p["bg"], highlightthickness=0)
    ic.pack(side=tk.LEFT)
    icons.draw_neon(ic, "shield", 26, 26, size=28, color=icons.NEON["red"])
    box = tk.Frame(head, bg=p["bg"])
    box.pack(side=tk.LEFT, padx=(10, 0))
    tk.Label(box, text="Админка", bg=p["bg"], fg=p["text"], font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(box, text="Пользователи, ключи, журналы и настройки сервера", bg=p["bg"],
             fg=p["text_dim"], font=("Segoe UI", 10)).pack(anchor="w")

    tab_var = tk.StringVar(value="overview")
    tabs = SegmentedControl(root, {**p, "surface": p["bg"]},
                            [("overview", "Обзор"), ("users", "Пользователи"), ("keys", "Ключи"),
                             ("logs", "Логи"), ("library", "Библиотека"), ("news", "Новости"),
                             ("server", "Сервер")], variable=tab_var, padx=14, pady=6)
    tabs.pack(anchor="w", padx=8, pady=(0, 10))
    holder = tk.Frame(root, bg=p["bg"])
    holder.pack(fill=tk.BOTH, expand=True, padx=8)
    pages = {}

    # ============================================================ ОБЗОР
    def page_overview(f):
        grid = tk.Frame(f, bg=p["bg"])
        grid.pack(fill=tk.X)
        cards = {}
        spec = [("users", "Пользователей", "users", "violet"), ("active_licenses", "Активных лицензий", "key", "pink"),
                ("expiring_7d", "Истекают за 7 дней", "alert", "orange"), ("online_24h", "Были за 24 ч", "user", "cyan"),
                ("keys_unused", "Свободных ключей", "key", "lime"), ("devices", "Устройств", "server", "blue"),
                ("events_24h", "Событий за 24 ч", "chart", "violet"), ("failed_logins_24h", "Неудачных входов", "ban", "red")]
        for i, (k, title, kind, hue) in enumerate(spec):
            c = tk.Frame(grid, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
            c.grid(row=i // 4, column=i % 4, padx=6, pady=6, sticky="nsew")
            grid.columnconfigure(i % 4, weight=1, uniform="s")
            cv = tk.Canvas(c, width=44, height=44, bg=p["surface"], highlightthickness=0)
            cv.pack(side=tk.LEFT, padx=(10, 0), pady=10)
            icons.draw_neon(cv, kind, 22, 22, size=20, color=icons.NEON[hue], glow=0.75)
            col = tk.Frame(c, bg=p["surface"])
            col.pack(side=tk.LEFT, padx=(2, 12))
            num = tk.Label(col, text="—", bg=p["surface"], fg=p["text"], font=("Segoe UI", 18, "bold"))
            num.pack(anchor="w")
            tk.Label(col, text=title, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9)).pack(anchor="w")
            cards[k] = num
        chart = tk.Canvas(f, height=190, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
        chart.pack(fill=tk.X, padx=6, pady=(10, 6))
        top = tk.Label(f, text="", bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 9), justify="left", anchor="w")
        top.pack(fill=tk.X, padx=8)

        def draw(ov):
            for k, lab in cards.items():
                lab.configure(text=str(ov.get(k, "—")))
            chart.delete("all")
            series = ov["series"]
            w, h = max(chart.winfo_width(), 700), 190
            mx = max([d["events"] for d in series] + [1])
            bw = (w - 60) / len(series)
            chart.create_text(14, 14, text="События и входы за 14 дней", anchor="w", fill=p["text"],
                              font=("Segoe UI", 10, "bold"))
            for i, d in enumerate(series):
                x = 30 + i * bw
                for val, col, off in ((d["events"], icons.NEON["violet"], 0), (d["logins"], icons.NEON["cyan"], bw * 0.42)):
                    bh = (h - 70) * (val / mx)
                    rounded_rect(chart, x + off, h - 28 - bh, x + off + bw * 0.38, h - 28, radius=3,
                                 fill=_blend_hex(col, p["surface"], 0.9), outline="")
                chart.create_text(x + bw * 0.4, h - 14, text=_ts(d["day"], "%d.%m"), fill=p["text_faint"],
                                  font=("Segoe UI", 8))
            tops = ", ".join(f"{EVENT_NAMES.get(t['type'], t['type'])}: {t['c']}" for t in ov["top_events"])
            top.configure(text="Популярные события за неделю — " + (tops or "пока нет данных"))

        f.refresh = lambda: call("GET", "/overview", done=draw)
        return f

    # ============================================================ ПОЛЬЗОВАТЕЛИ
    def page_users(f):
        bar = tk.Frame(f, bg=p["bg"])
        bar.pack(fill=tk.X, pady=(0, 8))
        q = tk.StringVar()
        e = _entry(bar, p, 26, q)
        e.pack(side=tk.LEFT, ipady=5)
        e.bind("<Return>", lambda ev: f.refresh())
        _btn(bar, p, "Найти", lambda: f.refresh()).pack(side=tk.LEFT, padx=(8, 0))
        table = _Table(f, p, [("u", "Логин"), ("r", "Роль"), ("l", "Лицензия"), ("e", "До"), ("d", "Устр."),
                              ("ll", "Последний вход"), ("n", "Заметка")], [150, 80, 100, 100, 60, 130, 200])
        table.pack(fill=tk.BOTH, expand=True)
        acts = tk.Frame(f, bg=p["bg"])
        acts.pack(fill=tk.X, pady=(8, 0))

        def sel():
            u = table.selected()
            if not u:
                app.set_status("Сначала выберите пользователя в таблице")
            return u

        def act(action, data=None, toast="Готово", after=None):
            u = sel()
            if u:
                call("POST", f"/users/{u['id']}/{action}", data or {}, toast=toast,
                     done=after or (lambda r: f.refresh()))

        def ban():
            u = sel()
            if not u:
                return
            if u["banned"]:
                return act("unban", toast="Разблокирован")
            dialogs.ask(app, "Блокировка", [("reason", "Причина (необязательно)", "", False)],
                        lambda v: act("ban", {"reason": v["reason"]}, "Заблокирован"), ok_text="Заблокировать")

        def extend():
            def go(v):
                try:
                    d = int(v["days"])
                except ValueError:
                    return "Введите число дней (можно отрицательное)"
                act("extend", {"days": d}, f"Срок изменён на {d} дн.")
            if sel():
                dialogs.ask(app, "Продлить лицензию", [("days", "На сколько дней", "30", False)], go)

        def devices():
            def go(v):
                try:
                    act("set-devices", {"max_devices": int(v["n"])}, "Лимит обновлён")
                except ValueError:
                    return "Введите число"
            if sel():
                dialogs.ask(app, "Лимит устройств", [("n", "От 1 до 50", "1", False)], go)

        def reset_pw():
            u = sel()
            if not u:
                return

            def shown(r):
                dialogs.show_text(app, "Временный пароль", r["new_password"], note=(
                    f"Передайте пароль пользователю {u['username']}: при входе программа попросит "
                    "задать свой."))
            dialogs.confirm(app, "Сбросить пароль?", f"Для {u['username']} будет создан новый "
                            "временный пароль.", lambda: act("reset-password", after=shown))

        def delete():
            u = sel()
            if u:
                dialogs.confirm(app, "Удалить пользователя?", f"{u['username']} и все его данные "
                                "будут удалены безвозвратно.", lambda: act("delete", toast="Удалён"),
                                danger=True, ok_text="Удалить")

        def note():
            u = sel()
            if u:
                dialogs.ask(app, "Заметка", [("n", "Текст", u.get("note", ""), False)],
                            lambda v: act("note", {"note": v["n"]}, "Сохранено"))

        def role():
            u = sel()
            if u:
                new = "user" if u["role"] == "admin" else "admin"
                dialogs.confirm(app, "Сменить роль?", f"{u['username']} станет «{new}».",
                                lambda: act("set-role", {"role": new}, "Роль изменена"))

        for text, cmd, danger in (("Заблокировать / разблокировать", ban, False), ("Продлить…", extend, False),
                                  ("Бессрочно", lambda: act("unlimited", toast="Лицензия бессрочная"), False),
                                  ("Отозвать лицензию", lambda: act("revoke-license", toast="Лицензия отозвана"), False),
                                  ("Лимит устройств…", devices, False),
                                  ("Сбросить устройства", lambda: act("reset-devices", toast="Устройства сброшены"), False),
                                  ("Новый пароль", reset_pw, False), ("Заметка", note, False),
                                  ("Роль", role, False), ("Удалить", delete, True)):
            _btn(acts, p, text, cmd, danger).pack(side=tk.LEFT, padx=(0, 6), pady=2)

        def draw(res):
            rows = []
            for u in res["items"]:
                lic = LIC_NAMES.get(u["license"], u["license"])
                if u["banned"]:
                    lic = "заблокирован"
                rows.append((u["id"], (u["username"], u["role"], lic,
                                       "бессрочно" if (u["expires"] is None and u["license"] == "active") else _ts(u["expires"], "%d.%m.%Y"),
                                       f"{u['devices']}/{u['max_devices']}", _ts(u["last_login"]), u["note"]), u))
            table.set(rows)

        f.refresh = lambda: call("GET", "/users", query={"q": q.get()}, done=draw)
        return f

    # ============================================================ КЛЮЧИ
    def page_keys(f):
        form = tk.Frame(f, bg=p["bg"])
        form.pack(fill=tk.X, pady=(0, 8))
        vars_ = {"count": tk.StringVar(value="1"), "days": tk.StringVar(value="30"),
                 "dev": tk.StringVar(value="1"), "plan": tk.StringVar(value="Стандарт"),
                 "note": tk.StringVar()}
        for label, key, w in (("Штук", "count", 5), ("Дней (0 — бессрочно)", "days", 7),
                              ("Устройств", "dev", 5), ("Тариф", "plan", 14), ("Заметка", "note", 18)):
            tk.Label(form, text=label, bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
            _entry(form, p, w, vars_[key]).pack(side=tk.LEFT, ipady=4, padx=(0, 12))

        def issue():
            try:
                body = {"count": int(vars_["count"].get()), "days": int(vars_["days"].get()),
                        "max_devices": int(vars_["dev"].get()), "plan": vars_["plan"].get(),
                        "note": vars_["note"].get()}
            except ValueError:
                return app.set_status("Штуки, дни и устройства — числа")

            def shown(r):
                text = "\n".join(r["keys"])
                dialogs.show_text(app, "Ключи выпущены", text, note="Скопируйте и передайте пользователям. "
                                  "Каждый ключ работает один раз.")
                f.refresh()
            call("POST", "/keys", body, done=shown)
        _btn(form, p, "Выпустить", issue, primary=True).pack(side=tk.LEFT)
        table = _Table(f, p, [("k", "Ключ"), ("pl", "Тариф"), ("d", "Дней"), ("v", "Устр."), ("s", "Статус"),
                              ("u", "Кто активировал"), ("c", "Создан"), ("n", "Заметка")],
                       [170, 100, 60, 60, 110, 130, 120, 160])
        table.pack(fill=tk.BOTH, expand=True)
        acts = tk.Frame(f, bg=p["bg"])
        acts.pack(fill=tk.X, pady=(8, 0))

        def revoke():
            k = table.selected()
            if k:
                dialogs.confirm(app, "Отозвать ключ?", f"{k['key']} перестанет работать.", lambda: call(
                    "POST", f"/keys/{k['key']}/revoke", {}, toast="Ключ отозван", done=lambda r: f.refresh()),
                    danger=True, ok_text="Отозвать")

        def copy():
            k = table.selected()
            if k:
                app.root.clipboard_clear()
                app.root.clipboard_append(k["key"])
                app.set_status("Ключ скопирован")
        _btn(acts, p, "Копировать ключ", copy).pack(side=tk.LEFT, padx=(0, 6))
        _btn(acts, p, "Отозвать", revoke, True).pack(side=tk.LEFT)

        def draw(res):
            rows = []
            for k in res["items"]:
                st = "отозван" if k["revoked"] else ("использован" if k["used_by"] else "свободен")
                rows.append((k["key"], (k["key"], k["plan"], k["days"] or "∞", k["max_devices"], st,
                                        k.get("used_by_name") or "", _ts(k["created_at"], "%d.%m.%Y"), k["note"]), k))
            table.set(rows)
        f.refresh = lambda: call("GET", "/keys", done=draw)
        return f

    # ============================================================ ЛОГИ
    def page_logs(f):
        bar = tk.Frame(f, bg=p["bg"])
        bar.pack(fill=tk.X, pady=(0, 8))
        user = tk.StringVar()
        etype = tk.StringVar()
        tk.Label(bar, text="Пользователь", bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        _entry(bar, p, 16, user).pack(side=tk.LEFT, ipady=4, padx=(0, 12))
        tk.Label(bar, text="Событие", bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        cb = ttk.Combobox(bar, textvariable=etype, values=EVENT_TYPES, width=16, state="readonly")
        cb.pack(side=tk.LEFT, padx=(0, 12))
        state = {"offset": 0}
        info = tk.Label(bar, text="", bg=p["bg"], fg=p["text_faint"], font=("Segoe UI", 9))
        table = _Table(f, p, [("t", "Время"), ("u", "Пользователь"), ("e", "Событие"), ("v", "Версия"), ("d", "Данные")],
                       [140, 140, 130, 90, 400])

        def query():
            return {"user": user.get(), "type": etype.get(), "limit": 100, "offset": state["offset"]}

        def draw(res):
            rows = [(e["id"], (_ts(e["ts"]), e["username"] or "—", EVENT_NAMES.get(e["type"], e["type"]),
                               e["version"], e["data"]), e) for e in res["items"]]
            table.set(rows)
            info.configure(text=f"{state['offset'] + 1 if res['items'] else 0}–{state['offset'] + len(res['items'])} из {res['total']}")
            state["total"] = res["total"]

        def page(delta):
            state["offset"] = max(0, min(state["offset"] + delta, max(0, state.get("total", 0) - 1)))
            f.refresh(keep=True)

        def export():
            path = filedialog.asksaveasfilename(parent=app.root, defaultextension=".csv", initialfile="events.csv",
                                                filetypes=[("CSV", "*.csv")])
            if not path:
                return

            def work():
                data, _ = api.request("GET", "/admin/events.csv", query={k: v for k, v in query().items()
                                                                           if k in ("user", "type")}, want_bytes=True,
                                      timeout=30)
                with open(path, "wb") as fh:
                    fh.write(data)
            app.run_task(work, lambda r: app.toasts.show("CSV сохранён", kind="success"),
                         lambda e: app.toasts.show(str(e), kind="error"))
        _btn(bar, p, "Показать", lambda: (state.update(offset=0), f.refresh(keep=True)), primary=True).pack(side=tk.LEFT)
        _btn(bar, p, "Экспорт CSV", export).pack(side=tk.LEFT, padx=(8, 0))
        info.pack(side=tk.RIGHT)
        _btn(bar, p, "›", lambda: page(100)).pack(side=tk.RIGHT, padx=(4, 8))
        _btn(bar, p, "‹", lambda: page(-100)).pack(side=tk.RIGHT)
        table.pack(fill=tk.BOTH, expand=True)

        def refresh(keep=False):
            if not keep:
                state["offset"] = 0
            call("GET", "/events", query=query(), done=draw)
        f.refresh = refresh
        return f

    # ============================================================ БИБЛИОТЕКА
    def page_library(f):
        table = _Table(f, p, [("n", "Название"), ("i", "ID"), ("c", "Шаблонов"), ("v", "Версия"), ("a", "Автор"),
                              ("d", "Скачиваний"), ("t", "Загружен")], [200, 150, 80, 70, 120, 90, 130])
        acts = tk.Frame(f, bg=p["bg"])
        acts.pack(fill=tk.X, pady=(0, 8))
        table.pack(fill=tk.BOTH, expand=True)

        def upload():
            path = filedialog.askopenfilename(parent=app.root, filetypes=[("Пакет шаблонов", "*.zip")])
            if path:
                with open(path, "rb") as fh:
                    data = fh.read()
                call("POST", "/library", raw=data, toast="Пакет загружен", done=lambda r: f.refresh())

        def from_mine():
            from .templates import _load_user_templates
            mine = _load_user_templates()
            if not mine:
                return app.set_status("Сначала сохраните свои шаблоны в разделе «Шаблоны»")

            def go(v):
                pid = v["id"].strip().lower()
                if not v["name"].strip():
                    return "Введите название"
                data = lib.build_pack(pid, v["name"].strip(), v["desc"], s.username, mine)
                call("POST", "/library", raw=data, toast=f"Опубликовано шаблонов: {len(mine)}",
                     done=lambda r: f.refresh())
            dialogs.ask(app, "Опубликовать мои шаблоны", [("id", "ID (латиница, цифры, - и _)", "my-pack", False),
                                                         ("name", "Название пакета", "", False),
                                                         ("desc", "Описание", "", False)], go,
                        text=f"В пакет войдут все ваши шаблоны ({len(mine)}).", ok_text="Опубликовать", width=460)

        def delete():
            k = table.selected()
            if k:
                dialogs.confirm(app, "Удалить пакет?", f"«{k['name']}» исчезнет из библиотеки у всех.",
                                lambda: call("DELETE", f"/library/{k['id']}", toast="Удалено",
                                             done=lambda r: f.refresh()), danger=True, ok_text="Удалить")
        _btn(acts, p, "Опубликовать мои шаблоны…", from_mine, primary=True).pack(side=tk.LEFT)
        _btn(acts, p, "Загрузить .zip…", upload).pack(side=tk.LEFT, padx=(8, 0))
        _btn(acts, p, "Удалить", delete, True).pack(side=tk.LEFT, padx=(8, 0))

        def draw(res):
            table.set([(i["id"], (i["name"], i["id"], i["count"], i["version"], i["author"], i["downloads"],
                                  _ts(i["created_at"], "%d.%m.%Y")), i) for i in res["items"]])
        def _lib_list(cb):
            app.run_task(lambda: api.library(), lambda items: cb({"items": items}),
                         lambda e: app.toasts.show(str(e), kind="error"))
        f.refresh = lambda: _lib_list(draw)
        return f

    # ============================================================ НОВОСТИ
    def page_news(f):
        form = tk.Frame(f, bg=p["bg"])
        form.pack(fill=tk.X, pady=(0, 8))
        title = tk.StringVar()
        body = tk.StringVar()
        level = tk.StringVar(value="info")
        pinned = tk.BooleanVar(value=False)
        tk.Label(form, text="Заголовок", bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        _entry(form, p, 22, title).pack(side=tk.LEFT, ipady=4, padx=(0, 10))
        tk.Label(form, text="Текст", bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        _entry(form, p, 40, body).pack(side=tk.LEFT, ipady=4, padx=(0, 10))
        SegmentedControl(form, {**p, "surface": p["bg"]}, [("info", "Инфо"), ("warn", "Важно"), ("success", "Радость")],
                         variable=level).pack(side=tk.LEFT, padx=(0, 10))
        tk.Checkbutton(form, text="Закрепить", variable=pinned, bg=p["bg"], fg=p["text"], selectcolor=p["surface_alt"],
                       activebackground=p["bg"], activeforeground=p["text"], highlightthickness=0, bd=0).pack(side=tk.LEFT)

        def publish():
            if not title.get().strip():
                return app.set_status("Нужен заголовок")
            call("POST", "/announcements", {"title": title.get(), "body": body.get(), "level": level.get(),
                                            "pinned": pinned.get()}, toast="Опубликовано",
                 done=lambda r: (title.set(""), body.set(""), f.refresh()))
        _btn(form, p, "Опубликовать", publish, primary=True).pack(side=tk.LEFT, padx=(10, 0))
        table = _Table(f, p, [("t", "Дата"), ("h", "Заголовок"), ("b", "Текст"), ("l", "Уровень"), ("p", "Закреплено")],
                       [110, 220, 420, 90, 90])
        table.pack(fill=tk.BOTH, expand=True)
        acts = tk.Frame(f, bg=p["bg"])
        acts.pack(fill=tk.X, pady=(8, 0))
        _btn(acts, p, "Удалить выбранную", lambda: (lambda a: a and call(
            "DELETE", f"/announcements/{a['id']}", toast="Удалено", done=lambda r: f.refresh()))(table.selected()),
             True).pack(side=tk.LEFT)

        def draw(items):
            table.set([(a["id"], (_ts(a["ts"], "%d.%m.%Y"), a["title"], a["body"], a["level"],
                                  "да" if a["pinned"] else ""), a) for a in items])
        f.refresh = lambda: app.run_task(lambda: api.announcements(), draw,
                                         lambda e: app.toasts.show(str(e), kind="error"))
        return f

    # ============================================================ СЕРВЕР
    def page_server(f):
        form = tk.Frame(f, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
        form.pack(fill=tk.X, pady=(0, 10))
        inner = tk.Frame(form, bg=p["surface"])
        inner.pack(fill=tk.X, padx=16, pady=12)
        sv = {k: tk.StringVar() for k in ("maintenance_text", "min_version", "latest_version", "download_url",
                                          "support_contact", "motd")}
        maint = tk.StringVar(value="off")
        row = tk.Frame(inner, bg=p["surface"])
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text="Технические работы", bg=p["surface"], fg=p["text"], font=("Segoe UI", 10),
                 width=24, anchor="w").pack(side=tk.LEFT)
        SegmentedControl(row, p, [("off", "Выкл"), ("on", "Вкл")], variable=maint).pack(side=tk.LEFT)
        for key, label in (("maintenance_text", "Текст для пользователей"), ("min_version", "Минимальная версия программы"),
                           ("latest_version", "Последняя версия"), ("download_url", "Ссылка на скачивание"),
                           ("support_contact", "Контакт поддержки"), ("motd", "Сообщение на экране входа")):
            r = tk.Frame(inner, bg=p["surface"])
            r.pack(fill=tk.X, pady=3)
            tk.Label(r, text=label, bg=p["surface"], fg=p["text"], font=("Segoe UI", 10), width=24,
                     anchor="w").pack(side=tk.LEFT)
            _entry(r, p, 60, sv[key]).pack(side=tk.LEFT, ipady=4)

        def save():
            body = {k: v.get() for k, v in sv.items()}
            body["maintenance"] = maint.get() == "on"
            call("POST", "/settings", body, toast="Настройки сохранены")
        _btn(inner, p, "Сохранить", save, primary=True).pack(anchor="w", pady=(10, 0))
        tk.Label(f, text="ЖУРНАЛ ДЕЙСТВИЙ АДМИНИСТРАТОРОВ", bg=p["bg"], fg=p["text_faint"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(4, 4))
        audit = _Table(f, p, [("t", "Время"), ("a", "Кто"), ("x", "Действие"), ("g", "Объект"), ("d", "Детали")],
                       [130, 110, 150, 160, 300], height=8)
        audit.pack(fill=tk.BOTH, expand=True)

        def draw_settings(res):
            st = res["settings"]
            for k in sv:
                sv[k].set(st.get(k, ""))
            maint.set("on" if st.get("maintenance") == "1" else "off")

        def refresh():
            call("GET", "/settings", done=draw_settings)
            call("GET", "/audit", done=lambda r: audit.set(
                [(i, (_ts(a["ts"]), a["admin"] or "—", a["action"], a["target"], a["detail"]), a)
                 for i, a in enumerate(r["items"])]))
        f.refresh = refresh
        return f

    builders = {"overview": page_overview, "users": page_users, "keys": page_keys, "logs": page_logs,
                "library": page_library, "news": page_news, "server": page_server}

    def show(*_):
        key = tab_var.get()
        for k, fr in pages.items():
            fr.pack_forget()
        if key not in pages:
            pages[key] = builders[key](tk.Frame(holder, bg=p["bg"]))
        pages[key].pack(fill=tk.BOTH, expand=True)
        pages[key].refresh()

    tab_var.trace_add("write", show)
    root.refresh = lambda: show()
    root.after(50, show)
    return root
