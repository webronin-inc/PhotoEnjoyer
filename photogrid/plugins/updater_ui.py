"""UI для системы обновлений."""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .. import branding
from .. import updater
from ..version import __version__


def register(app):
    _ensure_defaults(app)
    app.add_menu_item("Справка", f"Проверить обновления…",
                      lambda: _check(app))
    app.add_menu_item("Справка", f"Настройки обновлений…",
                      lambda: _settings(app))
    app.plugin_flags["updater"] = True




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
            _show_error(app, f"Не удалось проверить обновления:\n{err}", silent)
            return
        _show_result(app, info, silent)

    updater.perform_check(app, silent=silent, on_done=done)

    def worker():
        try:
            manifest = updater.fetch_manifest(url)
            info = updater.analyze(manifest)
            info["_checked_url"] = url
            app.root.after(0, lambda: _show_result(app, info, silent))
        except Exception as e:
            msg = f"Не удалось проверить обновления:\n{e}"
            app.root.after(0, lambda: _show_error(app, msg, silent))

    threading.Thread(target=worker, daemon=True).start()


def _show_error(app, msg, silent):
    app.set_status("Ошибка проверки обновлений")
    if not silent:
        messagebox.showerror(f"Обновления — {branding.APP_NAME}", msg)


def _show_result(app, info, silent):
    if not info["available"]:
        app.set_status(f"Обновлений нет (версия {info['current']})")
        if not silent:
            messagebox.showinfo(
                f"Обновления — {branding.APP_NAME}",
                f"У вас последняя версия: {info['current']}\n\n"
                f"Проверено: {info.get('_checked_url', '')}"
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

# ---------- Диалог обновления ----------
class _UpdateDialog:
    def __init__(self, app, info):
        self.app = app
        self.info = info
        p = app.palette

        self.top = tk.Toplevel(app.root)
        self.top.title(f"Обновление — {branding.APP_NAME}")
        self.top.configure(bg=p["surface"])
        self.top.geometry("560x520")
        self.top.transient(app.root)
        self.top.grab_set()

        tk.Label(self.top,
                 text=f"{branding.APP_NAME}: доступна версия {info['remote']}",
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 14, "bold")
                 ).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(self.top,
                 text=f"Текущая: {info['current']}   •   "
                      f"Дата: {info['release_date'] or '—'}",
                 bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9)
                 ).pack(anchor="w", padx=20)

        tk.Label(self.top, text="Что нового:", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", padx=20, pady=(14, 4))

        notes = tk.Text(self.top, height=10, wrap="word", bd=0,
                        bg=p["surface_alt"], fg=p["text"],
                        font=("Segoe UI", 10), padx=10, pady=8)
        notes.insert("1.0", info["notes"] or "—")
        notes.config(state="disabled")
        notes.pack(fill=tk.BOTH, expand=True, padx=20)

        self.progress = ttk.Progressbar(self.top, mode="determinate")
        self.progress.pack(fill=tk.X, padx=20, pady=(14, 4))
        self.status = tk.Label(self.top, text="", bg=p["surface"],
                               fg=p["text_dim"], font=("Segoe UI", 9))
        self.status.pack(anchor="w", padx=20)

        bf = tk.Frame(self.top, bg=p["surface"])
        bf.pack(fill=tk.X, padx=20, pady=16)

        self.install_btn = ttk.Button(bf, text="Скачать и установить",
                                      style="Accent.TButton",
                                      command=self._install)
        self.install_btn.pack(side=tk.RIGHT)
        ttk.Button(bf, text="Позже", command=self.top.destroy
                   ).pack(side=tk.RIGHT, padx=(0, 8))

        homepage = info.get("homepage") or branding.APP_HOMEPAGE
        if homepage:
            ttk.Button(bf, text="Открыть страницу",
                       command=lambda: _open_url(homepage)
                       ).pack(side=tk.LEFT)

        # если запущено из .py — установка exe невозможна, но плагины обновить можно
        if not updater.is_frozen():
            self.status.config(
                text="Запущено из исходников: установка EXE недоступна, "
                     "будут обновлены только плагины."
            )

    def _install(self):
        self.install_btn.config(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        info = self.info

        # 1) Обновляем плагины
        if info["plugins"] and self.app.config.data["updates"].get("auto_install_plugins"):
            self._status("Обновление плагинов…")
            reports = updater.apply_plugin_updates(
                info["plugins"],
                progress_cb=self._progress_cb,
            )
            ok = sum(1 for r in reports if r["ok"])
            self._status(f"Плагины обновлены: {ok}/{len(reports)}")
            for r in reports:
                if not r["ok"]:
                    print(f"plugin {r['name']} failed: {r['error']}")

        # 2) Скачиваем и устанавливаем обновление
        if updater.is_frozen() and info["download_url"]:
            self._status("Скачивание обновления…")
            try:
                import tempfile
                from pathlib import Path
                tmp_dir = Path(tempfile.gettempdir())

                if updater.is_installed_via_inno():
                    # Стандартный случай: пользователь ставил через Setup.exe.
                    # Скачиваем новый Setup и запускаем в тихом режиме.
                    setup_name = f"{branding.APP_NAME}-Setup-{info['remote']}.exe"
                    tmp_setup = tmp_dir / setup_name
                    updater.download_file(info["download_url"], tmp_setup,
                                          progress_cb=self._progress_cb)
                    if info.get("sha256") and not updater.verify_sha256(
                            tmp_setup, info["sha256"]):
                        raise ValueError("sha256 не совпадает — файл повреждён")

                    self._status("Запуск установщика. Приложение закроется…")
                    updater.run_installer_and_exit(tmp_setup, self.app)
                    return

                # Portable-режим: подменяем сам EXE
                tmp_exe = tmp_dir / f"{branding.APP_SLUG}_new.exe"
                updater.download_file(info["download_url"], tmp_exe,
                                      progress_cb=self._progress_cb)
                if info.get("sha256") and not updater.verify_sha256(
                        tmp_exe, info["sha256"]):
                    raise ValueError("sha256 не совпадает — файл повреждён")

                self._status("Применение обновления…")
                if not updater.schedule_self_replace(tmp_exe):
                    raise RuntimeError("не удалось запланировать подмену EXE")
                self._status("Готово. Приложение будет перезапущено.")
                self.app.root.after(500, self._quit_and_restart)
                return
            except Exception as e:
                self._status(f"Ошибка: {e}")
                self.install_btn.config(state="normal")
                return

    def _quit_and_restart(self):
        try:
            self.app.on_close()
        except Exception:
            pass

    def _progress_cb(self, got, total):
        if not total:
            return
        frac = got / total
        self.top.after(0, lambda: self.progress.config(
            maximum=100, value=int(frac * 100)))

    def _status(self, text):
        self.top.after(0, lambda: self.status.config(text=text))


def _open_url(url):
    import webbrowser
    webbrowser.open(url)


# ---------- Настройки обновлений ----------
def _settings(app):
    p = app.palette
    top = tk.Toplevel(app.root)
    top.title(f"Настройки обновлений — {branding.APP_NAME}")
    top.configure(bg=p["surface"])
    top.geometry("560x280")
    top.transient(app.root)
    top.grab_set()

    u = app.config.data["updates"]
    url_var = tk.StringVar(value=u.get("manifest_url", ""))
    auto_var = tk.BooleanVar(value=bool(u.get("auto_check")))
    plugins_var = tk.BooleanVar(value=bool(u.get("auto_install_plugins")))

    tk.Label(top, text="URL манифеста обновлений (manifest.json):",
             bg=p["surface"], fg=p["text"]
             ).pack(anchor="w", padx=20, pady=(18, 4))
    ttk.Entry(top, textvariable=url_var).pack(fill=tk.X, padx=20)

    tk.Label(top,
             text=f"Текущая версия: {__version__}",
             bg=p["surface"], fg=p["text_dim"],
             font=("Segoe UI", 9)
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