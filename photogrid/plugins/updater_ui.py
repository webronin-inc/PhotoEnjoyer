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
    """Публичная точка входа — для значка обновления в рельсе."""
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
        self.top.geometry("680x760")
        self.top.minsize(620, 620)
        self.top.resizable(True, True)
        self.top.transient(app.root)
        self.top.grab_set()

        self.top.protocol("WM_DELETE_WINDOW", self._on_close_request)

        # ============ ШАПКА (не растягивается) ============
        self._build_header()

        # ============ НИЖНИЙ БЛОК КНОПОК (прижат к низу) ============
        # ВАЖНО: строим его вторым, чтобы он занял место снизу,
        # а скроллируемая часть растянулась в остатке.
        self._build_footer()

        # ============ ЦЕНТР: notes + прогресс (растягивается) ============
        self._build_body()

        self._installing = False

    # ---------------------------------------------------------------
    def _build_header(self):
        p = self.app.palette

        head = tk.Frame(self.top, bg=p["surface"])
        head.pack(fill=tk.X, padx=24, pady=(20, 8))

        # Иконка
        icon = tk.Canvas(head, width=52, height=52, bg=p["surface"],
                         highlightthickness=0)
        icon.pack(side=tk.LEFT, padx=(0, 14))
        icon.create_oval(2, 2, 50, 50, fill=ACCENT, outline="")
        icon.create_text(26, 26, text="↑", fill="#ffffff",
                         font=("Segoe UI", 22, "bold"))

        # Тексты
        head_text = tk.Frame(head, bg=p["surface"])
        head_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(head_text,
                 text=f"{branding.APP_NAME}: доступно обновление",
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 15, "bold"),
                 anchor="w").pack(fill=tk.X)
        tk.Label(head_text,
                 text=f"Версия {self.info['remote']}  ·  "
                      f"дата выхода: {self.info.get('release_date') or '—'}",
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 10), anchor="w").pack(fill=tk.X)

        # Чипы версий
        vers = tk.Frame(self.top, bg=p["surface"])
        vers.pack(fill=tk.X, padx=24, pady=(10, 4))
        self._version_chip(vers, "Сейчас", self.info["current"], muted=True)
        tk.Label(vers, text="→", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT, padx=14)
        self._version_chip(vers, "Новая", self.info["remote"], muted=False)

    # ---------------------------------------------------------------
    def _build_body(self):
        """Notes + прогресс-полоса + статус — растягиваемая часть."""
        p = self.app.palette

        body = tk.Frame(self.top, bg=p["surface"])
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(16, 8))

        # Заголовок «Что нового»
        tk.Label(body, text="Что нового",
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 11, "bold"),
                 anchor="w").pack(fill=tk.X, pady=(0, 6))

        # --- Notes: скроллируемый блок с ограниченной высотой ---
        notes_outer = tk.Frame(body, bg=p["surface_alt"], bd=0)
        notes_outer.pack(fill=tk.BOTH, expand=True)

        # Canvas + scrollbar + Text внутри — чтобы notes не растягивал окно
        notes_canvas = tk.Canvas(notes_outer, bg=p["surface_alt"],
                                 highlightthickness=0, height=240)
        notes_scroll = tk.Scrollbar(notes_outer, orient="vertical",
                                    command=notes_canvas.yview)
        notes_text = tk.Text(
            notes_canvas, wrap="word", bd=0,
            bg=p["surface_alt"], fg=p["text"],
            font=("Segoe UI", 10), padx=14, pady=12,
            highlightthickness=0, height=10,
            yscrollcommand=notes_scroll.set,
        )
        notes_text.insert("1.0", self.info.get("notes") or "Обновление без описания.")
        notes_text.config(state="disabled")

        notes_canvas.create_window((0, 0), window=notes_text, anchor="nw")
        notes_canvas.configure(yscrollcommand=notes_scroll.set)

        def _on_text_configure(_):
            notes_canvas.configure(scrollregion=notes_canvas.bbox("all"))

        def _on_canvas_configure(e):
            notes_canvas.itemconfigure("all", width=e.width)

        notes_text.bind("<Configure>", _on_text_configure)
        notes_canvas.bind("<Configure>", _on_canvas_configure)

        notes_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        notes_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Колесо мыши внутри notes
        try:
            from ..ui_widgets import enable_mousewheel
            enable_mousewheel(notes_canvas)
        except Exception:
            pass

        # --- Прогресс ---
        prog_frame = tk.Frame(body, bg=p["surface"])
        prog_frame.pack(fill=tk.X, pady=(16, 4))

        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                        style="Update.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X)

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

        # --- Статус ---
        self.status = tk.Label(body, text="", bg=p["surface"],
                               fg=p["text_dim"], font=("Segoe UI", 9),
                               anchor="w")
        self.status.pack(fill=tk.X, pady=(0, 2))

        if not updater.is_frozen():
            self.status.config(
                text="Запущено из исходников: будет обновлён только manifest."
            )

    # ---------------------------------------------------------------
    def _build_footer(self):
        """Кнопки — всегда прижаты к низу окна, не скроллятся."""
        p = self.app.palette

        # Разделитель
        tk.Frame(self.top, bg=p["border_soft"], height=1).pack(
            side=tk.BOTTOM, fill=tk.X)

        footer = tk.Frame(self.top, bg=p["surface"])
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=(12, 20))

        # Правая сторона: главные кнопки
        right = tk.Frame(footer, bg=p["surface"])
        right.pack(side=tk.RIGHT)

        self.install_btn = ttk.Button(
            right, text="Обновить сейчас",
            style="Accent.TButton",
            command=self._install,
        )
        self.install_btn.pack(side=tk.RIGHT)

        self.later_btn = ttk.Button(
            right, text="Позже",
            command=self.top.destroy,
        )
        self.later_btn.pack(side=tk.RIGHT, padx=(0, 10))

        # Левая сторона: ссылка на проект
        homepage = self.info.get("homepage") or branding.APP_HOMEPAGE
        if homepage:
            ttk.Button(footer, text="Открыть страницу проекта",
                       command=lambda: _open_url(homepage)
                       ).pack(side=tk.LEFT)

    # ---------------------------------------------------------------
    def _version_chip(self, parent, label, version, muted):
        p = self.app.palette
        box = tk.Frame(parent, bg=p["surface_alt"])
        box.pack(side=tk.LEFT)

        tk.Label(box, text=label, bg=p["surface_alt"], fg=p["text_dim"],
                 font=("Segoe UI", 8), padx=12, pady=(6, 0),
                 anchor="w").pack(fill=tk.X)

        tk.Label(box, text=version, bg=p["surface_alt"],
                 fg=p["text_dim"] if muted else ACCENT,
                 font=("Segoe UI", 13, "bold"), padx=12, pady=(0, 6),
                 anchor="w").pack(fill=tk.X)

    # ---------------------------------------------------------------
    def _on_close_request(self):
        if self._installing:
            return   # нельзя прервать установку
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

                self._status("Запуск установщика…")
                time.sleep(0.5)
                updater.run_installer_and_exit(tmp_setup, self.app)
                return
            else:
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

            self.top.after(0, lambda: self._apply_progress(pct if total else 0, text))

        updater.download_file(url, dest, progress_cb=progress)
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