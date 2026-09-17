"""UI для системы обновлений — красивое окно с прогрессом."""
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .. import branding
from .. import updater
from ..version import __version__


# Цвета для карточек/акцентов
ACCENT = "#7c5cff"
ACCENT_HOVER = "#917aff"
SUCCESS = "#3ddc84"
TEXT_DIM = "#7e7e9c"


def register(app):
    _ensure_defaults(app)
    app.add_menu_item("Справка", "Проверить обновления…", lambda: _check(app))
    app.add_menu_item("Справка", "Настройки обновлений…", lambda: _settings(app))
    app.plugin_flags["updater_ui"] = True


def _ensure_defaults(app):
    u = app.config.data.setdefault("updates", {})
    u.setdefault("manifest_url", updater.DEFAULT_MANIFEST_URL)
    u.setdefault("auto_check", True)
    u.setdefault("auto_install_plugins", True)


# ---------- Проверка ----------
def _check(app, silent=False):
    def done(info, err):
        if err == "url_not_configured":
            if not silent:
                messagebox.showinfo(
                    f"Обновления — {branding.APP_NAME}",
                    "URL манифеста обновлений не настроен.\n\n"
                    "Откройте «Справка → Настройки обновлений…» и укажите адрес\n"
                    "вашего manifest.json."
                )
            return
        if err:
            if not silent:
                messagebox.showerror(
                    f"Обновления — {branding.APP_NAME}",
                    f"Не удалось проверить обновления:\n{err}"
                )
            app.set_status("Ошибка проверки обновлений")
            return
        _show_result(app, info, silent)

    updater.perform_check(app, silent=silent, on_done=done)


def _show_result(app, info, silent):
    if not info["available"]:
        app.set_status(f"Обновлений нет (версия {info['current']})")
        if not silent:
            messagebox.showinfo(
                f"Обновления — {branding.APP_NAME}",
                f"У вас последняя версия: {info['current']}"
            )
        return

    app.set_status(f"Доступна новая версия {info['remote']}")
    if not silent:
        _UpdateDialog(app, info)


def open_update_dialog(app):
    """Публичная точка входа — для бейджика из auto_updater."""
    info = updater.get_pending()
    if info:
        _UpdateDialog(app, info)
    else:
        _check(app, silent=False)


