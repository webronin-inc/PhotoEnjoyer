"""Окна «О программе» и «Горячие клавиши» в фирменном стиле."""
import tkinter as tk
import webbrowser
from pathlib import Path

from .. import branding, fx, icons
from ..ui_widgets import GradientButton, LogoMark, _blend_hex

# (группа, [(сочетание, описание)])
HOTKEYS = (
    ("Файл", (
        ("Ctrl+O", "Выбрать фото"),
        ("Ctrl+S", "Сохранить коллаж"),
        ("Ctrl+Shift+S", "Сохранить как…"),
        ("Ctrl+Shift+C", "Копировать в буфер"),
        ("Ctrl+V", "Вставить фото из буфера"),
    )),
    ("Правка", (
        ("Ctrl+Z", "Отменить"),
        ("Ctrl+Y", "Повторить"),
        ("Ctrl+Shift+Z", "Повторить (как Ctrl+Y)"),
        ("Ctrl+A", "Отметить все фото"),
        ("Delete", "Убрать отмеченные (или выбранное) фото"),
        ("Esc", "Снять отметки и выделение"),
        ("Ctrl+E", "Редактор фото для выбранного слота"),
    )),
    ("Вид", (
        ("F5", "Обновить предпросмотр"),
        ("Ctrl+,", "Настройки"),
    )),
    ("Мышь", (
        ("Клик", "Выбрать слот · по пустому — добавить файл"),
        ("Два клика", "Поменять два фото местами"),
        ("Ctrl/Shift+клик", "Отметить для удаления"),
        ("Двойной клик", "Заменить фото"),
        ("ПКМ", "Меню слота"),
    )),
)


def _fit(top, app, w, min_h=0):
    """Высота окна — по содержимому, окно по центру главного."""
    top.update_idletasks()
    h = max(min_h, top.winfo_reqheight())
    app.root.update_idletasks()
    rx, ry = app.root.winfo_rootx(), app.root.winfo_rooty()
    rw, rh = app.root.winfo_width(), app.root.winfo_height()
    x = max(0, rx + (rw - w) // 2)
    y = max(0, ry + (rh - h) // 3)
    top.geometry(f"{w}x{h}+{x}+{y}")


def _shell(app, title, w, h):
    p = app.palette
    top = tk.Toplevel(app.root)
    top.title(title)
    top.configure(bg=p["bg"])
    top.transient(app.root)
    top.resizable(False, False)
    top.bind("<Escape>", lambda e: top.destroy())
    wrap = tk.Frame(top, bg=p["surface"], highlightthickness=1,
                    highlightbackground=p["border"])
    wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    return top, wrap


def _changelog_latest():
    """Последний блок CHANGELOG.md (если файл есть рядом с программой)."""
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1], Path.cwd()):
        f = base / "CHANGELOG.md"
        if f.exists():
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                return []
            blocks = [b for b in text.split("\n## ") if b.strip()]
            if not blocks:
                return []
            lines = [ln[2:].strip() for ln in blocks[0].splitlines()[1:]
                     if ln.startswith("- ")]
            short = []
            for ln in lines[:4]:                 # в окне — только суть
                ln = ln.split(". ")[0]
                short.append(ln if len(ln) <= 92 else ln[:89].rstrip(" ,;:—-") + "…")
            return short
    return []


