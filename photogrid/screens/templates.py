"""Панель шаблонов раскладок."""
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from .. import branding


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
        "name": "Плёнка 1×4",
        "desc": "Горизонтальная лента",
        "layout": "4×1 — горизонтальная полоса",
        "mode": "fill",
        "cell_size": 600,
        "border": 6,
        "border_color": "#1a1a1a",
        "bg_color": "#000000",
    },
    {
        "name": "Столбик 4×1",
        "desc": "Вертикальная лента",
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
    head.pack(fill=tk.X, padx=8, pady=(6, 16))
    tk.Label(head, text="Шаблоны раскладок",
             bg=p["bg"], fg=p["text"],
             font=("Segoe UI", 16, "bold"),
             anchor="w").pack(side=tk.LEFT)
    tk.Label(head, text="Клик — применить раскладку",
             bg=p["bg"], fg=p["text_dim"],
             font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(16, 0))

    # Скроллируемая область
    outer = tk.Frame(root, bg=p["bg"])
    outer.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(outer, bg=p["bg"], highlightthickness=0)
    scroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=p["bg"])

    inner.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # Секция "Готовые"
    _section_label(inner, "Готовые", p)
    grid_builtin = tk.Frame(inner, bg=p["bg"])
    grid_builtin.pack(fill=tk.X, padx=8, pady=(0, 16))

    for i, tpl in enumerate(BUILTIN):
        card = _TemplateCard(grid_builtin, p, tpl, app,
                             on_click=lambda t=tpl: _apply_template(app, t))
        card.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")

    # Секция "Мои"
    _section_label(inner, "Мои шаблоны", p)
    grid_user = tk.Frame(inner, bg=p["bg"])
    grid_user.pack(fill=tk.X, padx=8, pady=(0, 16))

    user = _load_user_templates()
    if not user:
        tk.Label(grid_user,
                 text="Пока нет сохранённых шаблонов.\n"
                      "Настройте раскладку и нажмите «Сохранить как шаблон».",
                 bg=p["bg"], fg=p["text_dim"],
                 font=("Segoe UI", 10), justify="left"
                 ).pack(anchor="w", padx=4, pady=8)
    else:
        for i, (name, tpl) in enumerate(user.items()):
            card = _TemplateCard(grid_user, p, {**tpl, "name": name},
                                 app, on_click=lambda t=tpl: _apply_template(app, t),
                                 on_delete=lambda n=name: _delete_user_template(app, n, root))
            card.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")

    # Кнопка "Сохранить текущие как шаблон"
    bottom = tk.Frame(root, bg=p["bg"])
    bottom.pack(fill=tk.X, padx=8, pady=(12, 6))

    tk.Button(
        bottom,
        text="  Сохранить текущие как шаблон",
        bg=p["accent"], fg="#ffffff",
        activebackground=p["accent_hi"], activeforeground="#ffffff",
        bd=0, relief="flat", cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        padx=18, pady=10,
        command=lambda: _save_current_as_template(app, root),
    ).pack(anchor="w")

    return root


# ==============================================================
def _section_label(parent, text, p):
    tk.Label(parent, text=text.upper(),
             bg=p["bg"], fg=p["text_faint"],
             font=("Segoe UI", 9, "bold"),
             anchor="w").pack(fill=tk.X, padx=8, pady=(8, 4))


class _TemplateCard(tk.Frame):
    def __init__(self, parent, p, tpl, app, on_click, on_delete=None):
        super().__init__(parent, bg=p["surface"],
                         highlightthickness=1,
                         highlightbackground=p["border"])
        self.p = p
        self.tpl = tpl
        self._on_click = on_click
        self._on_delete = on_delete
        self._hover = False

        self.configure(width=220, height=140)
        self.pack_propagate(False)
        self.grid_propagate(False)

        # Иконка раскладки на Canvas
        preview = tk.Canvas(self, width=200, height=70,
                            bg=p["surface"], highlightthickness=0)
        preview.pack(pady=(10, 6))
        self._draw_layout_preview(preview, tpl.get("layout", ""))

        # Название
        tk.Label(self, text=tpl.get("name", "Шаблон"),
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill=tk.X, padx=14)

        # Описание
        desc = tpl.get("desc", "")
        if not desc:
            desc = f"{tpl.get('cell_size', 800)}px · рамка {tpl.get('border', 10)}"
        tk.Label(self, text=desc,
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 8),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(0, 8))

        # Кнопка удаления
        if on_delete:
            del_btn = tk.Label(self, text="✕",
                               bg=p["surface"], fg=p["text_faint"],
                               font=("Segoe UI", 10), cursor="hand2")
            del_btn.place(relx=1.0, rely=0.0, x=-10, y=6, anchor="ne")
            del_btn.bind("<Button-1>", lambda e: on_delete())

        # Hover
        for w in (self, preview):
            w.bind("<Enter>", self._on_enter, add="+")
            w.bind("<Leave>", self._on_leave, add="+")
            w.bind("<Button-1>", lambda e: on_click(), add="+")

    def _on_enter(self, _):
        self.configure(highlightbackground=self.p["accent"],
                       highlightthickness=2)

    def _on_leave(self, _):
        self.configure(highlightbackground=self.p["border"],
                       highlightthickness=1)

    @staticmethod
    def _draw_layout_preview(canvas, layout_name):
        """Рисует миниатюру раскладки."""
        W, H = 200, 70
        color = "#5a5a70"
        pad = 6

        if "2×2" in layout_name:
            cols, rows = 2, 2
        elif "4×1" in layout_name or "горизонтальная" in layout_name:
            cols, rows = 4, 1
        elif "1×4" in layout_name or "вертикальная" in layout_name:
            cols, rows = 1, 4
        else:
            cols, rows = 2, 2

        cell_w = (W - pad * (cols + 1)) / cols
        cell_h = (H - pad * (rows + 1)) / rows

        for r in range(rows):
            for c in range(cols):
                x1 = pad + c * (cell_w + pad)
                y1 = pad + r * (cell_h + pad)
                x2 = x1 + cell_w
                y2 = y1 + cell_h
                canvas.create_rectangle(x1, y1, x2, y2,
                                        outline=color, width=1)


# ==============================================================
def _apply_template(app, tpl):
    try:
        app.config["layout"] = tpl.get("layout", app.config["layout"])
        app.config["mode"] = tpl.get("mode", app.config["mode"])
        app.config["cell_size"] = int(tpl.get("cell_size",
                                              app.config["cell_size"]))
        app.config["border"] = int(tpl.get("border", app.config["border"]))
        app.config["border_color"] = tpl.get("border_color",
                                             app.config["border_color"])
        app.config["bg_color"] = tpl.get("bg_color", app.config["bg_color"])
        app.config.save()

        # Обновить поля интерфейса
        app.layout_var.set(app.config["layout"])
        app.mode_var.set(app.config["mode"])
        app.cell_var.set(app.config["cell_size"])
        app.border_var.set(app.config["border"])
        if hasattr(app, "border_color_btn"):
            app.border_color_btn.set_color(app.config["border_color"])
        if hasattr(app, "bg_color_btn"):
            app.bg_color_btn.set_color(app.config["bg_color"])

        app.schedule_preview()
        app.update_status()
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