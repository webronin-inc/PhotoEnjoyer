"""Шаблоны оформления: сохранение/загрузка/удаление наборов настроек."""
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from .. import branding

TEMPLATES_FILE = Path.home() / f"{branding.APP_CONFIG_DIR}_templates.json"

KEYS = ("layout", "mode", "cell_size", "border",
        "border_color", "bg_color", "quality", "watermark")


def register(app):
    app.add_menu_item("Вид", "Сохранить шаблон…", lambda: _save(app))
    app.add_menu_item("Вид", "Загрузить шаблон…", lambda: _load_dialog(app))
    app.add_menu_item("Вид", "Удалить шаблон…", lambda: _delete_dialog(app))
    app.plugin_flags["templates"] = True


def _read_all():
    try:
        if TEMPLATES_FILE.exists():
            return json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_all(data):
    TEMPLATES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def _collect_current(app):
    tpl = {}
    for k in KEYS:
        if k == "watermark":
            wm = app.config.data.get("watermark")
            tpl[k] = dict(wm) if wm else None
        else:
            tpl[k] = app.config.get(k)
    return tpl


def _apply(app, tpl):
    for k in KEYS:
        if k in tpl and tpl[k] is not None:
            app.config[k] = tpl[k]
    app.layout_var.set(app.config["layout"])
    app.mode_var.set(app.config["mode"])
    app.cell_var.set(app.config["cell_size"])
    app.border_var.set(app.config["border"])
    app.quality_var.set(app.config["quality"])
    app.quality_label.config(text=f"{app.config['quality']}%")
    app.border_color_btn.config(bg=app.config["border_color"])
    app.bg_color_btn.config(bg=app.config["bg_color"])
    if tpl.get("watermark"):
        app.plugin_flags["watermark"] = bool(tpl["watermark"].get("enabled"))
    app.config.save()
    app.update_preview()
    app.update_status()


def _save(app):
    name = simpledialog.askstring("Сохранить шаблон", "Название шаблона:",
                                  parent=app.root)
    if not name:
        return
    name = name.strip()
    if not name:
        return
    data = _read_all()
    data[name] = _collect_current(app)
    _write_all(data)
    app.set_status(f"Шаблон «{name}» сохранён")


def _load_dialog(app):
    data = _read_all()
    if not data:
        messagebox.showinfo("Шаблоны", "Нет сохранённых шаблонов")
        return

    def do(n):
        _apply(app, data[n])
        app.set_status(f"Шаблон «{n}» загружен")

    _pick_dialog(app, "Загрузить шаблон", list(data), do)


def _delete_dialog(app):
    data = _read_all()
    if not data:
        messagebox.showinfo("Шаблоны", "Нет сохранённых шаблонов")
        return

    def do(n):
        del data[n]
        _write_all(data)
        app.set_status(f"Шаблон «{n}» удалён")

    _pick_dialog(app, "Удалить шаблон", list(data), do)


def _pick_dialog(app, title, names, on_choice):
    p = app.palette
    top = tk.Toplevel(app.root)
    top.title(title)
    top.configure(bg=p["surface"])
    top.transient(app.root)
    top.grab_set()
    top.geometry("360x440")

    tk.Label(top, text=title, bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 11, "bold")).pack(pady=(16, 10))

    lb = tk.Listbox(top, bg=p["surface_alt"], fg=p["text"],
                    bd=0, highlightthickness=0, font=("Segoe UI", 10),
                    selectbackground=p["accent"], activestyle="none")
    for n in names:
        lb.insert("end", n)
    lb.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
    if names:
        lb.selection_set(0)

    def ok(_=None):
        sel = lb.curselection()
        if not sel:
            return
        name = lb.get(sel[0])
        top.destroy()
        on_choice(name)

    lb.bind("<Double-Button-1>", ok)

    bf = tk.Frame(top, bg=p["surface"]); bf.pack(fill=tk.X, padx=16, pady=(0, 14))
    ttk.Button(bf, text="OK", style="Accent.TButton", command=ok).pack(side=tk.RIGHT)
    ttk.Button(bf, text="Отмена", command=top.destroy).pack(side=tk.RIGHT, padx=(0, 8))