"""Раздел «Плагины»: список загруженных + их действия."""
import tkinter as tk
from tkinter import messagebox

from .. import branding
from ..ui_widgets import enable_mousewheel

# Метаданные о встроенных плагинах: описание, категория
PLUGIN_META = {
    "drag_drop": {
        "title": "Drag & Drop",
        "desc": "Перетаскивание файлов на слоты",
        "category": "Интеграция",
    },
    "batch": {
        "title": "Пакетная обработка",
        "desc": "Коллаж для каждой папки с 4+ фото",
        "category": "Экспорт",
        "open_section": "batch",
    },
    "watermark": {
        "title": "Водяной знак",
        "desc": "Наложение текста поверх коллажа",
        "category": "Оформление",
    },
    "pdf_export": {
        "title": "Экспорт в PDF",
        "desc": "Сохранение коллажа в PDF-документ",
        "category": "Экспорт",
    },
    "crop_editor": {
        "title": "Редактор обрезки",
        "desc": "Ручная обрезка фото перед сборкой",
        "category": "Редактирование",
    },
    "clipboard": {
        "title": "Вставка из буфера",
        "desc": "Вставка картинок из буфера обмена",
        "category": "Интеграция",
    },
    "templates": {
        "title": "Шаблоны оформления",
        "desc": "Сохранение и загрузка наборов настроек",
        "category": "Оформление",
    },
    "auto_updater": {
        "title": "Автообновление",
        "desc": "Фоновая проверка новых версий",
        "category": "Система",
    },
    "updater_ui": {
        "title": "Проверка обновлений",
        "desc": "Ручная проверка и установка обновлений",
        "category": "Система",
    },
}


def build_plugins_view(parent, app):
    """Создаёт раздел «Плагины»."""
    p = app.palette

    root = tk.Frame(parent, bg=p["bg"])
    root.pack(fill=tk.BOTH, expand=True, padx=(0, 14), pady=(14, 0))

    # Заголовок
    head = tk.Frame(root, bg=p["bg"])
    head.pack(fill=tk.X, padx=8, pady=(6, 16))
    tk.Label(head, text="Плагины",
             bg=p["bg"], fg=p["text"],
             font=("Segoe UI", 16, "bold"),
             anchor="w").pack(side=tk.LEFT)

    loaded = list(app.plugin_flags.keys())
    tk.Label(head, text=f"{len(loaded)} активно",
             bg=p["bg"], fg=p["text_dim"],
             font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(16, 0))

    # Скроллируемая область
    outer = tk.Frame(root, bg=p["bg"])
    outer.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(outer, bg=p["bg"], highlightthickness=0)
    scroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=p["bg"])
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    from ..ui_widgets import enable_mousewheel
    enable_mousewheel(canvas)

    # ===== Секция 1: загруженные плагины (сетка 2 колонки) =====
    _section_label(inner, "Загруженные плагины", p)

    cards = tk.Frame(inner, bg=p["bg"])
    cards.pack(fill=tk.X, padx=8, pady=(0, 16))
    cards.columnconfigure(0, weight=1, uniform="plugcol")
    cards.columnconfigure(1, weight=1, uniform="plugcol")

    if not loaded:
        tk.Label(cards, text="Плагины не загружены.",
                 bg=p["bg"], fg=p["text_dim"],
                 font=("Segoe UI", 10)
                 ).grid(row=0, column=0, columnspan=2,
                        sticky="w", padx=8, pady=8)
    else:
        for i, name in enumerate(loaded):
            meta = PLUGIN_META.get(name, {
                "title": name.replace("_", " ").title(),
                "desc": "Пользовательский плагин",
                "category": "Прочее",
            })
            card = _PluginCard(cards, p, name, meta, app)
            card.grid(row=i // 2, column=i % 2,
                      padx=6, pady=6, sticky="nsew")

    # ===== Секция 2: действия =====
    _section_label(inner, "Доступные действия", p)

    actions_frame = tk.Frame(inner, bg=p["bg"])
    actions_frame.pack(fill=tk.X, padx=8, pady=(0, 16))

    actions = getattr(app, "plugin_actions", {})
    has_any = any(actions.values())

    if not has_any:
        tk.Label(actions_frame,
                 text="Плагины не зарегистрировали действий.",
                 bg=p["bg"], fg=p["text_dim"],
                 font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=8)
    else:
        # Группируем по исходному меню: Файл / Правка / Вид / Справка
        for menu_name in ("Файл", "Правка", "Вид", "Справка"):
            items = actions.get(menu_name, [])
            if not items:
                continue
            _group(actions_frame, menu_name, items, p, app)

    # ===== Секция 3: открыть раздел «Пакетная» =====
    _section_label(inner, "Разделы", p)
    link_row = tk.Frame(inner, bg=p["bg"])
    link_row.pack(fill=tk.X, padx=16, pady=(0, 16))

    tk.Button(link_row, text="  Открыть «Пакетная обработка»",
              bg=p["accent"], fg="#ffffff",
              activebackground=p["accent_hi"], activeforeground="#ffffff",
              bd=0, relief="flat", cursor="hand2",
              font=("Segoe UI", 10, "bold"),
              padx=18, pady=10,
              command=lambda: app._set_section("batch")
              ).pack(anchor="w")

    return root


