"""Панель пакетной обработки: коллаж из каждой папки."""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import IMAGE_EXTS
from ..core import build_collage


def build_batch_view(parent, app):
    """Создаёт панель пакетной обработки и возвращает её корневой фрейм."""
    p = app.palette

    root = tk.Frame(parent, bg=p["bg"])
    root.pack(fill=tk.BOTH, expand=True, padx=(0, 14), pady=(14, 0))

    state = {
        "in_dir":  tk.StringVar(),
        "out_dir": tk.StringVar(),
        "recursive": tk.BooleanVar(value=True),
        "overwrite": tk.BooleanVar(value=False),
        "running": False,
        "stop": False,
    }

    # Заголовок
    head = tk.Frame(root, bg=p["bg"])
    head.pack(fill=tk.X, padx=8, pady=(6, 16))
    tk.Label(head, text="Пакетная обработка",
             bg=p["bg"], fg=p["text"],
             font=("Segoe UI", 16, "bold"),
             anchor="w").pack(side=tk.LEFT)
    tk.Label(head, text="Коллаж для каждой папки с 4+ фото",
             bg=p["bg"], fg=p["text_dim"],
             font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(16, 0))

    # Панель управления
    panel_outer = tk.Frame(root, bg=p["border"], bd=0)
    panel_outer.pack(fill=tk.X, padx=8, pady=(0, 12))
    panel = tk.Frame(panel_outer, bg=p["surface"])
    panel.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    # Входная папка
    _row_label(panel, "Входная папка", p)
    in_row = tk.Frame(panel, bg=p["surface"])
    in_row.pack(fill=tk.X, padx=18, pady=(0, 10))
    ttk.Entry(in_row, textvariable=state["in_dir"]).pack(
        side=tk.LEFT, fill=tk.X, expand=True)
    tk.Button(in_row, text="…", bg=p["surface_alt"], fg=p["text"],
              bd=0, relief="flat", cursor="hand2",
              font=("Segoe UI", 11), width=3,
              command=lambda: _pick_dir(state["in_dir"])
              ).pack(side=tk.LEFT, padx=(6, 0))

    # Выходная папка
    _row_label(panel, "Куда сохранять", p)
    out_row = tk.Frame(panel, bg=p["surface"])
    out_row.pack(fill=tk.X, padx=18, pady=(0, 10))
    ttk.Entry(out_row, textvariable=state["out_dir"]).pack(
        side=tk.LEFT, fill=tk.X, expand=True)
    tk.Button(out_row, text="…", bg=p["surface_alt"], fg=p["text"],
              bd=0, relief="flat", cursor="hand2",
              font=("Segoe UI", 11), width=3,
              command=lambda: _pick_dir(state["out_dir"])
              ).pack(side=tk.LEFT, padx=(6, 0))

    # Опции
    opts = tk.Frame(panel, bg=p["surface"])
    opts.pack(fill=tk.X, padx=18, pady=(0, 14))
    ttk.Checkbutton(opts, text="Обходить подпапки",
                    variable=state["recursive"]).pack(side=tk.LEFT)
    ttk.Checkbutton(opts, text="Перезаписывать существующие",
                    variable=state["overwrite"]).pack(side=tk.LEFT, padx=(18, 0))

    # Кнопки
    actions = tk.Frame(panel, bg=p["surface"])
    actions.pack(fill=tk.X, padx=18, pady=(0, 16))

    start_btn = tk.Button(
        actions, text="  Начать обработку",
        bg=p["accent"], fg="#ffffff",
        activebackground=p["accent_hi"], activeforeground="#ffffff",
        bd=0, relief="flat", cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        padx=18, pady=10,
    )
    start_btn.pack(side=tk.LEFT)

    stop_btn = tk.Button(
        actions, text="Остановить",
        bg=p["surface_alt"], fg=p["text_dim"],
        activebackground=p["surface_hi"], activeforeground=p["text"],
        bd=0, relief="flat", cursor="hand2",
        font=("Segoe UI", 10),
        padx=14, pady=10,
        state="disabled",
    )
    stop_btn.pack(side=tk.LEFT, padx=(8, 0))

    # Прогресс
    prog_wrap = tk.Frame(root, bg=p["bg"])
    prog_wrap.pack(fill=tk.X, padx=8, pady=(0, 6))
    progress = ttk.Progressbar(prog_wrap, mode="determinate")
    progress.pack(fill=tk.X)

    status = tk.Label(root, text="Готово к работе",
                      bg=p["bg"], fg=p["text_dim"],
                      font=("Segoe UI", 9), anchor="w")
    status.pack(fill=tk.X, padx=8, pady=(0, 8))

    # Лог
    _row_label(root, "Журнал", p)
    log_frame = tk.Frame(root, bg=p["border"])
    log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 16))
    log_list = tk.Listbox(
        log_frame, bg=p["surface"], fg=p["text"],
        bd=0, highlightthickness=0,
        font=("Consolas", 9), activestyle="none",
        selectbackground=p["surface_hi"],
    )
    log_list.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    log_scroll = tk.Scrollbar(log_frame, command=log_list.yview)
    log_list.config(yscrollcommand=log_scroll.set)

    # Связываем действия
    def add_log(text):
        def _do():
            log_list.insert("end", text)
            log_list.see("end")
        root.after(0, _do)

    def set_status(text):
        root.after(0, lambda: status.config(text=text))

    def set_progress(cur, total):
        def _do():
            progress["maximum"] = max(1, total)
            progress["value"] = cur
        root.after(0, _do)

    def start():
        if state["running"]:
            return
        in_dir = state["in_dir"].get().strip()
        out_dir = state["out_dir"].get().strip()
        if not in_dir or not os.path.isdir(in_dir):
            messagebox.showwarning("Внимание", "Выберите существующую входную папку.")
            return
        if not out_dir:
            messagebox.showwarning("Внимание", "Выберите папку для сохранения.")
            return
        os.makedirs(out_dir, exist_ok=True)

        state["running"] = True
        state["stop"] = False
        start_btn.config(state="disabled")
        stop_btn.config(state="normal")
        log_list.delete(0, "end")
        progress["value"] = 0

        threading.Thread(
            target=_worker,
            args=(app, state, in_dir, out_dir,
                  add_log, set_status, set_progress,
                  lambda: (start_btn.config(state="normal"),
                           stop_btn.config(state="disabled"),
                           setattr(state, "running", False))),
            daemon=True,
        ).start()

    def stop():
        state["stop"] = True
        add_log("⏹ Запрошена остановка…")

    start_btn.config(command=start)
    stop_btn.config(command=stop)

    return root


