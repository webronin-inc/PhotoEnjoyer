"""Панель шаблонов раскладок."""
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from .. import anim, branding, icons
from ..config import LAYOUTS
from ..ui_widgets import (GradientButton, _blend_hex, enable_mousewheel,
                          rounded_rect)


def _templates_path():
    return Path.home() / f"{branding.APP_CONFIG_DIR}_templates.json"


def _load_user_templates():
    try:
        p = _templates_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_user_templates(data):
    try:
        _templates_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


BUILTIN = [
    {
        "name": "Классика 2×2",
        "desc": "Стандартная сетка",
        "layout": "2×2 — квадрат",
        "mode": "fit",
        "cell_size": 800,
        "border": 10,
        "border_color": "#ffffff",
        "bg_color": "#ffffff",
    },
    {
        "name": "Полароид",
        "desc": "Белые рамки",
        "layout": "2×2 — квадрат",
        "mode": "fill",
        "cell_size": 700,
        "border": 30,
        "border_color": "#ffffff",
        "bg_color": "#f0f0f0",
    },
    {
        "name": "Плёнка",
        "desc": "Четыре кадра в ряд",
        "layout": "4×1 — горизонтальная полоса",
        "mode": "fill",
        "cell_size": 600,
        "border": 6,
        "border_color": "#1a1a1a",
        "bg_color": "#000000",
    },
    {
        "name": "Столбик",
        "desc": "Четыре кадра в столбик",
        "layout": "1×4 — вертикальная полоса",
        "mode": "fit",
        "cell_size": 700,
        "border": 12,
        "border_color": "#ffffff",
        "bg_color": "#fafafa",
    },
    {
        "name": "Ночной",
        "desc": "Тёмный фон",
        "layout": "2×2 — квадрат",
        "mode": "fill",
        "cell_size": 800,
        "border": 8,
        "border_color": "#0f0f17",
        "bg_color": "#0f0f17",
    },
    {
        "name": "Пастель",
        "desc": "Мягкий фон",
        "layout": "2×2 — квадрат",
        "mode": "fit",
        "cell_size": 800,
        "border": 20,
        "border_color": "#f0e6f6",
        "bg_color": "#faf0ff",
    },
]