# ==============================================================
def _section_label(parent, text, p):
    tk.Label(parent, text=text.upper(),
             bg=p["bg"], fg=p["text_faint"],
             font=("Segoe UI", 9, "bold"),
             anchor="w").pack(fill=tk.X, padx=8, pady=(8, 4))


def _group(parent, title, items, p, app):
    """Группа действий (например, «Правка»)."""
    wrap = tk.Frame(parent, bg=p["border"], bd=0)
    wrap.pack(fill=tk.X, padx=8, pady=(4, 8))
    card = tk.Frame(wrap, bg=p["surface"])
    card.pack(fill=tk.X, padx=1, pady=1)

    tk.Label(card, text=title.upper(),
             bg=p["surface"], fg=p["text_faint"],
             font=("Segoe UI", 8, "bold"),
             anchor="w").pack(fill=tk.X, padx=14, pady=(10, 6))

    for item in items:
        label = item.get("label", "Действие")
        command = item.get("command")
        accel = item.get("accelerator", "")

        row = tk.Frame(card, bg=p["surface"])
        row.pack(fill=tk.X, padx=8, pady=2)

        btn = tk.Button(
            row, text="  " + label,
            bg=p["surface"], fg=p["text"],
            activebackground=p["surface_hi"],
            activeforeground=p["text"],
            bd=0, relief="flat", cursor="hand2",
            font=("Segoe UI", 10), anchor="w",
            padx=12, pady=8,
            command=command,
        )
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        if accel:
            tk.Label(row, text=accel,
                     bg=p["surface"], fg=p["text_faint"],
                     font=("Segoe UI", 8),
                     padx=10).pack(side=tk.RIGHT)


class _PluginCard(tk.Frame):
    """Карточка одного плагина."""

    def __init__(self, parent, p, name, meta, app):
        super().__init__(parent, bg=p["border"], bd=0)
        self.p = p
        self.name = name
        self.app = app

        inner = tk.Frame(self, bg=p["surface"])
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Индикатор
        dot = tk.Canvas(inner, width=10, height=10,
                        bg=p["surface"], highlightthickness=0)
        dot.pack(side=tk.LEFT, padx=(14, 10), pady=14)
        dot.create_oval(2, 2, 8, 8, fill=p["success"], outline="")

        # Текст
        text_box = tk.Frame(inner, bg=p["surface"])
        text_box.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)

        row1 = tk.Frame(text_box, bg=p["surface"])
        row1.pack(fill=tk.X)

        tk.Label(row1, text=meta.get("title", name),
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(side=tk.LEFT)

        cat = meta.get("category", "")
        if cat:
            chip = tk.Label(row1, text=cat.upper(),
                            bg=p["surface_alt"], fg=p["text_dim"],
                            font=("Segoe UI", 7, "bold"),
                            padx=6, pady=2)
            chip.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(text_box, text=meta.get("desc", ""),
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9),
                 anchor="w").pack(fill=tk.X)

        # Дополнительное действие для batch
        if meta.get("open_section"):
            sec = meta["open_section"]
            btn = tk.Button(inner, text="Открыть",
                            bg=p["surface_alt"], fg=p["text"],
                            activebackground=p["surface_hi"],
                            activeforeground=p["text"],
                            bd=0, relief="flat", cursor="hand2",
                            font=("Segoe UI", 9),
                            padx=10, pady=5,
                            command=lambda s=sec: app._set_section(s))
            btn.pack(side=tk.RIGHT, padx=12)