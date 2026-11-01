"""«Библиотека» — наборы шаблонов оформления, которые автор программы публикует
на сервере. Вместо облачного хранилища: ничего пользовательского на сервер не
отправляется, только скачиваются готовые наборы."""
import colorsys
import hashlib
import tkinter as tk

from .. import anim, icons
from ..account import library as lib
from ..account.api import ApiError, NetworkError
from ..config import LAYOUTS
from ..ui_widgets import (GradientButton, _blend_hex, enable_mousewheel,
                          rounded_rect)


def _plural(n, forms):
    """1 шаблон · 2 шаблона · 5 шаблонов."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def _hue_for(pack_id):
    h = int(hashlib.md5(pack_id.encode()).hexdigest()[:4], 16) / 65535.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.55, 1.0)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


class _PackCard(tk.Canvas):
    W, H = 300, 196

    def __init__(self, parent, p, item, state, on_install, index=0):
        super().__init__(parent, width=self.W, height=self.H, bg=p["bg"], highlightthickness=0)
        self.p, self.item, self.state = p, item, state     # state: new | installed | update | busy
        self.on_install = on_install
        self.hue = _hue_for(item["id"])
        self._hv, self._rv = 0.0, 0.0
        self.bind("<Enter>", lambda e: anim.tween_attr(self, "_hv", 1.0, 160, redraw=self._redraw))
        self.bind("<Leave>", lambda e: anim.tween_attr(self, "_hv", 0.0, 220, redraw=self._redraw))
        self.bind("<Motion>", lambda e: self.configure(cursor="hand2" if self._btn(e.x, e.y) else ""))
        self.bind("<Button-1>", self._click)
        self.bind("<Destroy>", self._on_destroy, add="+")
        anim.get(self).animate(420, self._reveal, delay_ms=70 * index, key=(id(self), "rv"))

    def _reveal(self, t):
        self._rv = t
        self._redraw()

    def _btn(self, x, y):
        return self.state in ("new", "update") and 16 <= x <= 16 + 130 and 150 <= y <= 184

    def _click(self, e):
        if self._btn(e.x, e.y):
            self.on_install(self.item)

    def set_state(self, state):
        self.state = state
        self._redraw()

    def _on_destroy(self, event):
        if event.widget is self:
            a = anim.get(self)
            a.cancel((id(self), "rv"))
            a.cancel((id(self), "_hv"))

    def _redraw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        p, W, H, hv, rv = self.p, self.W, self.H, self._hv, self._rv
        dy = (1 - rv) * 18 - 4 * hv
        fade = lambda c: _blend_hex(c, p["bg"], rv)
        rounded_rect(self, 3, 6 + dy, W - 3, H - 3 + dy, radius=16,
                     fill=fade(_blend_hex(p["surface_hi"], p["surface"], hv)),
                     outline=fade(_blend_hex(self.hue, p["border"], 0.5 * hv)), width=1 + int(hv))
        # «обложка»: цветная плашка с неоновой иконкой
        rounded_rect(self, 16, 18 + dy, W - 16, 74 + dy, radius=10,
                     fill=fade(_blend_hex(self.hue, p["surface"], 0.20 + 0.12 * hv)), outline="")
        icons.draw_neon(self, "template", 44, 46 + dy, size=26, color=self.hue,
                        glow=round((0.6 + 0.4 * hv) * 4) / 4)
        it = self.item
        self.create_text(78, 36 + dy, text=it["name"][:26], anchor="w", fill=fade(p["text"]),
                         font=("Segoe UI", 12, "bold"))
        n = it.get("count", 0)
        meta = f"{n} {_plural(n, ('шаблон', 'шаблона', 'шаблонов'))} · v{it.get('version', '1')}"
        if it.get("author"):
            meta += f" · {it['author']}"
        self.create_text(78, 58 + dy, text=meta[:42], anchor="w", fill=fade(p["text_dim"]),
                         font=("Segoe UI", 9))
        self.create_text(18, 98 + dy, text=(it.get("description") or "Набор шаблонов оформления")[:90],
                         anchor="nw", width=W - 36, fill=fade(p["text_dim"]), font=("Segoe UI", 9))
        # кнопка
        labels = {"new": "Установить", "update": "Обновить", "busy": "Установка…",
                  "installed": "Установлено"}
        txt = labels[self.state]
        if self.state in ("new", "update"):
            rounded_rect(self, 16, 150 + dy, 146, 184 + dy, radius=9,
                         fill=fade(p["accent_hi"] if hv > 0.5 else p["accent"]), outline="")
            self.create_text(81, 167 + dy, text=txt, fill=fade("#ffffff"), font=("Segoe UI", 10, "bold"))
        else:
            ok = self.state == "installed"
            icons.draw(self, "check" if ok else "refresh", 28, 167 + dy, size=16,
                       color=fade(icons.NEON["lime"] if ok else p["text_dim"]))
            self.create_text(44, 167 + dy, text=txt, anchor="w",
                             fill=fade(icons.NEON["lime"] if ok else p["text_dim"]),
                             font=("Segoe UI", 10, "bold"))


def build_library_view(parent, app):
    p = app.palette
    s = app.session
    root = tk.Frame(parent, bg=p["bg"])

    head = tk.Frame(root, bg=p["bg"])
    head.pack(fill=tk.X, padx=8, pady=(6, 12))
    ic = tk.Canvas(head, width=52, height=52, bg=p["bg"], highlightthickness=0)
    ic.pack(side=tk.LEFT)
    icons.draw_neon(ic, "book", 26, 26, size=28, color=icons.NEON["blue"])
    box = tk.Frame(head, bg=p["bg"])
    box.pack(side=tk.LEFT, padx=(10, 0))
    tk.Label(box, text="Библиотека", bg=p["bg"], fg=p["text"], font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(box, text="Наборы шаблонов оформления — устанавливаются в один клик",
             bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 10)).pack(anchor="w")

    if s is None or s.offline:
        card = tk.Frame(root, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
        card.pack(expand=True)
        msg = ("Библиотека доступна после входа в аккаунт." if s is None else
               "Без сети библиотека недоступна. Подключитесь к интернету и перезапустите программу.")
        tk.Label(card, text=msg, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 11),
                 wraplength=420, justify="center").pack(padx=50, pady=40)
        return root

    status = tk.Label(root, text="Загружаем список…", bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 10))
    status.pack(anchor="w", padx=10)
    canvas = tk.Canvas(root, bg=p["bg"], highlightthickness=0)
    inner = tk.Frame(canvas, bg=p["bg"])
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.pack(fill=tk.BOTH, expand=True)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    enable_mousewheel(canvas)
    cards = []

    def reflow(_e=None):
        width = max(canvas.winfo_width(), 1)
        cols = max(1, (width - 16) // (_PackCard.W + 16))
        for i, c in enumerate(cards):
            c.grid(row=i // cols, column=i % cols, padx=8, pady=8)

    canvas.bind("<Configure>", lambda e: (canvas.itemconfigure(win, width=e.width), reflow()))

    def installed():
        return app.config.get("installed_packs", {}) or {}

    def state_for(item):
        v = installed().get(item["id"])
        if v is None:
            return "new"
        return "installed" if v == item.get("version") else "update"

    def install(item, card):
        card.set_state("busy")

        def work():
            data, headers = s.api.library_download(item["id"])
            from ..screens.templates import _load_user_templates, _save_user_templates
            added, merged = lib.install(data, item.get("sha256"), _load_user_templates(),
                                        LAYOUTS, item["name"])
            return added, merged

        def done(res):
            added, merged = res
            from ..screens.templates import _save_user_templates
            _save_user_templates(merged)
            inst = dict(installed())
            inst[item["id"]] = item.get("version")
            app.config["installed_packs"] = inst
            app.config.save()
            card.set_state("installed")
            app.track("library_install", pack=item["id"], n=added)
            app.toasts.show(f"«{item['name']}»: добавлено шаблонов — {added}", kind="success")
            tv = app.views.pop("templates", None)       # раздел «Шаблоны» перестроится
            if tv is not None:
                tv.destroy()

        def fail(e):
            card.set_state(state_for(item))
            msg = e.message if isinstance(e, ApiError) else (
                "Нет связи с сервером" if isinstance(e, NetworkError) else str(e))
            app.toasts.show(msg, kind="error")

        app.run_task(work, done, fail)

    def refresh():
        def work():
            return s.api.library()

        def done(items):
            for c in cards:
                c.destroy()
            cards.clear()
            for i, it in enumerate(items):
                card = _PackCard(inner, p, it, state_for(it), lambda item, c=None: None, index=i)
                card.on_install = lambda item, card=card: install(item, card)
                cards.append(card)
            status.configure(text="" if items else
                             "Пока в библиотеке пусто — новые наборы появятся здесь.")
            reflow()

        app.run_task(work, done, lambda e: status.configure(
            text=(e.message if isinstance(e, ApiError) else "Не удалось загрузить список")))

    root.refresh = refresh
    root.after(50, refresh)
    return root
