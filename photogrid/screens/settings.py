"""Модальное окно настроек приложения."""
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .. import branding, updater
from ..version import __version__, __release_date__


def open_settings_dialog(app):
    SettingsDialog(app)


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        self.config = app.config
        self.p = app.palette

        self.top = tk.Toplevel(app.root)
        self.top.title(f"Настройки — {branding.APP_NAME}")
        self.top.configure(bg=self.p["surface"])
        self.top.geometry("580x720")
        self.top.resizable(False, False)
        self.top.transient(app.root)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()

    # ==========================================================
    def _build(self):
        p = self.p

        # ---------- Шапка ----------
        head = tk.Frame(self.top, bg=p["surface"])
        head.pack(fill=tk.X, padx=24, pady=(22, 8))

        logo = tk.Canvas(head, width=52, height=52,
                         bg=p["surface"], highlightthickness=0)
        logo.pack(side=tk.LEFT)
        from ..ui_widgets import rounded_rect
        rounded_rect(logo, 0, 0, 52, 52, radius=14,
                     fill=p["accent"], outline="")
        logo.create_text(26, 27, text="P", fill="#ffffff",
                         font=("Segoe UI", 24, "bold"))

        title_box = tk.Frame(head, bg=p["surface"])
        title_box.pack(side=tk.LEFT, padx=(14, 0), fill=tk.X, expand=True)

        tk.Label(title_box, text=branding.APP_NAME,
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 16, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(title_box, text=f"версия {__version__}  ·  {__release_date__}",
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)

        copy_btn = tk.Label(head, text="⧉",
                            bg=p["surface"], fg=p["text_faint"],
                            font=("Segoe UI", 12), cursor="hand2")
        copy_btn.pack(side=tk.RIGHT, padx=(8, 0))
        copy_btn.bind("<Button-1>", lambda e: self._copy_version())
        copy_btn.bind("<Enter>", lambda e: copy_btn.config(fg=p["accent"]))
        copy_btn.bind("<Leave>", lambda e: copy_btn.config(fg=p["text_faint"]))

        # ---------- Скроллируемый контент ----------
        body_wrap = tk.Frame(self.top, bg=p["surface"])
        body_wrap.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(body_wrap, bg=p["surface"], highlightthickness=0)
        scroll = tk.Scrollbar(body_wrap, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=p["surface"])

        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        from ..ui_widgets import enable_mousewheel
        enable_mousewheel(canvas)

        # ============ ВНЕШНИЙ ВИД ============
        self._section(body, "Внешний вид")

        theme_row = tk.Frame(body, bg=p["surface"])
        theme_row.pack(fill=tk.X, padx=24, pady=(0, 4))
        tk.Label(theme_row, text="Тема приложения",
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)

        self.theme_var = tk.StringVar(value=self.config.get("theme", "dark"))
        theme_btns = tk.Frame(theme_row, bg=p["surface"])
        theme_btns.pack(side=tk.RIGHT)
        ttk.Radiobutton(theme_btns, text="Тёмная",
                        variable=self.theme_var, value="dark"
                        ).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Radiobutton(theme_btns, text="Светлая",
                        variable=self.theme_var, value="light"
                        ).pack(side=tk.LEFT)

        tk.Label(body, text="Тема применится мгновенно после сохранения",
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 8), anchor="w"
                 ).pack(fill=tk.X, padx=24, pady=(0, 8))

        # ============ ОБНОВЛЕНИЯ ============
        self._divider(body)
        self._section(body, "Обновления")

        u = self.config.data.setdefault("updates", {})
        self.auto_check_var = tk.BooleanVar(value=bool(u.get("auto_check", True)))
        self.auto_plugins_var = tk.BooleanVar(
            value=bool(u.get("auto_install_plugins", True)))

        ttk.Checkbutton(body, text="Проверять обновления при запуске",
                        variable=self.auto_check_var).pack(
            anchor="w", padx=24, pady=(0, 4))
        ttk.Checkbutton(body, text="Автоматически устанавливать плагины",
                        variable=self.auto_plugins_var).pack(
            anchor="w", padx=24, pady=(0, 8))

        # Только одна кнопка — проверить сейчас. URL не показываем.
        btn_row = tk.Frame(body, bg=p["surface"])
        btn_row.pack(fill=tk.X, padx=24, pady=(0, 4))
        self._flat_button(btn_row, "Проверить обновления сейчас",
                          self._check_updates).pack(side=tk.LEFT)

        # ============ ДАННЫЕ ============
        self._divider(body)
        self._section(body, "Данные")

        data_row = tk.Frame(body, bg=p["surface"])
        data_row.pack(fill=tk.X, padx=24, pady=(0, 4))
        self._flat_button(data_row, "Открыть папку данных",
                          self._open_data_dir).pack(side=tk.LEFT)
        self._flat_button(data_row, "Очистить кэш",
                          self._clear_cache).pack(side=tk.LEFT, padx=(8, 0))

        # ============ БУФЕР ОБМЕНА ============
        self._divider(body)
        self._section(body, "Копирование")

        tk.Label(body,
                 text="Скопировать готовый коллаж в буфер обмена,\n"
                      "чтобы вставить его в другую программу.",
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), justify="left", anchor="w"
                 ).pack(fill=tk.X, padx=24, pady=(0, 6))

        self._flat_button(body, "Скопировать текущий коллаж в буфер",
                          self._copy_collage).pack(anchor="w", padx=24, pady=(0, 4))

        # ============ ПЛАГИНЫ ============
        self._divider(body)
        self._section(body, "Плагины")

        plugins = list(self.app.plugin_flags.keys())
        if plugins:
            tk.Label(body, text=f"{len(plugins)} активно",
                     bg=p["surface"], fg=p["text"],
                     font=("Segoe UI", 9, "bold"), anchor="w"
                     ).pack(fill=tk.X, padx=24, pady=(0, 2))
            tk.Label(body, text=" · ".join(plugins),
                     bg=p["surface"], fg=p["text_dim"],
                     font=("Segoe UI", 9), wraplength=520,
                     justify="left", anchor="w"
                     ).pack(fill=tk.X, padx=24, pady=(0, 4))

        # ============ СБРОС ============
        self._divider(body)
        self._section(body, "Сброс")

        self._flat_button(body, "Сбросить все настройки",
                          self._reset_settings,
                          danger=True).pack(anchor="w", padx=24, pady=(0, 4))

        # ============ О ПРОГРАММЕ ============
        self._divider(body)
        self._section(body, "О программе")

        about_lines = [
            f"{branding.APP_NAME} · {branding.APP_TAGLINE}",
            f"© {branding.APP_PUBLISHER}",
            "Python · Tkinter · Pillow",
        ]
        for line in about_lines:
            tk.Label(body, text=line,
                     bg=p["surface"], fg=p["text_dim"],
                     font=("Segoe UI", 9),
                     anchor="w").pack(fill=tk.X, padx=24, pady=(0, 2))

        if branding.APP_HOMEPAGE:
            link_row = tk.Frame(body, bg=p["surface"])
            link_row.pack(fill=tk.X, padx=24, pady=(8, 4))
            self._flat_button(link_row, "Открыть страницу проекта",
                              lambda: self._open_url(branding.APP_HOMEPAGE)
                              ).pack(side=tk.LEFT)

        tk.Frame(body, bg=p["surface"], height=16).pack()

        # ---------- Кнопки внизу ----------
        bottom = tk.Frame(self.top, bg=p["surface"])
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=24, pady=(0, 20))
        tk.Frame(bottom, bg=p["border_soft"], height=1).pack(
            fill=tk.X, pady=(0, 14))
        ttk.Button(bottom, text="Отмена",
                   command=self._on_cancel).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bottom, text="Сохранить", style="Accent.TButton",
                   command=self._save).pack(side=tk.RIGHT)

    # ==========================================================
    def _section(self, parent, text):
        p = self.p
        tk.Label(parent, text=text.upper(),
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill=tk.X, padx=24, pady=(6, 8))

    def _divider(self, parent):
        p = self.p
        tk.Frame(parent, bg=p["border_soft"], height=1
                 ).pack(fill=tk.X, padx=24, pady=(16, 12))

    def _flat_button(self, parent, text, command, danger=False):
        p = self.p
        fg = p["danger"] if danger else p["text"]
        return tk.Button(parent, text=text,
                         bg=p["surface_alt"], fg=fg,
                         activebackground=p["surface_hi"],
                         activeforeground=fg,
                         bd=0, relief="flat", cursor="hand2",
                         font=("Segoe UI", 9),
                         padx=12, pady=6,
                         command=command)

    # ==========================================================
    def _copy_version(self):
        try:
            self.top.clipboard_clear()
            self.top.clipboard_append(__version__)
            self.app.set_status(f"Версия {__version__} скопирована")
        except Exception:
            pass

    def _open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def _check_updates(self):
        self._persist_non_theme_settings()
        try:
            from ..plugins import updater_ui
            updater_ui._check(self.app, silent=False)
        except Exception as e:
            messagebox.showerror("Ошибка",
                                 f"Не удалось проверить обновления:\n{e}")

    def _copy_collage(self):
        """Собирает текущий коллаж и копирует его в буфер."""
        result = self.app.copy_collage_to_clipboard()
        if result is True:
            messagebox.showinfo("Готово", "Коллаж скопирован в буфер обмена.")
        elif isinstance(result, str):
            messagebox.showerror("Ошибка", result)
        # если result == False — уже показано сообщение

    def _open_data_dir(self):
        try:
            d = updater.user_data_dir()
            d.mkdir(parents=True, exist_ok=True)
            self._open_in_explorer(d)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку:\n{e}")

    def _open_in_explorer(self, path):
        path = str(path)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _clear_cache(self):
        if not messagebox.askyesno("Очистить кэш",
                                   "Удалить временные файлы приложения?"):
            return
        try:
            d = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / branding.APP_SLUG
            removed = 0
            if d.exists():
                for f in d.glob("PhotoEnjoyer-Setup-*.exe"):
                    try:
                        f.unlink()
                        removed += 1
                    except Exception:
                        pass
                for name in ("launch.log", "install.log"):
                    try:
                        (d / name).unlink()
                        removed += 1
                    except Exception:
                        pass
            self.app.set_status(f"Кэш очищен: удалено {removed} файлов")
            messagebox.showinfo("Очистка кэша", f"Удалено файлов: {removed}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось очистить кэш:\n{e}")

    def _reset_settings(self):
        if not messagebox.askyesno(
            "Сброс",
            "Сбросить ВСЕ настройки к значениям по умолчанию?"
        ):
            return
        from ..config import DEFAULTS
        for k, v in DEFAULTS.items():
            if k != "theme":
                self.config[k] = v
        self.config.save()
        self.top.destroy()
        self.app.reload_ui()
        messagebox.showinfo("Готово", "Настройки сброшены.")

    def _persist_non_theme_settings(self):
        u = self.config.data.setdefault("updates", {})
        u["auto_check"] = bool(self.auto_check_var.get())
        u["auto_install_plugins"] = bool(self.auto_plugins_var.get())
        self.config.save()

    def _save(self):
        old_theme = self.config.get("theme", "dark")
        new_theme = self.theme_var.get()
        theme_changed = (old_theme != new_theme)

        self.config["theme"] = new_theme
        self._persist_non_theme_settings()
        self.top.destroy()
        if theme_changed:
            self.app.reload_ui()

    def _on_cancel(self):
        self.top.destroy()

    def _on_close(self):
        self.top.destroy()