# =====================================================================
#  Главное окно «Доступно обновление»
# =====================================================================
class _UpdateDialog:
    def __init__(self, app, info):
        self.app = app
        self.info = info
        p = app.palette

        self.top = tk.Toplevel(app.root)
        self.top.title(f"Обновление — {branding.APP_NAME}")
        self.top.configure(bg=p["surface"])
        self.top.geometry("580x560")
        self.top.resizable(False, False)
        self.top.transient(app.root)
        self.top.grab_set()

        # Закрытие крестиком = «Позже», но запрещаем во время установки
        self.top.protocol("WM_DELETE_WINDOW", self._on_close_request)

        # --- Шапка: иконка + название ---
        head = tk.Frame(self.top, bg=p["surface"])
        head.pack(fill=tk.X, padx=24, pady=(20, 8))

        # Простая «иконка» кружком
        icon = tk.Canvas(head, width=48, height=48, bg=p["surface"],
                         highlightthickness=0)
        icon.pack(side=tk.LEFT, padx=(0, 14))
        icon.create_oval(2, 2, 46, 46, fill=ACCENT, outline="")
        icon.create_text(24, 24, text="↑", fill="#ffffff",
                         font=("Segoe UI", 20, "bold"))

        head_text = tk.Frame(head, bg=p["surface"])
        head_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(head_text,
                 text=f"{branding.APP_NAME}: обновление",
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 14, "bold"),
                 anchor="w").pack(fill=tk.X)
        tk.Label(head_text,
                 text=f"Версия {info['remote']}  ·  сегодня",
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)

        # --- Блок версий ---
        vers = tk.Frame(self.top, bg=p["surface"])
        vers.pack(fill=tk.X, padx=24, pady=(10, 4))

        self._version_chip(vers, "Сейчас", info["current"], muted=True)
        tk.Label(vers, text="→", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=12)
        self._version_chip(vers, "Новая", info["remote"], muted=False)

        # --- Notes ---
        tk.Label(self.top, text="Что нового", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill=tk.X, padx=24, pady=(18, 4))

        notes_frame = tk.Frame(self.top, bg=p["surface_alt"], bd=0)
        notes_frame.pack(fill=tk.BOTH, expand=True, padx=24)

        notes = tk.Text(notes_frame, height=9, wrap="word", bd=0,
                        bg=p["surface_alt"], fg=p["text"],
                        font=("Segoe UI", 10), padx=12, pady=10,
                        highlightthickness=0)
        notes.insert("1.0", info.get("notes") or "Обновление без описания.")
        notes.config(state="disabled")
        notes.pack(fill=tk.BOTH, expand=True)

        # --- Статус / прогресс ---
        self.progress_frame = tk.Frame(self.top, bg=p["surface"])
        self.progress_frame.pack(fill=tk.X, padx=24, pady=(14, 0))

        self.progress = ttk.Progressbar(self.progress_frame, mode="determinate",
                                        style="Update.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X)

        # Стиль прогресс-бара под акцентный цвет
        style = ttk.Style()
        try:
            style.configure("Update.Horizontal.TProgressbar",
                            troughcolor=p["surface_alt"],
                            background=ACCENT,
                            bordercolor=p["surface_alt"],
                            lightcolor=ACCENT,
                            darkcolor=ACCENT)
        except Exception:
            pass

        self.status = tk.Label(self.top, text="", bg=p["surface"],
                               fg=p["text_dim"], font=("Segoe UI", 9),
                               anchor="w")
        self.status.pack(fill=tk.X, padx=24, pady=(4, 0))

        # --- Кнопки ---
        bf = tk.Frame(self.top, bg=p["surface"])
        bf.pack(fill=tk.X, padx=24, pady=(16, 20))

        self.install_btn = ttk.Button(bf, text="Обновить сейчас",
                                      style="Accent.TButton",
                                      command=self._install)
        self.install_btn.pack(side=tk.RIGHT)

        self.later_btn = ttk.Button(bf, text="Позже", command=self.top.destroy)
        self.later_btn.pack(side=tk.RIGHT, padx=(0, 10))

        homepage = info.get("homepage") or branding.APP_HOMEPAGE
        if homepage:
            ttk.Button(bf, text="Открыть страницу",
                       command=lambda: _open_url(homepage)
                       ).pack(side=tk.LEFT)

        if not updater.is_frozen():
            self.status.config(
                text="Запущено из исходников: будет обновлён только manifest."
            )

        self._installing = False

    def _version_chip(self, parent, label, version, muted):
        p = self.app.palette
        box = tk.Frame(parent, bg=p["surface_alt"])
        box.pack(side=tk.LEFT)

        tk.Label(box, text=label, bg=p["surface_alt"], fg=p["text_dim"],
                 font=("Segoe UI", 8),
                 anchor="w").pack(fill=tk.X, padx=10, pady=(6, 0))

        tk.Label(box, text=version, bg=p["surface_alt"],
                 fg=p["text_dim"] if muted else ACCENT,
                 font=("Segoe UI", 12, "bold"),
                 anchor="w").pack(fill=tk.X, padx=10, pady=(0, 6))

    def _on_close_request(self):
        if self._installing:
            # Во время установки крестик не работает — только через кнопки
            return
        self.top.destroy()

    # ---------- Установка ----------
    def _install(self):
        self._installing = True
        self.install_btn.config(state="disabled")
        self.later_btn.config(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        info = self.info
        try:
            # 1) Плагины
            if info["plugins"] and self.app.config.data["updates"].get("auto_install_plugins"):
                self._status("Обновление плагинов…")
                reports = updater.apply_plugin_updates(
                    info["plugins"], progress_cb=self._progress_cb)
                ok = sum(1 for r in reports if r["ok"])
                self._status(f"Плагины обновлены: {ok}/{len(reports)}")

            # 2) Скачивание установщика
            if updater.is_frozen() and info["download_url"]:
                import tempfile
                from pathlib import Path

                tmp_dir = Path(tempfile.gettempdir())
                setup_name = f"{branding.APP_NAME}-Setup-{info['remote']}.exe"
                tmp_setup = tmp_dir / setup_name

                self._status("Подключение к серверу…")
                self._download_with_ui(info["download_url"], tmp_setup)

                # Проверка sha256
                if info.get("sha256"):
                    self._status("Проверка целостности…")
                    if not updater.verify_sha256(tmp_setup, info["sha256"]):
                        raise ValueError("sha256 не совпадает — файл повреждён")

                # Запуск установщика
                self._status("Запуск установщика…")
                time.sleep(0.5)
                updater.run_installer_and_exit(tmp_setup, self.app)
                return
            else:
                # Запуск из исходников — покажем результат
                self._status("Готово. Перезапустите приложение вручную.")
                self.app.root.after(1500, self.top.destroy)
                return

        except Exception as e:
            self._status(f"Ошибка: {e}")
            self.install_btn.config(state="normal")
            self.later_btn.config(state="normal")
            self._installing = False

    def _download_with_ui(self, url, dest):
        """Скачивает файл, показывая проценты, МБ и скорость."""
        from pathlib import Path
        dest.parent.mkdir(parents=True, exist_ok=True)

        start = time.time()
        last_update = [0.0]

        def progress(got, total):
            now = time.time()
            # Обновляем UI не чаще 10 раз в секунду
            if now - last_update[0] < 0.1:
                return
            last_update[0] = now

            elapsed = now - start
            speed = got / elapsed if elapsed > 0 else 0

            if total:
                pct = int(got / total * 100)
                text = (f"{pct}%  ·  {got/1048576:.1f} МБ / "
                        f"{total/1048576:.1f} МБ  ·  {speed/1048576:.1f} МБ/с")
            else:
                text = f"{got/1048576:.1f} МБ  ·  {speed/1048576:.1f} МБ/с"

            self.top.after(0, lambda: self._apply_progress(pct if total else 0,
                                                           text))

        updater.download_file(url, dest, progress_cb=progress)

        # Финальная отрисовка
        self.top.after(0, lambda: self._apply_progress(100, "Готово"))

    def _apply_progress(self, pct, text):
        try:
            self.progress["value"] = pct
            self.status.config(text=text)
        except tk.TclError:
            pass

    def _progress_cb(self, got, total):
        if not total:
            return
        pct = int(got / total * 100)
        self.top.after(0, lambda: self.progress.config(value=pct))

    def _status(self, text):
        try:
            self.top.after(0, lambda: self.status.config(text=text))
        except tk.TclError:
            pass


def _open_url(url):
    import webbrowser
    webbrowser.open(url)


# =====================================================================
#  Настройки обновлений
# =====================================================================
def _settings(app):
    p = app.palette
    top = tk.Toplevel(app.root)
    top.title(f"Настройки обновлений — {branding.APP_NAME}")
    top.configure(bg=p["surface"])
    top.geometry("560x300")
    top.resizable(False, False)
    top.transient(app.root)
    top.grab_set()

    u = app.config.data["updates"]
    url_var = tk.StringVar(value=u.get("manifest_url", ""))
    auto_var = tk.BooleanVar(value=bool(u.get("auto_check")))
    plugins_var = tk.BooleanVar(value=bool(u.get("auto_install_plugins")))

    tk.Label(top, text="URL манифеста обновлений",
             bg=p["surface"], fg=p["text"],
             font=("Segoe UI", 10, "bold")
             ).pack(anchor="w", padx=20, pady=(18, 4))
    ttk.Entry(top, textvariable=url_var).pack(fill=tk.X, padx=20)

    tk.Label(top, text=f"Текущая версия: {__version__}",
             bg=p["surface"], fg=p["text_dim"], font=("Segoe UI", 9)
             ).pack(anchor="w", padx=20, pady=(6, 0))

    ttk.Checkbutton(top, text="Проверять обновления при запуске",
                    variable=auto_var).pack(anchor="w", padx=20, pady=(14, 4))
    ttk.Checkbutton(top, text="Автоматически устанавливать обновления плагинов",
                    variable=plugins_var).pack(anchor="w", padx=20)

    def save():
        u["manifest_url"] = url_var.get().strip()
        u["auto_check"] = bool(auto_var.get())
        u["auto_install_plugins"] = bool(plugins_var.get())
        app.config.save()
        top.destroy()
        app.set_status("Настройки обновлений сохранены")

    bf = tk.Frame(top, bg=p["surface"])
    bf.pack(fill=tk.X, padx=20, pady=20)
    ttk.Button(bf, text="Сохранить", style="Accent.TButton",
               command=save).pack(side=tk.RIGHT)
    ttk.Button(bf, text="Отмена", command=top.destroy
               ).pack(side=tk.RIGHT, padx=(0, 8))