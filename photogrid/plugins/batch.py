"""Пакетная обработка папок: для каждой подпапки — коллаж из первых 4 фото."""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import IMAGE_EXTS
from ..core import build_collage


def register(app):
    app.add_menu_item("Файл", "Пакетная обработка папок…", lambda: _BatchDialog(app))
    app.plugin_flags["batch"] = True


class _BatchDialog:
    def __init__(self, app):
        self.app = app
        self.stop_flag = False
        p = app.palette

        self.top = tk.Toplevel(app.root)
        self.top.title("Пакетная обработка")
        self.top.configure(bg=p["surface"])
        self.top.geometry("640x600")
        self.top.transient(app.root)
        self.top.grab_set()
        pad = {"padx": 16, "pady": 6}

        tk.Label(self.top, text="Входная папка:", bg=p["surface"], fg=p["text"]
                 ).pack(anchor="w", **pad)
        row = tk.Frame(self.top, bg=p["surface"]); row.pack(fill=tk.X, padx=16)
        self.in_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.in_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="…", width=3, command=self._pick_in).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(self.top, text="Куда сохранять:", bg=p["surface"], fg=p["text"]
                 ).pack(anchor="w", **pad)
        row = tk.Frame(self.top, bg=p["surface"]); row.pack(fill=tk.X, padx=16)
        self.out_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.out_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="…", width=3, command=self._pick_out).pack(side=tk.LEFT, padx=(6, 0))

        self.flat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.top, text="Также разбить файлы в корне папки по 4 шт.",
                        variable=self.flat_var).pack(anchor="w", **pad)

        tk.Label(self.top, text="Прогресс:", bg=p["surface"], fg=p["text"]
                 ).pack(anchor="w", **pad)
        self.log = tk.Listbox(self.top, bg=p["surface_alt"], fg=p["text"],
                              bd=0, highlightthickness=0, font=("Segoe UI", 9))
        self.log.pack(fill=tk.BOTH, expand=True, padx=16)

        self.progress = ttk.Progressbar(self.top, mode="determinate")
        self.progress.pack(fill=tk.X, padx=16, pady=(6, 0))

        bf = tk.Frame(self.top, bg=p["surface"]); bf.pack(fill=tk.X, padx=16, pady=12)
        self.start_btn = ttk.Button(bf, text="Запустить", style="Accent.TButton",
                                    command=self._start)
        self.start_btn.pack(side=tk.RIGHT)
        self.close_btn = ttk.Button(bf, text="Закрыть", command=self._close)
        self.close_btn.pack(side=tk.RIGHT, padx=(0, 8))

    def _pick_in(self):
        d = filedialog.askdirectory(title="Входная папка", parent=self.top)
        if d:
            self.in_var.set(d)
            if not self.out_var.get():
                self.out_var.set(os.path.join(d, "_collages"))

    def _pick_out(self):
        d = filedialog.askdirectory(title="Куда сохранять", parent=self.top)
        if d:
            self.out_var.set(d)

    def _close(self):
        if self.start_btn["state"] == "disabled":
            self.stop_flag = True
            self._log("⏹ Запрошена остановка…")
        else:
            self.top.destroy()

    def _log(self, msg):
        self.top.after(0, lambda: (self.log.insert("end", msg), self.log.see("end")))

    def _start(self):
        src, out = self.in_var.get().strip(), self.out_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showwarning("Внимание", "Выберите существующую входную папку", parent=self.top)
            return
        if not out:
            messagebox.showwarning("Внимание", "Выберите папку для сохранения", parent=self.top)
            return
        os.makedirs(out, exist_ok=True)
        self.start_btn.config(state="disabled")
        self.stop_flag = False
        self.log.delete(0, "end")
        threading.Thread(target=self._run, args=(src, out), daemon=True).start()

    def _run(self, src, out):
        try:
            jobs = self._collect_jobs(src)
            total = len(jobs)
            self._set_progress(0, total)
            done = 0
            for name, photos in jobs:
                if self.stop_flag:
                    self._log("⏹ Остановлено пользователем")
                    break
                try:
                    img = build_collage(photos, self.app.config, for_preview=False)
                    img = self.app.apply_collage_hooks(img, for_preview=False)
                    path = os.path.join(out, f"{name}.jpg")
                    img.save(path, "JPEG", quality=int(self.app.config["quality"]), optimize=True)
                    self._log(f"✓ {name}  ({img.width}×{img.height})")
                except Exception as e:
                    self._log(f"✗ {name}: {e}")
                done += 1
                self._set_progress(done, total)
            self._log(f"— Готово: {done}/{total}")
        except Exception as e:
            self._log(f"Ошибка: {e}")
        finally:
            self.top.after(0, lambda: self.start_btn.config(state="normal"))

    def _collect_jobs(self, src):
        jobs = []
        if self.flat_var.get():
            files = sorted(
                os.path.join(src, f) for f in os.listdir(src)
                if os.path.isfile(os.path.join(src, f))
                and os.path.splitext(f)[1].lower() in IMAGE_EXTS
            )
            for i in range(0, len(files) - 3, 4):
                chunk = files[i:i+4]
                if len(chunk) == 4:
                    jobs.append((f"{os.path.basename(src)}_batch{i//4+1}", chunk))
        for name in sorted(os.listdir(src)):
            sub = os.path.join(src, name)
            if not os.path.isdir(sub):
                continue
            files = sorted(
                os.path.join(sub, f) for f in os.listdir(sub)
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS
            )
            if len(files) < 4:
                self._log(f"· пропуск {name}: найдено {len(files)} фото")
                continue
            jobs.append((name, files[:4]))
        return jobs

    def _set_progress(self, done, total):
        def upd():
            self.progress["maximum"] = max(1, total)
            self.progress["value"] = done
        self.top.after(0, upd)