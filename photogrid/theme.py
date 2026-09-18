"""Тёмная/светлая тема, шрифты, ttk-стили."""
import sys
import tkinter as tk
from tkinter import ttk


def system_font_family():
    if sys.platform == "win32":
        for family in ("Segoe UI Variable Text", "Segoe UI", "Tahoma"):
            if _font_exists(family):
                return family
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "Inter"


_font_cache = {}


def _font_exists(family):
    if family in _font_cache:
        return _font_cache[family]
    try:
        import tkinter.font as tkfont
        root = tk._default_root
        if root is None:
            _font_cache[family] = True
            return True
        families = set(tkfont.families(root))
        ok = family in families
    except Exception:
        ok = True
    _font_cache[family] = ok
    return ok


def get_font(size=10, bold=False, italic=False):
    style = ""
    if bold and italic:
        style = "bold italic"
    elif bold:
        style = "bold"
    elif italic:
        style = "italic"
    if style:
        return (system_font_family(), size, style)
    return (system_font_family(), size)


# ---------------------------------------------------------------- палитры
DARK = {
    "bg":            "#0f0f17",   # нейтральный тёмный фон
    "surface":       "#18181f",   # панели
    "surface_alt":   "#21212a",   # поля ввода
    "surface_hi":    "#2a2a36",   # hover
    "border":        "#26262f",
    "border_soft":   "#1f1f27",

    "text":          "#e6e6ef",
    "text_dim":      "#8a8a9c",
    "text_faint":    "#5a5a6c",

    "accent":        "#7c7cff",   # мягкий индиго
    "accent_hi":     "#9292ff",   # hover
    "accent_lo":     "#6666e0",   # pressed
    "accent2":       "#7c7cff",   # без градиента — тот же цвет
    "accent_soft":   "#25254a",

    "success":       "#4ade80",
    "danger":        "#f87171",
    "warning":       "#fbbf24",

    "slot_bg":       "#1a1a22",
    "slot_border":   "#2a2a36",
    "shadow":        "#000000",
}

LIGHT = {
    "bg":            "#f4f5f9",
    "surface":       "#ffffff",
    "surface_alt":   "#eef0f5",
    "surface_hi":    "#e2e5ef",
    "border":        "#dde0ea",
    "border_soft":   "#e8eaf2",

    "text":          "#171726",
    "text_dim":      "#6d6d88",
    "text_faint":    "#9a9ab0",

    "accent":        "#6666e0",
    "accent_hi":     "#7878e8",
    "accent_lo":     "#5252c4",
    "accent2":       "#6666e0",
    "accent_soft":   "#e4e4fc",

    "success":       "#16a34a",
    "danger":        "#dc2626",
    "warning":       "#d97706",

    "slot_bg":       "#f0f0f6",
    "slot_border":   "#dcdce6",
    "shadow":        "#c8c8dc",
}


def apply_theme(root, name="dark"):
    palette = DARK if name == "dark" else LIGHT
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=palette["bg"])

    style.configure("TFrame", background=palette["bg"])
    style.configure("Surface.TFrame", background=palette["surface"])
    style.configure("Bg.TFrame", background=palette["bg"])

    style.configure("TLabel", background=palette["surface"],
                    foreground=palette["text"], font=get_font(10))
    style.configure("Section.TLabel", background=palette["surface"],
                    foreground=palette["text_faint"], font=get_font(9, bold=True))
    style.configure("Dim.TLabel", background=palette["surface"],
                    foreground=palette["text_dim"], font=get_font(9))
    style.configure("Hint.TLabel", background=palette["surface"],
                    foreground=palette["text_faint"], font=get_font(9))

    style.configure("TButton",
                    background=palette["surface_alt"],
                    foreground=palette["text"],
                    borderwidth=0, focusthickness=0,
                    padding=(14, 10), font=get_font(10), relief="flat")
    style.map("TButton",
              background=[("active", palette["surface_hi"])],
              foreground=[("active", palette["text"])])

    style.configure("Accent.TButton",
                    background=palette["accent"],
                    foreground="#ffffff",
                    borderwidth=0, focusthickness=0,
                    padding=(16, 12), font=get_font(10, bold=True),
                    relief="flat")
    style.map("Accent.TButton",
              background=[("active", palette["accent_hi"]),
                          ("pressed", palette["accent_lo"])])

    style.configure("Ghost.TButton",
                    background=palette["surface"],
                    foreground=palette["text_dim"],
                    borderwidth=0, focusthickness=0,
                    padding=(10, 6), font=get_font(9), relief="flat")
    style.map("Ghost.TButton",
              background=[("active", palette["surface_alt"])],
              foreground=[("active", palette["text"])])

    style.configure("TRadiobutton",
                    background=palette["surface"],
                    foreground=palette["text"],
                    font=get_font(10),
                    focuscolor=palette["surface"],
                    indicatorcolor=palette["surface_alt"])
    style.map("TRadiobutton",
              background=[("active", palette["surface"])],
              foreground=[("active", palette["accent"])])

    style.configure("TCheckbutton",
                    background=palette["surface"],
                    foreground=palette["text"],
                    font=get_font(10),
                    focuscolor=palette["surface"])
    style.map("TCheckbutton",
              background=[("active", palette["surface"])],
              foreground=[("active", palette["accent"])])

    style.configure("TCombobox",
                    fieldbackground=palette["surface_alt"],
                    background=palette["surface_alt"],
                    foreground=palette["text"],
                    arrowcolor=palette["text_dim"],
                    borderwidth=0, padding=8, relief="flat")
    style.map("TCombobox",
              fieldbackground=[("readonly", palette["surface_alt"]),
                               ("active", palette["surface_hi"])],
              background=[("readonly", palette["surface_alt"]),
                          ("active", palette["surface_hi"])],
              foreground=[("readonly", palette["text"])])

    style.configure("TSpinbox",
                    fieldbackground=palette["surface_alt"],
                    background=palette["surface_alt"],
                    foreground=palette["text"],
                    arrowcolor=palette["text_dim"],
                    borderwidth=0, padding=6, relief="flat")
    style.map("TSpinbox",
              fieldbackground=[("focus", palette["surface_hi"])])

    style.configure("TScale",
                    background=palette["surface"],
                    troughcolor=palette["surface_alt"],
                    borderwidth=0, sliderthickness=14,
                    lightcolor=palette["accent"],
                    darkcolor=palette["accent"])

    style.configure("TSeparator", background=palette["border"])

    style.configure("TEntry",
                    fieldbackground=palette["surface_alt"],
                    foreground=palette["text"],
                    borderwidth=0, padding=8, relief="flat")
    style.map("TEntry",
              fieldbackground=[("focus", palette["surface_hi"])])

    style.configure("TProgressbar",
                    troughcolor=palette["surface_alt"],
                    background=palette["accent"],
                    borderwidth=0, thickness=6)

    return palette