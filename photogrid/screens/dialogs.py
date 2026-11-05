"""Небольшие общие окна: ввод значений, подтверждение, показ текста с копированием."""
import tkinter as tk

from .. import fx
from ..ui_widgets import GradientButton


def _shell(app, title, width=420):
    p = app.palette
    top = fx.toplevel(app.root)
    top.title(title)
    top.configure(bg=p["surface"])
    top.transient(app.root)
    top.resizable(False, False)
    top.minsize(width, 120)               # диалог не должен быть «узкой щелью»
    top.bind("<Escape>", lambda e: top.destroy())
    wrap = tk.Frame(top, bg=p["surface"])
    wrap.pack(padx=28, pady=22)
    top.update_idletasks()
    rx, ry = app.root.winfo_rootx(), app.root.winfo_rooty()
    x = rx + (app.root.winfo_width() - width) // 2
    top.geometry(f"+{max(0, x)}+{max(0, ry + 140)}")
    return top, wrap


def ask(app, title, fields, on_submit, text="", ok_text="Готово", ok_icon="check", width=420):
    """Окно ввода. fields — [(ключ, подпись, значение_по_умолчанию, secret?)].
    on_submit(dict) → None или строка-ошибка (окно остаётся открытым)."""
    from .login import _NeonField
    p = app.palette
    top, wrap = _shell(app, title, width)
    tk.Label(wrap, text=title, bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 15, "bold"), anchor="w").pack(fill=tk.X)
    if text:
        tk.Label(wrap, text=text, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9),
                 justify="left", wraplength=width - 60, anchor="w").pack(fill=tk.X, pady=(2, 8))
    widgets = {}
    for key, label, default, secret in fields:
        f = _NeonField(wrap, p, label, "lock" if secret else "log", secret=secret)
        f.var.set(default or "")
        f.pack(fill=tk.X, pady=(6, 0))
        widgets[key] = f
    msg = tk.Label(wrap, text="", bg=p["surface"], fg="#ff5470", font=("Segoe UI", 9),
                   justify="left", wraplength=width - 60, anchor="w")
    msg.pack(fill=tk.X, pady=(8, 0))

    def submit():
        err = on_submit({k: w.get() for k, w in widgets.items()})
        if err:
            msg.configure(text=err)
        else:
            top.destroy()
    row = tk.Frame(wrap, bg=p["surface"])
    row.pack(fill=tk.X, pady=(12, 0))
    GradientButton(row, p, text=ok_text, icon=ok_icon, height=40, command=submit).pack(fill=tk.X)
    top.bind("<Return>", lambda e: submit())
    if widgets:
        next(iter(widgets.values())).entry.focus_set()
    return top


def confirm(app, title, text, on_yes, danger=False, ok_text="Да"):
    p = app.palette
    top, wrap = _shell(app, title, 400)
    tk.Label(wrap, text=title, bg=p["surface"], fg=p["text"], font=("Segoe UI", 15, "bold"),
             anchor="w").pack(fill=tk.X)
    tk.Label(wrap, text=text, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 10),
             justify="left", wraplength=340, anchor="w").pack(fill=tk.X, pady=(6, 14))
    row = tk.Frame(wrap, bg=p["surface"])
    row.pack(fill=tk.X)

    def yes():
        top.destroy()
        on_yes()
    b = tk.Button(row, text=ok_text, command=yes, bd=0, relief="flat", cursor="hand2",
                  bg="#ff5470" if danger else p["accent"], fg="#ffffff",
                  activebackground="#ff7088" if danger else p["accent_hi"],
                  activeforeground="#ffffff", font=("Segoe UI", 10, "bold"), padx=18, pady=9,
                  highlightthickness=0, takefocus=0)
    b.pack(side=tk.LEFT)
    tk.Button(row, text="Отмена", command=top.destroy, bd=0, relief="flat", cursor="hand2",
              bg=p["surface_alt"], fg=p["text"], activebackground=p["surface_hi"],
              activeforeground=p["text"], font=("Segoe UI", 10), padx=18, pady=9,
              highlightthickness=0, takefocus=0).pack(side=tk.LEFT, padx=(8, 0))
    return top


def show_text(app, title, text, copy_text=None, note=""):
    """Показывает текст (например, выданные ключи) с кнопкой «Копировать»."""
    p = app.palette
    top, wrap = _shell(app, title, 480)
    tk.Label(wrap, text=title, bg=p["surface"], fg=p["text"], font=("Segoe UI", 15, "bold"),
             anchor="w").pack(fill=tk.X)
    if note:
        tk.Label(wrap, text=note, bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9),
                 justify="left", wraplength=420, anchor="w").pack(fill=tk.X, pady=(2, 8))
    box = tk.Text(wrap, width=44, height=min(14, max(3, text.count("\n") + 2)),
                  bg=p["surface_alt"], fg=p["text"], relief="flat", bd=0,
                  font=("Consolas", 11), insertbackground=p["text"], padx=10, pady=8)
    box.insert("1.0", text)
    box.configure(state="disabled")
    box.pack(fill=tk.X, pady=(6, 0))

    def copy():
        app.root.clipboard_clear()
        app.root.clipboard_append(copy_text if copy_text is not None else text)
        app.set_status("Скопировано в буфер обмена")
    GradientButton(wrap, p, text="Копировать", icon="copy", height=40,
                   command=copy).pack(fill=tk.X, pady=(12, 0))
    return top