# ==============================================================
def _row_label(parent, text, p):
    tk.Label(parent, text=text,
             bg=p["surface"] if parent.cget("bg") == p["surface"] else p["bg"],
             fg=p["text_faint"],
             font=("Segoe UI", 8, "bold"),
             anchor="w").pack(fill=tk.X, padx=18, pady=(12, 4))


def _pick_dir(var):
    d = filedialog.askdirectory()
    if d:
        var.set(d)


def _worker(app, state, in_dir, out_dir, add_log, set_status, set_progress,
            on_done):
    try:
        # Собираем задания: список (name, [4 пути])
        jobs = _collect_jobs(state, in_dir, add_log)
        total = len(jobs)
        if total == 0:
            add_log("Не найдено папок с 4+ изображениями.")
            set_status("Нечего обрабатывать.")
            return

        add_log(f"Найдено заданий: {total}")
        set_status(f"Обработка 0/{total}")
        set_progress(0, total)

        done = 0
        ok = 0
        failed = 0
        for name, photos in jobs:
            if state["stop"]:
                add_log("⏹ Остановлено пользователем.")
                break
            out_path = os.path.join(out_dir, f"{name}.jpg")
            if os.path.exists(out_path) and not state["overwrite"].get():
                add_log(f"· {name}.jpg — пропущено (уже есть)")
                done += 1
                set_progress(done, total)
                continue

            try:
                img = build_collage(photos, app.config, for_preview=False)
                img = app.apply_collage_hooks(img, for_preview=False)
                img.save(out_path, "JPEG",
                         quality=int(app.config.get("quality", 92)),
                         optimize=True)
                add_log(f"✓ {name}.jpg  ({img.width}×{img.height})")
                ok += 1
            except Exception as e:
                add_log(f"✗ {name}: {e}")
                failed += 1
            done += 1
            set_progress(done, total)
            set_status(f"Обработка {done}/{total}")

        add_log(f"— Готово: успешно {ok}, ошибок {failed}")
        set_status(f"Завершено: {ok} из {total}")

    except Exception as e:
        add_log(f"❌ Критическая ошибка: {e}")
    finally:
        on_done()


def _collect_jobs(state, in_dir, add_log):
    """Возвращает список (имя, [пути 4 файлов])."""
    jobs = []

    def scan(folder, prefix=""):
        try:
            files = sorted(
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if os.path.isfile(os.path.join(folder, f))
                and os.path.splitext(f)[1].lower() in IMAGE_EXTS
            )
        except Exception as e:
            add_log(f"· Не прочитано: {folder} ({e})")
            return

        # Папка целиком как одно задание (если 4+ фото)
        if len(files) >= 4:
            name = os.path.basename(folder) or "root"
            if prefix:
                name = f"{prefix}_{name}"
            # Обрабатываем по 4 фото за раз
            for i in range(0, len(files) - 3, 4):
                chunk = files[i:i + 4]
                if len(chunk) == 4:
                    jobs.append((f"{name}_{i // 4 + 1:02d}", chunk))

    if state["recursive"].get():
        for root, dirs, _files in os.walk(in_dir):
            scan(root)
    else:
        scan(in_dir)

    return jobs