def show_about(app):
    p = app.palette
    from ..version import __release_date__, __version__
    top, wrap = _shell(app, f"О программе — {branding.APP_NAME}", 560, 600)

    hero = tk.Frame(wrap, bg=p["surface"])
    hero.pack(pady=(26, 4))
    LogoMark(hero, {**p, "bg": p["surface"]}, size=84).pack()
    tk.Label(hero, text=branding.APP_NAME, bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 22, "bold")).pack(pady=(6, 0))
    tk.Label(hero, text=f"версия {__version__} · {__release_date__}",
             bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 10)).pack()
    tk.Label(hero, text="Коллажи из фотографий за пару кликов",
             bg=p["surface"], fg=p["accent_hi"],
             font=("Segoe UI", 10, "bold")).pack(pady=(8, 0))

    news = _changelog_latest()
    if news:
        tk.Label(wrap, text="ЧТО НОВОГО", bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 8, "bold"), anchor="w"
                 ).pack(fill=tk.X, padx=30, pady=(18, 4))
        card = tk.Frame(wrap, bg=p["surface_alt"])
        card.pack(fill=tk.X, padx=28)
        for line in news:
            tk.Label(card, text="•  " + line, bg=p["surface_alt"], fg=p["text"],
                     font=("Segoe UI", 9), anchor="w", justify="left",
                     wraplength=440).pack(fill=tk.X, padx=14, pady=3)
        tk.Frame(card, bg=p["surface_alt"], height=4).pack()

    plugins = [k for k in app.plugin_flags]
    if plugins:
        tk.Label(wrap, text=f"ПЛАГИНЫ  ·  {len(plugins)}", bg=p["surface"],
                 fg=p["text_faint"], font=("Segoe UI", 8, "bold"), anchor="w"
                 ).pack(fill=tk.X, padx=30, pady=(16, 4))
        chips = tk.Frame(wrap, bg=p["surface"])
        chips.pack(fill=tk.X, padx=28)
        for i, name in enumerate(plugins):
            tk.Label(chips, text=name.replace("_", " "),
                     bg=_blend_hex(p["accent"], p["surface"], 0.16),
                     fg=p["accent_hi"], font=("Segoe UI", 8), padx=8, pady=3
                     ).grid(row=i // 5, column=i % 5, padx=3, pady=3, sticky="w")

    bar = tk.Frame(wrap, bg=p["surface"])
    bar.pack(fill=tk.X, padx=26, pady=(22, 14))
    GradientButton(bar, p, text="Проверить обновления", icon="refresh",
                   height=40, command=lambda: (top.destroy(),
                                               app._on_update_click())
                   ).pack(side=tk.LEFT)
    for text, cmd in (("Горячие клавиши", lambda: (top.destroy(), show_hotkeys(app))),
                      ("GitHub", lambda: webbrowser.open(branding.APP_HOMEPAGE))):
        b = tk.Button(bar, text=text, command=cmd, bg=p["surface_alt"],
                      fg=p["text"], activebackground=p["surface_hi"],
                      activeforeground=p["text"], bd=0, relief="flat",
                      cursor="hand2", font=("Segoe UI", 9), padx=14, pady=10,
                      highlightthickness=0, takefocus=0)
        b.pack(side=tk.LEFT, padx=(8, 0))
    tk.Label(wrap, text=f"© {branding.APP_PUBLISHER}", bg=p["surface"],
             fg=p["text_faint"], font=("Segoe UI", 8)).pack(pady=(0, 12))
    _fit(top, app, 560)
    fx.dialog_in(top)
    return top


def show_hotkeys(app):
    p = app.palette
    top, wrap = _shell(app, "Горячие клавиши", 760, 560)

    head = tk.Frame(wrap, bg=p["surface"])
    head.pack(fill=tk.X, padx=28, pady=(22, 6))
    ic = tk.Canvas(head, width=48, height=48, bg=p["surface"], highlightthickness=0)
    ic.pack(side=tk.LEFT)
    icons.draw_neon(ic, "wand", 24, 24, size=26, color=icons.NEON["cyan"])
    box = tk.Frame(head, bg=p["surface"])
    box.pack(side=tk.LEFT, padx=(10, 0))
    tk.Label(box, text="Горячие клавиши", bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 17, "bold")).pack(anchor="w")
    tk.Label(box, text="Работают на любой раскладке — русской тоже",
             bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 10)
             ).pack(anchor="w")

    cols = tk.Frame(wrap, bg=p["surface"])
    cols.pack(fill=tk.BOTH, expand=True, padx=24, pady=(10, 18))
    cols.columnconfigure((0, 1), weight=1, uniform="c")
    for gi, (group, rows) in enumerate(HOTKEYS):
        col = tk.Frame(cols, bg=p["surface"])
        col.grid(row=gi // 2, column=gi % 2, sticky="nsew", padx=8, pady=6)
        tk.Label(col, text=group.upper(), bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, pady=(0, 4))
        for keys, text in rows:
            row = tk.Frame(col, bg=p["surface"])
            row.pack(fill=tk.X, pady=3)
            kc = tk.Frame(row, bg=p["surface"])
            kc.pack(side=tk.LEFT)
            for j, part in enumerate(keys.split("+")):
                if j:
                    tk.Label(kc, text="+", bg=p["surface"], fg=p["text_faint"],
                             font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=2)
                tk.Label(kc, text=part, bg=p["surface_hi"], fg=p["text"],
                         font=("Segoe UI", 9, "bold"), padx=7, pady=2,
                         highlightthickness=1, highlightbackground=p["border"]
                         ).pack(side=tk.LEFT)
            tk.Label(row, text=text, bg=p["surface"], fg=p["text_dim"],
                     font=("Segoe UI", 9), anchor="w", wraplength=170,
                     justify="left").pack(side=tk.LEFT, padx=(12, 0))
    _fit(top, app, 760)
    fx.dialog_in(top)
    return top
