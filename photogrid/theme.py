"""Тёмная/светлая тема, шрифты, ttk-стили."""
import sys
import tkinter as tk
from tkinter import ttk


def system_font_family():
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    return "DejaVu Sans"


def get_font(size=10, bold=False):
    return (system_font_family(), size, "bold") if bold else (system_font_family(), size)


DARK = {
    "bg":           "#14141c",
    "surface":      "#1c1c28",
    "surface_alt":  "#25253a",
    "surface_hi":   "#2e2e48",
    "border":       "#2c2c44",
    "text":         "#eaeaf2",
    "text_dim":     "#7e7e9c",
    "accent":       "#7c5cff",
    "accent_hi":    "#917aFF",
    "accent_lo":    "#6144e0",
    "success":      "#3ddc84",
    "danger":       "#ff5570",
    "warning":      "#ffbb33",
    "slot_bg":      "#22222f",
    "slot_border":  "#2f2f48",
}

LIGHT = {
    "bg":           "#f5f5fa",
    "surface":      "#ffffff",
    "surface_alt":  "#eeeef5",
    "surface_hi":   "#e0e0ee",
    "border":       "#dcdce6",
    "text":         "#1a1a24",
    "text_dim":     "#666680",
    "accent":       "#6a4cff",
    "accent_hi":    "#7e64ff",
    "accent_lo":    "#5238cc",
    "success":      "#22b46d",
    "danger":       "#e63950",
    "warning":      "#e59e00",
    "slot_bg":      "#ececf2",
    "slot_border":  "#d4d4e0",
}


def apply_theme(root, name="dark"):
    palette = DARK if name == "dark" else LIGHT
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=palette["bg"])

    # --- Ttk базовые ---
    style.configure("TFrame", background=palette["bg"])
    style.configure("Surface.TFrame", background=palette["surface"])
    style.configure("Card.TFrame", background=palette["surface"])
    style.configure("Header.TFrame", background=palette["surface"])
    style.configure("Status.TFrame", background=palette["surface"])

    # --- Labels ---
    style.configure("TLabel", background=palette["surface"],
                    foreground=palette["text"], font=get_font(10))
    style.configure("Title.TLabel", background=palette["surface"],
                    foreground=palette["text"], font=get_font(12, bold=True))
    style.configure("Section.TLabel", background=palette["surface"],
                    foreground=palette["text_dim"], font=get_font(9, bold=True))
    style.configure("Dim.TLabel", background=palette["surface"],
                    foreground=palette["text_dim"], font=get_font(9))
    style.configure("Hint.TLabel", background=palette["surface"],
                    foreground=palette["text_dim"], font=get_font(9))
    style.configure("Status.TLabel", background=palette["surface"],
                    foreground=palette["text_dim"], font=get_font(9))

    # --- Buttons ---
    style.configure("TButton",
                    background=palette["surface_alt"],
                    foreground=palette["text"],
                    borderwidth=0, focusthickness=0,
                    padding=(14, 9), font=get_font(10))
    style.map("TButton",
              background=[("active", palette["surface_hi"]),
                          ("pressed", palette["surface_hi"])],
              foreground=[("active", palette["text"])])

    style.configure("Accent.TButton",
                    background=palette["accent"], foreground="#ffffff",
                    borderwidth=0, focusthickness=0,
                    padding=(14, 11), font=get_font(10, bold=True))
    style.map("Accent.TButton",
              background=[("active", palette["accent_hi"]),
                          ("pressed", palette["accent_lo"])])

    style.configure("Ghost.TButton",
                    background=palette["surface"], foreground=palette["text_dim"],
                    borderwidth=0, focusthickness=0,
                    padding=(10, 6), font=get_font(9))
    style.map("Ghost.TButton",
              background=[("active", palette["surface_alt"])],
              foreground=[("active", palette["text"])])

    # --- Radiobutton ---
    style.configure("TRadiobutton",
                    background=palette["surface"], foreground=palette["text"],
                    font=get_font(10), focuscolor=palette["surface"],
                    indicatorcolor=palette["surface_alt"])
    style.map("TRadiobutton",
              background=[("active", palette["surface"])],
              foreground=[("active", palette["accent"])])

    # --- Combobox ---
    style.configure("TCombobox",
                    fieldbackground=palette["surface_alt"],
                    background=palette["surface_alt"],
                    foreground=palette["text"],
                    arrowcolor=palette["text_dim"],
                    borderwidth=0, padding=6)
    style.map("TCombobox",
              fieldbackground=[("readonly", palette["surface_alt"])],
              background=[("readonly", palette["surface_alt"])],
              foreground=[("readonly", palette["text"])])

    # --- Spinbox ---
    style.configure("TSpinbox",
                    fieldbackground=palette["surface_alt"],
                    background=palette["surface_alt"],
                    foreground=palette["text"],
                    arrowcolor=palette["text_dim"],
                    borderwidth=0, padding=4)
    style.map("TSpinbox",
              fieldbackground=[("focus", palette["surface_hi"])])

    # --- Scale ---
    style.configure("TScale",
                    background=palette["surface"],
                    troughcolor=palette["surface_alt"],
                    borderwidth=0, lightcolor=palette["accent"],
                    darkcolor=palette["accent"])

    # --- Separator ---
    style.configure("TSeparator", background=palette["border"])

    return palette