def build_templates_view(parent, app):
    """Создаёт панель шаблонов и возвращает её корневой фрейм."""
    p = app.palette

    root = tk.Frame(parent, bg=p["bg"])
    root.pack(fill=tk.BOTH, expand=True, padx=(0, 14), pady=(14, 0))

    # Заголовок
    head = tk.Frame(root, bg=p["bg"])
    head.pack(fill=tk.X, padx=8, pady=(6, 14))
    ic = tk.Canvas(head, width=48, height=48, bg=p["bg"], highlightthickness=0)
    ic.pack(side=tk.LEFT)
    icons.draw_neon(ic, "template", 24, 24, size=26, color=icons.NEON["pink"])
    box = tk.Frame(head, bg=p["bg"])
    box.pack(side=tk.LEFT, padx=(10, 0))
    tk.Label(box, text="Шаблоны", bg=p["bg"], fg=p["text"],
             font=("Segoe UI", 18, "bold"), anchor="w").pack(anchor="w")
    tk.Label(box, text="Один клик — раскладка, рамки и цвета применятся сразу",
             bg=p["bg"], fg=p["text_dim"], font=("Segoe UI", 10),
             anchor="w").pack(anchor="w")

    # Кнопка «Сохранить» закреплена внизу
    bottom = tk.Frame(root, bg=p["bg"])
    bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(10, 8))
    GradientButton(bottom, p, text="Сохранить текущее как шаблон", icon="save",
                   height=42, command=lambda: _save_current_as_template(app, root)
                   ).pack(anchor="w")

    # Прокручиваемая область (колесо мыши; без нативного скроллбара)
    canvas = tk.Canvas(root, bg=p["bg"], highlightthickness=0)
    inner = tk.Frame(canvas, bg=p["bg"])
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.pack(fill=tk.BOTH, expand=True)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    enable_mousewheel(canvas)

    cards = []                                  # (frame-сетка, [карточки])

    def build_grid(title, items, empty_text):
        _section_label(inner, title, p)
        grid = tk.Frame(inner, bg=p["bg"])
        grid.pack(fill=tk.X, padx=8, pady=(0, 14))
        if not items:
            tk.Label(grid, text=empty_text, bg=p["bg"], fg=p["text_dim"],
                     font=("Segoe UI", 10), justify="left"
                     ).pack(anchor="w", padx=4, pady=6)
            return
        lst = []
        for i, (tpl, deletable) in enumerate(items):
            kw = {}
            if deletable:
                kw["on_delete"] = lambda n=tpl["name"]: _delete_user_template(
                    app, n, root)
            card = _TemplateCard(grid, p, tpl, on_click=lambda t=tpl: _apply_template(app, t),
                                 index=i, **kw)
            lst.append(card)
        cards.append((grid, lst))

    build_grid("Готовые", [(t, False) for t in BUILTIN], "")
    user = _load_user_templates()
    build_grid("Мои шаблоны",
               [({**t, "name": n}, True) for n, t in user.items()],
               "Пока пусто. Настройте раскладку и нажмите\n"
               "«Сохранить текущее как шаблон» — он появится здесь.")

    def reflow(_e=None):
        width = max(canvas.winfo_width(), 1)
        cols = max(1, (width - 16) // (_TemplateCard.W + 16))
        for grid, lst in cards:
            for i, card in enumerate(lst):
                card.grid(row=i // cols, column=i % cols, padx=8, pady=8)

    canvas.bind("<Configure>",
                lambda e: (canvas.itemconfigure(win, width=e.width), reflow()))
    root.after(30, reflow)
    return root


# ==============================================================
def _section_label(parent, text, p):
    tk.Label(parent, text=text.upper(),
             bg=p["bg"], fg=p["text_faint"],
             font=("Segoe UI", 9, "bold"),
             anchor="w").pack(fill=tk.X, padx=8, pady=(8, 4))


_CELL_HUES = ("violet", "cyan", "pink", "lime", "orange", "blue", "red", "white")


class _TemplateCard(tk.Canvas):
    """Карточка шаблона: миниатюра в цветах шаблона, всплытие при наведении,
    плавное появление (каскадом)."""
    W, H = 228, 160

    def __init__(self, parent, p, tpl, on_click, on_delete=None, index=0):
        super().__init__(parent, width=self.W, height=self.H, bg=p["bg"],
                         highlightthickness=0, cursor="hand2")
        self.p = p
        self.tpl = tpl
        self._on_click = on_click
        self._on_delete = on_delete
        self._hv = 0.0               # наведение 0..1
        self._rv = 0.0               # появление 0..1
        self._del_hot = False
        cols, rows = LAYOUTS.get(tpl.get("layout", ""), (2, 2))
        self._cols, self._rows = cols, rows

        self.bind("<Enter>", lambda e: anim.tween_attr(self, "_hv", 1.0, 160))
        self.bind("<Leave>", lambda e: (self._set_del(False),
                                        anim.tween_attr(self, "_hv", 0.0, 220)))
        self.bind("<Motion>", self._motion)
        self.bind("<Button-1>", self._click)
        self.bind("<Destroy>", self._on_destroy, add="+")

        def reveal(t):
            self._rv = t
            self._redraw()

        anim.get(self).animate(420, reveal, delay_ms=70 * index,
                               key=(id(self), "reveal"))

    # ---- события
    def _set_del(self, v):
        if v != self._del_hot:
            self._del_hot = v
            self._redraw()

    def _in_delete(self, x, y):
        return bool(self._on_delete) and x > self.W - 40 and y < 40

    def _motion(self, e):
        self._set_del(self._in_delete(e.x, e.y))

    def _click(self, e):
        if self._in_delete(e.x, e.y):
            self._on_delete()
        else:
            self._on_click()

    def _on_destroy(self, event):
        if event.widget is self:
            an = anim.get(self)
            an.cancel((id(self), "reveal"))
            an.cancel((id(self), "_hv"))

    # ---- рисование
    def _redraw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        p, W, H = self.p, self.W, self.H
        hv, rv = self._hv, self._rv
        rise = (1 - rv) * 18                  # «выезжает» снизу
        lift = -4 * hv                        # приподнимается при наведении
        dy = rise + lift
        fade = lambda c: _blend_hex(c, p["bg"], rv)

        card_fill = _blend_hex(p["surface_hi"], p["surface"], hv)
        border = _blend_hex(p["accent"], p["border"], hv)
        rounded_rect(self, 3, 6 + dy, W - 3, H - 3 + dy, radius=16,
                     fill=fade(card_fill), outline=fade(border),
                     width=1 + int(hv * 1.2))

        # миниатюра: фон и рамка шаблона, ячейки — неоновые оттенки
        bg = self.tpl.get("bg_color") or "#ffffff"
        px0, py0, px1, py1 = 16, 18 + dy, W - 16, 92 + dy
        rounded_rect(self, px0, py0, px1, py1, radius=9, fill=fade(bg), outline="")
        gap = 3 + min(7, int(self.tpl.get("border", 10)) // 4)
        cw = (px1 - px0 - gap * (self._cols + 1)) / self._cols
        ch = (py1 - py0 - gap * (self._rows + 1)) / self._rows
        k = 0
        for r in range(self._rows):
            for c in range(self._cols):
                x0 = px0 + gap + c * (cw + gap)
                y0 = py0 + gap + r * (ch + gap)
                hue = icons.NEON[_CELL_HUES[k % len(_CELL_HUES)]]
                k += 1
                col = _blend_hex(hue, bg, 0.55 + 0.30 * hv)
                rounded_rect(self, x0, y0, x0 + cw, y0 + ch, radius=3,
                             fill=fade(col), outline="")

        name = self.tpl.get("name", "Шаблон")
        desc = self.tpl.get("desc") or (
            f"{self.tpl.get('cell_size', 800)} px · рамка {self.tpl.get('border', 10)}")
        self.create_text(18, 112 + dy, text=name, anchor="w",
                         fill=fade(p["text"]), font=("Segoe UI", 11, "bold"))
        self.create_text(18, 134 + dy, text=desc, anchor="w",
                         fill=fade(p["text_dim"]), font=("Segoe UI", 9))
        if self._on_delete and hv > 0.05:
            col = p["danger"] if self._del_hot else p["text_faint"]
            icons.draw(self, "close", W - 26, 30 + dy, size=14, color=fade(col))


def _apply_template(app, tpl):
    try:
        from ..config import LAYOUTS
        layout = tpl.get("layout", app.config["layout"])
        if layout in LAYOUTS:
            app.config["layout"] = layout
        app.config["mode"] = tpl.get("mode", app.config["mode"])
        app.config["cell_size"] = int(tpl.get("cell_size",
                                              app.config["cell_size"]))
        app.config["border"] = int(tpl.get("border", app.config["border"]))
        app.config["border_color"] = tpl.get("border_color",
                                             app.config["border_color"])
        app.config["bg_color"] = tpl.get("bg_color", app.config["bg_color"])

        # единая синхронизация (см. App._sync_vars_from_config)
        app._sync_vars_from_config()
        app.set_status(f"Шаблон применён: {tpl.get('name', '')}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось применить шаблон:\n{e}")


def _save_current_as_template(app, view_root):
    name = simpledialog.askstring(
        "Сохранить шаблон",
        "Название шаблона:",
        parent=app.root,
    )
    if not name:
        return
    name = name.strip()
    if not name:
        return

    tpl = {
        "desc": f"{app.config['cell_size']}px · рамка {app.config['border']}",
        "layout": app.config["layout"],
        "mode": app.config["mode"],
        "cell_size": app.config["cell_size"],
        "border": app.config["border"],
        "border_color": app.config["border_color"],
        "bg_color": app.config["bg_color"],
    }
    user = _load_user_templates()
    user[name] = tpl
    _save_user_templates(user)

    messagebox.showinfo("Готово", f"Шаблон «{name}» сохранён.")

    # Пересоздать панель — простое решение
    app.set_status(f"Шаблон «{name}» сохранён")
    # Форсим перезагрузку templates view
    if "templates" in app.views:
        app.views["templates"].destroy()
        del app.views["templates"]
    app._set_section("templates")


def _delete_user_template(app, name, view_root):
    if not messagebox.askyesno("Удалить шаблон",
                               f"Удалить шаблон «{name}»?"):
        return
    user = _load_user_templates()
    user.pop(name, None)
    _save_user_templates(user)

    if "templates" in app.views:
        app.views["templates"].destroy()
        del app.views["templates"]
    app._set_section("templates")