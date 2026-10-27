"""Главный класс приложения PhotoGrid."""
import os
import queue
import random
import shutil
import sys
import tempfile
import threading
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser

from PIL import Image, ImageTk

from .config import Config, LAYOUTS, IMAGE_EXTS, DEFAULTS
from . import anim, branding, icons
from .toast import ToastManager
from .core import build_collage
from .theme import apply_theme, DARK, LIGHT
from .ui_widgets import (
    HoverButton, Slot, LogoMark, IconButton, ColorSwatch,
    SegmentedControl, CaptionEntry,
    RailButton, GradientButton, GradientSlider, Tooltip, style_dropdown,
    AnimatedStatusBar,
)

# UTF-8 stdout
for _s in (sys.stdout, sys.stderr):
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class App:
    def __init__(self, root):
        self.root = root
        self.config = Config()
        self.palette = DARK if self.config["theme"] == "dark" else LIGHT

        self.root.title(branding.window_title())
        self.root.geometry("1320x840")
        self.root.minsize(1120, 720)
        self._set_window_icon()

        # ---- состояние ----
        _cols, _rows = LAYOUTS.get(self.config["layout"], (2, 2))
        self.photos = [None] * (_cols * _rows)
        self.captions = [""] * (_cols * _rows)   # ← подписи под фото

        self._tmp_dir = None        # папка для временных файлов (поворот, вставка…)
        self._syncing = False       # True, пока переменные UI синхронизируются с config
        self._undo_stack = []
        self._redo_stack = []
        self._undo_limit = 50
        self._last_layout_cols_rows = (_cols, _rows)
        self._status_reset_job = None

        self.selected_slot = None
        self.thumb_refs = [None] * len(self.photos)
        self.preview_ref = None
        self.last_save_path = None
        self._preview_job = None
        self.plugin_flags = {}
        self.collage_hooks = []
        self.rail_buttons = {}
        self.views = {}
        self.active_section = "collage"
        self.plugin_actions = {}

        # --- API для плагинов и состояние массового выбора ---
        self.slots_rebuilt_hooks = []   # вызываются после каждой пересборки слотов
        self.slot_actions = []          # пункты контекстного меню слота от плагинов
        self.marked = set()             # слоты, отмеченные для массового удаления
        self._mark_anchor = None
        self._drag_src = None           # перетаскивание фото между слотами
        self._drag_active = False
        self._drag_over = None
        self._preview_pil = None        # то, что сейчас показано в превью
        self._preview_seq = 0           # номер актуального запроса превью
        self._saving = False
        self._task_queue = queue.Queue()
        self._task_poll = None
        self._tasks_running = 0

        anim.set_enabled(self.config["animations"])

        self.layout_var  = tk.StringVar(value=self.config["layout"])
        self.mode_var    = tk.StringVar(value=self.config["mode"])
        self.cell_var    = tk.IntVar(value=self.config["cell_size"])
        self.border_var  = tk.IntVar(value=self.config["border"])
        self.quality_var = tk.DoubleVar(value=self.config["quality"])

        self.ttk = apply_theme(self.root, self.config["theme"])
        self.toasts = ToastManager(self.root, self.palette)

        self._build_layout()
        self._build_rail()
        self._build_body()
        self._build_statusbar()
        self._bind_shortcuts()

        for v in (self.layout_var, self.mode_var, self.cell_var, self.border_var):
            v.trace_add("write", lambda *a: self._on_settings_change())

        from .plugins import loader
        loader.load_all(self)
        self._plugins_loaded = True

        self.update_preview()
        self.update_status()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._fade_in_window()

    def _fade_in_window(self):
        """Плавное появление окна при запуске."""
        if not anim.is_enabled():
            return

        def _set(a):
            try:
                self.root.attributes("-alpha", a)
            except Exception:
                pass

        try:
            self.root.attributes("-alpha", 0.0)
        except Exception:
            return
        anim.get(self.root).animate(380, _set, on_done=lambda: _set(1.0),
                                    key="startup-fade")

    # ==================================================================
    #  ИКОНКА ОКНА
    # ==================================================================
    def _set_window_icon(self):
        from pathlib import Path
        candidates = [Path(__file__).parent / "icon.ico"]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "photogrid" / "icon.ico")
            candidates.append(Path(meipass) / "icon.ico")
        try:
            exe_dir = Path(sys.executable).parent
            candidates.append(exe_dir / "photogrid" / "icon.ico")
            candidates.append(exe_dir / "icon.ico")
        except Exception:
            pass

        icon_path = None
        for c in candidates:
            if c.exists():
                icon_path = c
                break

        if icon_path is None:
            print("[icon] Иконка не найдена — остаётся системная")
            return

        try:
            self.root.iconbitmap(default=str(icon_path))
        except Exception as e:
            print(f"[icon] iconbitmap не сработал: {e}")
            try:
                self._icon_img = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self._icon_img)
            except Exception as e2:
                print(f"[icon] iconphoto тоже не сработал: {e2}")

        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    f"{branding.APP_SLUG}.{branding.APP_EXE_NAME}.1"
                )
            except Exception:
                pass

    # ==================================================================
    #  КОРНЕВОЙ LAYOUT
    # ==================================================================
    def _build_layout(self):
        p = self.palette
        self.main_frame = tk.Frame(self.root, bg=p["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.rail = tk.Frame(self.main_frame, bg=p["bg"], width=68)
        self.rail.pack(side=tk.LEFT, fill=tk.Y)
        self.rail.pack_propagate(False)

        self.content = tk.Frame(self.main_frame, bg=p["bg"])
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ==================================================================
    #  РЕЛЬС
    # ==================================================================
    def _build_rail(self):
        p = self.palette

        logo_wrap = tk.Frame(self.rail, bg=p["bg"])
        logo_wrap.pack(pady=(20, 24))
        logo = LogoMark(logo_wrap, p, size=42, letter="P")
        logo.pack()
        Tooltip(logo, branding.APP_NAME, p)

        # разделы (верх)
        sections = [
            ("collage", "Коллаж", "Собрать коллаж из фото"),
            ("plugins", "Плагины", "Загруженные плагины и их действия"),
            ("batch",   "Пакетная обработка", "Обработать сразу много папок"),
            ("cloud",   "Облако", "Экспорт в облако (скоро)"),
        ]
        for key, tip, desc in sections:
            btn = RailButton(self.rail, p, kind=key, size=42,
                             command=lambda k=key: self._set_section(k),
                             tooltip=tip)
            btn.pack(pady=3)
            self.rail_buttons[key] = btn

        tk.Frame(self.rail, bg=p["bg"]).pack(fill=tk.BOTH, expand=True)

        # разделы (низ)
        bottom = [
            ("theme",    "Тема",         self.toggle_theme,   False),
            ("settings", "Настройки",    self.show_settings,  False),
            ("update",   "Обновление",   self._on_update_click, True),
            ("help",     "Справка",      self.show_about,     False),
        ]
        for kind, tip, cmd, pulse in bottom:
            btn = RailButton(self.rail, p, kind=kind, size=42,
                             command=cmd, tooltip=tip, pulse=pulse)
            btn.pack(pady=3)
            self.rail_buttons[kind] = btn

        tk.Frame(self.rail, bg=p["bg"], height=16).pack()

        # кнопка обновления скрыта по умолчанию
        if "update" in self.rail_buttons:
            self.rail_buttons["update"].pack_forget()

        self._set_section("collage")

    def _set_section(self, key):
        if key == "cloud":
            messagebox.showinfo(
                "Скоро",
                "Облачный экспорт появится в следующем обновлении."
            )
            return

        if key in ("plugins", "batch") and key not in self.views:
            try:
                if key == "plugins":
                    from .screens.plugins import build_plugins_view
                    self.views[key] = build_plugins_view(self.content, self)
                elif key == "batch":
                    from .screens.batch import build_batch_view
                    self.views[key] = build_batch_view(self.content, self)
            except Exception as e:
                messagebox.showerror(
                    "Ошибка",
                    f"Не удалось открыть раздел «{key}»:\n{e}"
                )
                return

        prev = self.active_section
        for v in self.views.values():
            v.pack_forget()

        target = self.views.get(key)
        if target is not None:
            target.pack(fill=tk.BOTH, expand=True,
                        padx=(0, 14), pady=(14, 0))
            if key != prev and getattr(self, "_plugins_loaded", False):
                self._rise_in(target)

        for k, btn in self.rail_buttons.items():
            btn.set_active(k == key)
        self.active_section = key

    def _rise_in(self, widget):
        """Раздел «всплывает» снизу вверх за ~220 мс."""
        def step(t):
            widget.pack_configure(pady=(int(14 + 26 * (1 - t)), 0))
        anim.get(self.root).animate(220, step, key="section-rise",
                                    easing=anim.ease_out_cubic)

    def show_settings(self):
        from .screens.settings import open_settings_dialog
        open_settings_dialog(self)

    # ==================================================================
    #  ОБНОВЛЕНИЯ
    # ==================================================================
    def _on_update_click(self):
        """Клик по кнопке обновления в рельсе."""
        try:
            from .plugins import updater_ui
            updater_ui.open_update_dialog(self)
        except Exception as e:
            print(f"[update] не удалось открыть диалог: {e}")

    def set_update_badge(self, info):
        """Показывает или прячет анимированную иконку обновления в рельсе.

        info — словарь из updater.analyze() или None.
        Вызывается из плагина auto_updater через подписку.
        """
        btn = self.rail_buttons.get("update")
        if btn is None:
            return

        if info is None:
            # Нет обновления — прячем
            btn.pack_forget()
            btn.set_active(False)
        else:
            version = info.get("remote", "")
            btn.set_tooltip(f"Доступно обновление {version}\n"
                            f"Нажмите для установки")
            if not btn.winfo_ismapped():
                help_btn = self.rail_buttons.get("help")
                try:
                    if help_btn is not None:
                        btn.pack(pady=3, before=help_btn)
                    else:
                        btn.pack(pady=3)
                except Exception:
                    btn.pack(pady=3)
            # Пульсируем — активируем анимацию
            btn.set_active(True)
            self.set_status(f"Доступна новая версия {version}")

    # ==================================================================
    #  ХЕЛПЕРЫ ПАНЕЛЕЙ
    # ==================================================================
    def _panel(self, parent, p):
        outer = tk.Frame(parent, bg=p["border"], bd=0)
        inner = tk.Frame(outer, bg=p["surface"], bd=0)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        return outer, inner

    def _section_title(self, parent, text, p):
        tk.Label(parent, text=text.upper(),
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill=tk.X, padx=20, pady=(14, 6))

    def _small_button(self, parent, text, command, danger=False):
        p = self.palette
        accent = p["danger"] if danger else p["text"]
        btn = tk.Button(parent, text=text, command=command,
                        bg=p["surface_alt"], fg=accent,
                        activebackground=p["surface_hi"],
                        activeforeground=accent,
                        disabledforeground=p["text_faint"],
                        bd=0, relief="flat", cursor="hand2",
                        highlightthickness=0,
                        font=("Segoe UI", 9), padx=10, pady=5)
        btn.bind("<Enter>", lambda e: btn.cget("state") == "normal"
                 and btn.config(bg=p["surface_hi"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=p["surface_alt"]))
        return btn

    def _section_divider(self, parent, p):
        wrap = tk.Frame(parent, bg=p["surface"])
        wrap.pack(fill=tk.X, padx=20, pady=(14, 0))
        tk.Frame(wrap, bg=p["border_soft"], height=1).pack(fill=tk.X)

    def _setting_label(self, parent, text, row, p):
        tk.Label(parent, text=text,
                 bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(
            row=row, column=0, sticky="w", pady=6)

    # ==================================================================
    #  BODY
    # ==================================================================
    def _build_body(self):
        import tkinter.ttk as ttk
        p = self.palette
        body = tk.Frame(self.content, bg=p["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=(0, 14), pady=(14, 0))

        # ---------- ЛЕВАЯ: слоты ----------
        left_outer, left = self._panel(body, p)
        left_outer.pack(side=tk.LEFT, fill=tk.Y)

        head = tk.Frame(left, bg=p["surface"])
        head.pack(fill=tk.X, padx=18, pady=(16, 4))
        tk.Label(head, text="ФОТОГРАФИИ",
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        IconButton(head, p, kind="caption", size=30,
                   command=self.open_captions_dialog,
                   tooltip="Подписи: стиль, шрифт, быстрые действия"
                   ).pack(side=tk.RIGHT)

        hint_text = ("Клик — выбрать / swap · Двойной — заменить\n"
                     "Ctrl/Shift+клик — отметить · Del — удалить отмеченные\n"
                     "ПКМ — действия · перетащите файлы")
        tk.Label(left, text=hint_text, bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 8), justify="left"
                 ).pack(fill=tk.X, padx=18, pady=(0, 8))

        bulk = tk.Frame(left, bg=p["surface"])
        bulk.pack(fill=tk.X, padx=18, pady=(0, 10))
        self.mark_all_btn = self._small_button(
            bulk, "Выбрать все", self.toggle_mark_all)
        self.mark_all_btn.pack(side=tk.LEFT)
        self.bulk_delete_btn = self._small_button(
            bulk, "Удалить (0)", self.delete_marked, danger=True)
        self.bulk_delete_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.clear_all_btn = self._small_button(
            bulk, "Очистить всё", self.clear_all)
        self.clear_all_btn.pack(side=tk.RIGHT)

        self.slots_grid = tk.Frame(left, bg=p["surface"])
        self.slots_grid.pack(padx=18, pady=(0, 18))
        self.slot_widgets = []
        self._build_slots()

        # ---------- ЦЕНТР: настройки ----------
        mid_outer, mid = self._panel(body, p)
        mid_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(14, 0))
        mid.configure(width=350)
        mid.pack_propagate(False)

        head = tk.Frame(mid, bg=p["surface"])
        head.pack(fill=tk.X, padx=20, pady=(16, 8))

        tk.Label(head, text="НАСТРОЙКИ",
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(side=tk.LEFT)

        IconButton(head, p, kind="refresh", size=30,
                   command=self.update_preview,
                   tooltip="Обновить предпросмотр (F5)"
                   ).pack(side=tk.RIGHT)

        # Раскладка
        self._section_title(mid, "Раскладка", p)
        sec1 = tk.Frame(mid, bg=p["surface"])
        sec1.pack(fill=tk.X, padx=20)
        sec1.columnconfigure(1, weight=1)

        self._setting_label(sec1, "Формат", 0, p)
        ttk.Combobox(sec1, textvariable=self.layout_var,
                     values=list(LAYOUTS.keys()),
                     state="readonly").grid(
            row=0, column=1, sticky="ew", padx=(16, 0), pady=6)

        self._setting_label(sec1, "Режим", 1, p)
        SegmentedControl(
            sec1, p, [("fit", "Вписать"), ("fill", "Заполнить")],
            variable=self.mode_var,
        ).grid(row=1, column=1, sticky="w", padx=(16, 0), pady=6)

        self._section_divider(mid, p)

        # Оформление
        self._section_title(mid, "Оформление", p)
        sec2 = tk.Frame(mid, bg=p["surface"])
        sec2.pack(fill=tk.X, padx=20)
        sec2.columnconfigure(1, weight=1)

        self._setting_label(sec2, "Размер ячейки", 0, p)
        row_f = tk.Frame(sec2, bg=p["surface"])
        row_f.grid(row=0, column=1, sticky="w", padx=(16, 0), pady=6)
        ttk.Spinbox(row_f, from_=50, to=4000, increment=50,
                    textvariable=self.cell_var, width=7).pack(side=tk.LEFT)
        tk.Label(row_f, text="px", bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 0))

        self._setting_label(sec2, "Рамка", 1, p)
        row_f = tk.Frame(sec2, bg=p["surface"])
        row_f.grid(row=1, column=1, sticky="w", padx=(16, 0), pady=6)
        ttk.Spinbox(row_f, from_=0, to=300, increment=5,
                    textvariable=self.border_var, width=7).pack(side=tk.LEFT)
        tk.Label(row_f, text="px", bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 0))

        self._setting_label(sec2, "Цвет рамки", 2, p)
        self.border_color_btn = ColorSwatch(
            sec2, p, color=self.config["border_color"], size=40,
            command=self._choose_border_color,
        )
        self.border_color_btn.grid(row=2, column=1, sticky="w",
                                    padx=(16, 0), pady=6)

        self._setting_label(sec2, "Фон ячейки", 3, p)
        self.bg_color_btn = ColorSwatch(
            sec2, p, color=self.config["bg_color"], size=40,
            command=self._choose_bg_color,
        )
        self.bg_color_btn.grid(row=3, column=1, sticky="w",
                                padx=(16, 0), pady=6)

        self._section_divider(mid, p)

        # Экспорт
        self._section_title(mid, "Экспорт", p)
        sec3 = tk.Frame(mid, bg=p["surface"])
        sec3.pack(fill=tk.X, padx=20)
        sec3.columnconfigure(0, weight=1)

        q_head = tk.Frame(sec3, bg=p["surface"])
        q_head.pack(fill=tk.X, pady=(0, 4))
        tk.Label(q_head, text="Качество JPEG", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)
        self.quality_label = tk.Label(
            q_head, text=f"{int(self.config['quality'])}%",
            bg=p["surface"], fg=p["text"],
            font=("Segoe UI", 10, "bold"))
        self.quality_label.pack(side=tk.RIGHT)

        self.quality_slider = GradientSlider(
            sec3, p, from_=60, to=100,
            value=float(self.config["quality"]),
            command=self._on_quality_slider, height=22,
        )
        self.quality_slider.pack(fill=tk.X, pady=(2, 6))

        # Кнопки
        btnbox = tk.Frame(mid, bg=p["surface"])
        btnbox.pack(fill=tk.X, padx=20, pady=(16, 20), side=tk.BOTTOM)

        GradientButton(
            btnbox, p, text="Сохранить как…", icon="save", height=44,
            command=lambda: self.combine_and_save(force_dialog=True),
        ).pack(fill=tk.X, pady=(0, 8))

        copy_btn = tk.Button(btnbox, text="Копировать в буфер",
                             image=icons.tk_icon("copy", 18, p["text_dim"], 10),
                             compound="left",
                             bg=p["surface_alt"], fg=p["text"],
                             activebackground=p["surface_hi"],
                             activeforeground=p["text"],
                             bd=0, relief="flat", cursor="hand2",
                             font=("Segoe UI", 10), anchor="w",
                             highlightthickness=0, takefocus=0,
                       padx=14, pady=10,
                             command=self.copy_collage_to_clipboard_with_ui)
        copy_btn.pack(fill=tk.X, pady=(0, 6))

        b2 = tk.Button(btnbox, text="Загрузить из папки",
                       image=icons.tk_icon("folder", 18, p["text_dim"], 10),
                       compound="left",
                       bg=p["surface_alt"], fg=p["text"],
                       activebackground=p["surface_hi"],
                       activeforeground=p["text"],
                       bd=0, relief="flat", cursor="hand2",
                       font=("Segoe UI", 10), anchor="w",
                       highlightthickness=0, takefocus=0,
                       padx=14, pady=11,
                       command=self.load_from_folder)
        b2.pack(fill=tk.X, pady=(0, 4))

        # ---------- ПРАВАЯ: предпросмотр ----------
        right_outer, right = self._panel(body, p)
        right_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))

        rh = tk.Frame(right, bg=p["surface"])
        rh.pack(fill=tk.X, padx=18, pady=(16, 4))
        tk.Label(rh, text="ПРЕДПРОСМОТР",
                 bg=p["surface"], fg=p["text_faint"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        stage = tk.Frame(right, bg=p["bg"], bd=0)
        stage.pack(fill=tk.BOTH, expand=True, padx=18, pady=(6, 18))

        self.preview_label = tk.Label(
            stage,
            text="Здесь появится коллаж\n\nВыберите фото\nили перетащите их в слоты",
            bg=p["bg"], fg=p["text_dim"],
            font=("Segoe UI", 11), justify="center", wraplength=260,
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        self.views["collage"] = body

    # ==================================================================
    #  СЛОТЫ
    # ==================================================================
    def _build_slots(self):
        p = self.palette
        for w in self.slots_grid.winfo_children():
            w.destroy()

        self.slot_widgets = []
        cols, rows = LAYOUTS.get(self.config["layout"], (2, 2))
        total = cols * rows

        if len(self.photos) < total:
            self.photos.extend([None] * (total - len(self.photos)))
        elif len(self.photos) > total:
            self.photos = self.photos[:total]

        self.thumb_refs = [None] * total
        # выделенный слот мог остаться за пределами новой раскладки
        if self.selected_slot is not None and self.selected_slot >= total:
            self.selected_slot = None
        self.marked = {i for i in self.marked if i < total}
        if self._mark_anchor is not None and self._mark_anchor >= total:
            self._mark_anchor = None

        # Синхронизируем список подписей под новое количество слотов
        if len(self.captions) < total:
            self.captions.extend([""] * (total - len(self.captions)))

        # Колонок в сетке: не больше 3, но минимум 1
        grid_cols = max(1, min(cols, 3))

        for i in range(total):
            r = i // grid_cols
            c = i % grid_cols

            slot = Slot(
                self.slots_grid, p, i,
                on_click=lambda e, idx=i: self.on_slot_click(idx, e),
                on_right_click=lambda e, idx=i: self.on_slot_context_menu(e, idx),
                on_double_click=lambda e, idx=i: self.on_slot_replace(idx),
            )
            slot.grid(row=r * 2, column=c, padx=6, pady=(6, 2))
            slot.bind("<ButtonPress-1>",
                      lambda e, idx=i: self._drag_start(idx, e), add="+")
            slot.bind("<B1-Motion>",
                      lambda e, idx=i: self._drag_move(idx, e), add="+")
            slot.bind("<ButtonRelease-1>",
                      lambda e, idx=i: self._drag_end(idx, e), add="+")
            self.slot_widgets.append(slot)

            # --- поле для подписи под слотом ---
            cap_var = tk.StringVar(value=self.captions[i] if i < len(self.captions) else "")
            entry = CaptionEntry(self.slots_grid, p, cap_var)
            entry.grid(row=r * 2 + 1, column=c,
                       padx=6, pady=(0, 8), sticky="ew")

            # сохраняем и обновляем превью при каждом изменении
            cap_var.trace_add(
                "write",
                lambda *a, idx=i, v=cap_var: self._on_caption_var_change(idx, v),
            )

            # корректируем ширину колонки по слоту
            self.slots_grid.columnconfigure(c, weight=0, minsize=168)

        self.slot_containers = self.slot_widgets
        self.slot_labels = self.slot_widgets

        for i in range(total):
            self.update_slot(i)

        # Слоты — новые виджеты: всё, что было навешено на старые (например,
        # приёмники drag & drop), нужно навесить заново. Раньше это делалось
        # один раз при загрузке плагинов, поэтому после смены шаблона
        # перетаскивание фото в слоты переставало работать.
        for hook in list(self.slots_rebuilt_hooks):
            try:
                hook()
            except Exception as e:
                print(f"slots_rebuilt hook error: {e}")

    def open_captions_dialog(self):
        """Окно настроек подписей (плагин captions)."""
        opener = getattr(self, "_captions_opener", None)
        if opener:
            opener()
        else:
            self.set_status("Плагин подписей не загружен")

    def _on_caption_var_change(self, idx, var):
        """Реагирует на ввод в поле подписи слота."""
        text = var.get()
        if idx >= len(self.captions):
            while len(self.captions) <= idx:
                self.captions.append("")
        self.captions[idx] = text
        self.schedule_preview()
    # ==================================================================
    #  STATUS BAR
    # ==================================================================
    def _build_statusbar(self):
        p = self.palette
        tk.Frame(self.root, bg=p["border_soft"], height=1).pack(
            fill=tk.X, side=tk.BOTTOM)

        self.status_bar = AnimatedStatusBar(self.root, p, height=34)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_var = tk.StringVar(value="Готово")
        self._status_reset_job = None

    # ==================================================================
    #  СЛОТЫ: содержимое
    # ==================================================================
    def update_slot(self, idx, animate=False):
        if idx >= len(self.slot_widgets):
            return
        slot = self.slot_widgets[idx]
        path = self.photos[idx] if idx < len(self.photos) else None
        if path is None:
            self.marked.discard(idx)
            slot.set_thumb(None)
            if idx < len(self.thumb_refs):
                self.thumb_refs[idx] = None
        else:
            try:
                thumb = self._make_thumb(path, 145)
                slot.set_thumb(thumb, animate=animate)
                if idx < len(self.thumb_refs):
                    self.thumb_refs[idx] = thumb
            except Exception as e:
                print(f"Ошибка загрузки миниатюры слота {idx}: {e}")
                slot.set_thumb(None)
                if idx < len(self.thumb_refs):
                    self.thumb_refs[idx] = None
        slot.set_marked(idx in self.marked)
        slot.update_border(selected=(self.selected_slot == idx))

    def _make_thumb(self, path, size):
        from .core import load_rgb
        img = load_rgb(path, self.palette["slot_bg"])
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGB", (size, size), self.palette["slot_bg"])
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
        return ImageTk.PhotoImage(canvas)

    # ==================================================================
    #  КЛИКИ
    # ==================================================================
    def on_slot_click(self, idx, event=None):
        state = getattr(event, "state", 0) or 0
        if not isinstance(state, int):
            state = 0
        ctrl, shift = bool(state & 0x4), bool(state & 0x1)
        # Ctrl/Shift+клик — отметка для массового удаления; пока что-то
        # отмечено, обычный клик по фото тоже отмечает (а не меняет местами)
        if self.photos[idx] is not None and (ctrl or shift or self.marked):
            self._mark_click(idx, shift)
            return

        if self.photos[idx] is None:
            path = filedialog.askopenfilename(
                title=f"Выберите фото {idx + 1}",
                filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                           ("Все файлы", "*.*")]
            )
            if path:
                self._push_undo("Выбор фото")
                self.photos[idx] = path
                self.update_slot(idx, animate=True)
                self.schedule_preview()
                self.update_status()
            return

        if self.selected_slot is None:
            self.selected_slot = idx
            self.update_slot(idx)
        elif self.selected_slot == idx:
            self.selected_slot = None
            self.update_slot(idx)
        else:
            a, b = self.selected_slot, idx
            self._push_undo("Обмен фото")
            self.photos[a], self.photos[b] = self.photos[b], self.photos[a]
            self.selected_slot = None
            self.update_slot(a, animate=True)
            self.update_slot(b, animate=True)
            self.schedule_preview()

    # ------------------------------------------------------------------
    #  ПЕРЕТАСКИВАНИЕ ФОТО МЕЖДУ СЛОТАМИ (мышью)
    # ------------------------------------------------------------------
    def _slot_under_pointer(self, event):
        try:
            w = self.root.winfo_containing(event.x_root, event.y_root)
        except Exception:
            return None
        return w.index if isinstance(w, Slot) else None

    def _set_drag_over(self, idx):
        if idx == self._drag_over:
            return
        for i in (self._drag_over, idx):
            if i is not None and i < len(self.slot_widgets):
                w = self.slot_widgets[i]
                on = (i == idx)
                w.hover = on
                w._hv = 1.0 if on else 0.0
                w._redraw()
        self._drag_over = idx

    def _drag_start(self, idx, event):
        self._drag_src = (idx, event.x_root, event.y_root)
        self._drag_active = False

    def _drag_move(self, idx, event):
        src = self._drag_src
        if not src or src[0] != idx or self.photos[idx] is None:
            return
        if not self._drag_active:
            if abs(event.x_root - src[1]) + abs(event.y_root - src[2]) < 10:
                return
            self._drag_active = True
            try:
                self.slot_widgets[idx].config(cursor="fleur")
            except Exception:
                pass
        t = self._slot_under_pointer(event)
        self._set_drag_over(t if t != idx else None)

    def _drag_end(self, idx, event):
        src, active = self._drag_src, self._drag_active
        self._drag_src, self._drag_active = None, False
        if not (src and active) or src[0] != idx:
            return
        try:
            self.slot_widgets[idx].config(cursor="hand2")
        except Exception:
            pass
        self._set_drag_over(None)
        target = self._slot_under_pointer(event)
        if target is None or target == idx or target >= len(self.photos):
            self._deselect()
            return
        self._push_undo("Перенос фото")
        self.photos[idx], self.photos[target] = self.photos[target], self.photos[idx]
        self.selected_slot = None
        self.update_slot(idx, animate=True)
        self.update_slot(target, animate=True)
        self.schedule_preview()

    # ------------------------------------------------------------------
    #  МАССОВЫЙ ВЫБОР / УДАЛЕНИЕ
    # ------------------------------------------------------------------
    def _filled_indices(self):
        return [i for i, p in enumerate(self.photos) if p is not None]

    def _mark_click(self, idx, shift=False):
        self._deselect()
        if shift and self._mark_anchor is not None:
            lo, hi = sorted((self._mark_anchor, idx))
            for i in range(lo, hi + 1):
                if self.photos[i] is not None:
                    self.marked.add(i)
        else:
            if idx in self.marked:
                self.marked.discard(idx)
            else:
                self.marked.add(idx)
            self._mark_anchor = idx
        self._refresh_marks()

    def _refresh_marks(self):
        for i, w in enumerate(self.slot_widgets):
            w.set_marked(i in self.marked)
        self.update_status()

    def toggle_mark_all(self):
        filled = set(self._filled_indices())
        if not filled:
            return
        self._deselect()
        if self.marked >= filled:
            self.marked.clear()
        else:
            self.marked = set(filled)
        self._refresh_marks()

    def clear_marks(self):
        if self.marked:
            self.marked.clear()
            self._mark_anchor = None
            self._refresh_marks()

    def delete_marked(self):
        """Убирает все отмеченные фото разом (Ctrl+Z возвращает)."""
        targets = sorted(i for i in self.marked
                         if i < len(self.photos) and self.photos[i] is not None)
        if not targets:
            self.set_status("Нет отмеченных фото")
            return 0
        self._push_undo("Массовое удаление")
        for i in targets:
            self.photos[i] = None
        self.marked.clear()
        self._mark_anchor = None
        self.selected_slot = None
        for i in range(len(self.photos)):
            self.update_slot(i)
        self.schedule_preview()
        self.update_status()
        self.toasts.show(f"Убрано фото: {len(targets)}", kind="info",
                         action=("Вернуть", self.undo))
        return len(targets)

    def _focus_in_text(self):
        try:
            w = self.root.focus_get()
            return w is not None and w.winfo_class() in (
                "Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox")
        except Exception:
            return False

    def _on_delete_key(self):
        if self._focus_in_text():
            return
        if self.marked:
            self.delete_marked()
        elif self.selected_slot is not None:
            self.on_slot_clear(self.selected_slot)

    def _on_select_all_key(self):
        if self._focus_in_text():
            return
        self.toggle_mark_all()
        return "break"

    def _on_escape(self):
        if self.marked:
            self.clear_marks()
        else:
            self._deselect()

    def on_slot_context_menu(self, event, idx):
        p = self.palette
        menu = tk.Menu(self.root, tearoff=0)
        style_dropdown(menu, p)

        has_photo = (idx < len(self.photos)) and (self.photos[idx] is not None)
        state = "normal" if has_photo else "disabled"

        menu.add_command(label="Заменить фото…",
                         command=lambda: self.on_slot_replace(idx),
                         state=state)
        menu.add_command(label="Убрать",
                         command=lambda: self.on_slot_clear(idx),
                         state=state)
        menu.add_separator()
        menu.add_command(label="Повернуть вправо 90°",
                         command=lambda: self.rotate_slot(idx, 90),
                         state=state)
        menu.add_command(label="Повернуть влево 90°",
                         command=lambda: self.rotate_slot(idx, -90),
                         state=state)
        menu.add_command(label="Отразить по горизонтали",
                         command=lambda: self.flip_slot(idx, "h"),
                         state=state)
        menu.add_command(label="Отразить по вертикали",
                         command=lambda: self.flip_slot(idx, "v"),
                         state=state)
        menu.add_separator()
        menu.add_command(label="Открыть в проводнике",
                         command=lambda: self.reveal_in_explorer(idx),
                         state=state)
        menu.add_command(label="Скопировать путь к файлу",
                         command=lambda: self.copy_slot_path(idx),
                         state=state)

        menu.add_separator()
        menu.add_command(
            label=("Снять отметку" if idx in self.marked
                   else "Отметить для удаления"),
            command=lambda: self._mark_click(idx), state=state)
        if self.marked:
            menu.add_command(label=f"Удалить отмеченные ({len(self.marked)})",
                             command=self.delete_marked)

        extra = [a for a in self.slot_actions
                 if has_photo or not a.get("needs_photo", True)]
        if extra:
            menu.add_separator()
            for act in extra:
                menu.add_command(
                    label=act["label"],
                    command=lambda a=act: a["command"](idx))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def on_slot_clear(self, idx):
        if idx < len(self.photos) and self.photos[idx] is not None:
            self._push_undo("Очистка слота")
            self.photos[idx] = None
            if self.selected_slot == idx:
                self.selected_slot = None
            self.update_slot(idx)
            self.schedule_preview()
            self.update_status()
            self.toasts.show("Фото убрано", kind="info",
                             action=("Вернуть", self.undo), duration=3000)

    def on_slot_replace(self, idx):
        path = filedialog.askopenfilename(
            title=f"Заменить фото {idx + 1}",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                       ("Все файлы", "*.*")]
        )
        if path:
            self._push_undo("Замена фото")
            self.photos[idx] = path
            if self.selected_slot == idx:
                self.selected_slot = None
            self.update_slot(idx, animate=True)
            self.schedule_preview()
            self.update_status()

    def _deselect(self):
        if self.selected_slot is not None:
            old = self.selected_slot
            self.selected_slot = None
            self.update_slot(old)

    # ==================================================================
    #  ПОВОРОТ / ОТРАЖЕНИЕ
    # ==================================================================
    def new_temp_path(self, prefix="pe", suffix=".png"):
        """Уникальный путь во временной папке приложения.

        Имена обязаны быть уникальными: раньше файл вида pe_rot_<слот>_90.png
        перезаписывался следующим поворотом, и в другом слоте/в undo
        внезапно оказывалась «чужая» картинка.
        """
        if self._tmp_dir is None or not os.path.isdir(self._tmp_dir):
            self._tmp_dir = tempfile.mkdtemp(
                prefix=f"{branding.APP_SLUG.lower()}_")
        return os.path.join(self._tmp_dir,
                            f"{prefix}_{uuid.uuid4().hex[:12]}{suffix}")

    def _transform_slot(self, idx, fn, undo_label, status_text, error_text):
        from .core import load_rgb
        path = self.photos[idx] if idx < len(self.photos) else None
        if path is None:
            return
        try:
            # load_rgb учитывает EXIF-ориентацию и прозрачность — результат
            # совпадает с тем, что видно в превью
            img = load_rgb(path, self.config["bg_color"])
            out = self.new_temp_path("pe_edit")
            fn(img).save(out, "PNG")
            self._push_undo(undo_label)
            self.photos[idx] = out
            self.update_slot(idx, animate=True)
            self.schedule_preview()
            self.set_status(status_text)
        except Exception as e:
            messagebox.showerror("Ошибка", f"{error_text}:\n{e}")

    def rotate_slot(self, idx, degrees):
        self._transform_slot(
            idx, lambda im: im.rotate(-degrees, expand=True),
            "Поворот фото", f"Фото {idx + 1} повёрнуто на {degrees}°",
            "Не удалось повернуть")

    def flip_slot(self, idx, direction="h"):
        method = (Image.FLIP_LEFT_RIGHT if direction == "h"
                  else Image.FLIP_TOP_BOTTOM)
        self._transform_slot(
            idx, lambda im: im.transpose(method),
            "Отражение фото", f"Фото {idx + 1} отражено",
            "Не удалось отразить")

    def reveal_in_explorer(self, idx):
        self.reveal_path(self.photos[idx])

    def reveal_path(self, path):
        if not path:
            return
        try:
            import subprocess
            folder = os.path.dirname(path)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть:\n{e}")

    def copy_slot_path(self, idx):
        path = self.photos[idx]
        if not path:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(path)
            self.set_status(f"Путь скопирован: {path}")
        except Exception:
            pass

    # ==================================================================
    #  ОТМЕНА / ПОВТОР
    # ==================================================================
    def _push_undo(self, label=""):
        cfg_keys = ("layout", "mode", "cell_size", "border",
                    "border_color", "bg_color", "quality")
        state = {
            "photos": list(self.photos),
            "captions": list(self.captions),
            "config": {k: self.config.get(k) for k in cfg_keys},
            "label": label,
        }
        self._undo_stack.append(state)
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.update_status()

    def undo(self):
        if not self._undo_stack:
            self.set_status("Нечего отменять")
            return
        cfg_keys = ("layout", "mode", "cell_size", "border",
                    "border_color", "bg_color", "quality")
        current = {
            "photos": list(self.photos),
            "captions": list(self.captions),
            "config": {k: self.config.get(k) for k in cfg_keys},
            "label": "",
        }
        state = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._apply_state(state)
        self.set_status(f"Отменено: {state.get('label', '') or 'изменение'}")

    def redo(self):
        if not self._redo_stack:
            self.set_status("Нечего повторять")
            return
        cfg_keys = ("layout", "mode", "cell_size", "border",
                    "border_color", "bg_color", "quality")
        current = {
            "photos": list(self.photos),
            "captions": list(self.captions),
            "config": {k: self.config.get(k) for k in cfg_keys},
            "label": "",
        }
        state = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._apply_state(state)
        self.set_status("Повторено")

    def _sync_vars_from_config(self):
        """Переносит значения из config в переменные/виджеты интерфейса.

        Переменные layout/mode/cell/border имеют trace, который пишет их
        значения обратно в config. Если выставлять их по одной, каждый trace
        затирал ещё не обновлённые значения старыми (так не применялись
        mode/размер/рамка из шаблона, сброс настроек и undo). Поэтому trace на
        время синхронизации выключен, а итоговое состояние применяется один раз.
        """
        self._syncing = True
        try:
            self.layout_var.set(self.config["layout"])
            self.mode_var.set(self.config["mode"])
            self.cell_var.set(self.config["cell_size"])
            self.border_var.set(self.config["border"])
            self.quality_var.set(self.config["quality"])
        finally:
            self._syncing = False

        if hasattr(self, "quality_label"):
            self.quality_label.config(text=f"{int(self.config['quality'])}%")
        if hasattr(self, "quality_slider"):
            self.quality_slider.set(self.config["quality"], notify=False)
        if hasattr(self, "border_color_btn"):
            self.border_color_btn.set_color(self.config["border_color"])
        if hasattr(self, "bg_color_btn"):
            self.bg_color_btn.set_color(self.config["bg_color"])

        new_layout = LAYOUTS.get(self.config["layout"], (2, 2))
        if self._last_layout_cols_rows != new_layout:
            self._last_layout_cols_rows = new_layout
            self._build_slots()

        self.config.save()
        self.schedule_preview()
        self.update_status()

    def _apply_state(self, state):
        self.marked.clear()
        self._mark_anchor = None
        self.photos = list(state["photos"])
        self.captions = list(state.get("captions", [""] * len(self.photos)))
        for k, v in state["config"].items():
            self.config[k] = v

        # слоты пересобираем всегда (фото/подписи заменены целиком)
        self._last_layout_cols_rows = LAYOUTS.get(self.config["layout"], (2, 2))
        self._sync_vars_from_config()
        self._build_slots()

    # ==================================================================
    #  ДЕЙСТВИЯ
    # ==================================================================
    def choose_photos_dialog(self):
        paths = filedialog.askopenfilenames(
            title=f"Выберите до {len(self.photos)} фотографий",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                       ("Все файлы", "*.*")]
        )
        if not paths:
            return
        self._push_undo("Загрузка фото")
        paths = list(paths)[:len(self.photos)]
        for i in range(len(self.photos)):
            self.photos[i] = paths[i] if i < len(paths) else None
            self.update_slot(i, animate=True)
        self.selected_slot = None
        self.schedule_preview()
        self.update_status()

    def fill_slots(self, files, start=None, undo_label="Вставка фото"):
        """Раскладывает файлы по слотам начиная с start (по кругу).

        start=None — с выделенного слота, иначе с первого пустого.
        Число слотов берётся из текущей раскладки (а не «всегда 4»).
        Возвращает, сколько файлов размещено.
        """
        n = len(self.photos)
        files = list(files)[:n]
        if n == 0 or not files:
            return 0
        if start is None:
            start = self.selected_slot
        if start is None:
            start = next((i for i, p in enumerate(self.photos) if p is None), 0)
        start = start % n

        self._push_undo(undo_label)
        for k, path in enumerate(files):
            idx = (start + k) % n
            self.photos[idx] = path
            self.update_slot(idx, animate=True)
        self.selected_slot = None
        self.schedule_preview()
        self.update_status()
        return len(files)

    def load_from_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку с фотографиями")
        if not folder:
            return
        try:
            files = sorted(
                f for f in os.listdir(folder)
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать папку:\n{e}")
            return
        if not files:
            messagebox.showwarning("Внимание", "В папке не найдено изображений")
            return
        need = len(self.photos)
        if len(files) < need:
            messagebox.showinfo(
                "Информация",
                f"В папке найдено {len(files)} фото.\n"
                f"Будут заполнены только они."
            )
        self._push_undo("Загрузка папки")
        for i in range(need):
            self.photos[i] = os.path.join(folder, files[i]) if i < len(files) else None
            self.update_slot(i, animate=True)
        self.selected_slot = None
        self.schedule_preview()
        self.update_status()

    def clear_all(self):
        if not any(self.photos):
            return
        # подтверждение больше не нужно: действие отменяется (Ctrl+Z / «Вернуть»)
        self._push_undo("Очистка")
        self.photos = [None] * len(self.photos)
        self.captions = [""] * len(self.photos)
        self.marked.clear()
        self._mark_anchor = None
        self.selected_slot = None
        # слоты пересобираются (заодно очищаются поля подписей)
        self._build_slots()
        self.schedule_preview()
        self.update_status()
        self.toasts.show("Все фото убраны", kind="info",
                         action=("Вернуть", self.undo))

    def shuffle_photos(self):
        self._push_undo("Перемешивание")
        filled = [p for p in self.photos if p is not None]
        random.shuffle(filled)
        for i in range(len(self.photos)):
            self.photos[i] = filled[i] if i < len(filled) else None
            self.update_slot(i)
        self.selected_slot = None
        self.schedule_preview()

    def reset_settings(self, confirm=True):
        if confirm and not messagebox.askyesno(
                "Сброс", "Сбросить все настройки по умолчанию?"):
            return
        for k, v in DEFAULTS.items():
            if k != "theme":
                self.config[k] = v
        anim.set_enabled(self.config["animations"])
        self._sync_vars_from_config()

    def toggle_theme(self):
        self.config["theme"] = "light" if self.config["theme"] == "dark" else "dark"
        self.config.save()
        self.reload_ui()

    def reload_ui(self):
        saved_photos = list(self.photos)
        saved_captions = list(self.captions)
        saved_selected = self.selected_slot
        saved_last_save = self.last_save_path

        # старые виджеты исчезнут — их анимации и хуки больше не нужны
        anim.get(self.root).stop_all()
        self.slots_rebuilt_hooks.clear()
        self.slot_actions.clear()
        self._preview_seq += 1
        self._preview_pil = None

        try:
            if hasattr(self, "status_bar"):
                self.status_bar.stop()
        except Exception:
            pass

        for w in list(self.root.winfo_children()):
            if isinstance(w, tk.Toplevel):
                try:
                    w.grab_release()
                    w.destroy()
                except Exception:
                    pass

        for w in list(self.root.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass

        self.palette = DARK if self.config["theme"] == "dark" else LIGHT
        self.ttk = apply_theme(self.root, self.config["theme"])
        self.toasts = ToastManager(self.root, self.palette)

        self.rail_buttons = {}
        self.views = {}
        self.menu_buttons = []
        self.menus = {}
        self.thumb_refs = [None] * len(saved_photos)
        self.preview_ref = None
        self._preview_job = None
        self.active_section = "collage"

        self._build_layout()
        self._build_rail()
        self._build_body()
        self._build_statusbar()
        self._bind_shortcuts()

        self.photos = saved_photos
        self.captions = saved_captions
        self.selected_slot = saved_selected
        self.last_save_path = saved_last_save

        for i in range(len(self.photos)):
            self.update_slot(i)
        self.update_preview()
        self.update_status()

        try:
            from .plugins import loader
            self.plugin_flags.clear()
            self.plugin_actions.clear()
            # плагины регистрируются заново — без очистки хук водяного знака
            # накладывался бы повторно после каждой смены темы
            self.collage_hooks.clear()
            loader.load_all(self)
        except Exception as e:
            print(f"reload_ui: плагины не перезагружены: {e}")

        # Восстанавливаем значок обновления
        try:
            from . import updater
            pending = updater.get_pending()
            self.set_update_badge(pending)
        except Exception as e:
            print(f"reload_ui: не удалось восстановить значок обновления: {e}")

        self.set_status("Тема применена")

    def _choose_border_color(self):
        color = colorchooser.askcolor(color=self.config["border_color"],
                                      title="Цвет рамки")[1]
        if color:
            self.config["border_color"] = color
            self.border_color_btn.set_color(color)
            self.config.save()
            self.schedule_preview()

    def _choose_bg_color(self):
        color = colorchooser.askcolor(color=self.config["bg_color"],
                                      title="Цвет фона ячейки")[1]
        if color:
            self.config["bg_color"] = color
            self.bg_color_btn.set_color(color)
            self.config.save()
            self.schedule_preview()

    def _on_quality_slider(self, value):
        q = int(round(value))
        self.quality_label.config(text=f"{q}%")
        self.config["quality"] = q
        self.config.save()

    def _on_settings_change(self):
        if self._syncing:
            return
        try:
            self.config["layout"] = self.layout_var.get()
            self.config["mode"] = self.mode_var.get()
            self.config["cell_size"] = int(self.cell_var.get())
            self.config["border"] = int(self.border_var.get())
        except (tk.TclError, ValueError):
            return
        if self.config["layout"] not in LAYOUTS:
            return

        cols, rows = LAYOUTS[self.config["layout"]]
        if self._last_layout_cols_rows != (cols, rows):
            self._last_layout_cols_rows = (cols, rows)
            self._build_slots()

        self.config.save()
        self.schedule_preview()
        self.update_status()

    # ==================================================================
    #  ПРЕДПРОСМОТР
    # ==================================================================
    def schedule_preview(self):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(250, self.update_preview)

    def _show_placeholder(self, text=None, error=False):
        p = self.palette
        self.preview_label.config(
            image="",
            text=text or "Здесь появится коллаж\n\nВыберите фото\nили перетащите их в слоты",
            bg=p["bg"])
        self.preview_ref = None
        self._preview_pil = None

    def _set_preview_image(self, img):
        self.preview_ref = ImageTk.PhotoImage(img)
        self.preview_label.config(image=self.preview_ref, text="",
                                  bg=self.palette["bg"])

    def _show_preview(self, img):
        """Показывает превью; новое изображение плавно проявляется поверх старого."""
        old = self._preview_pil
        self._preview_pil = img
        if not anim.is_enabled():
            self._set_preview_image(img)
            return

        bg = self.palette["bg"]
        w = max(img.width, old.width if old else 0)
        h = max(img.height, old.height if old else 0)

        def frame(im):
            c = Image.new("RGB", (w, h), bg)
            if im is not None:
                c.paste(im.convert("RGB"),
                        ((w - im.width) // 2, (h - im.height) // 2))
            return c

        a, b = frame(old), frame(img)

        def step(t):
            if self._preview_pil is not img:
                return
            self._set_preview_image(img if t >= 1.0 else Image.blend(a, b, t))

        anim.get(self.root).animate(240, step, key="preview-fade",
                                    easing=anim.ease_out_cubic)

    def update_preview(self, sync=False):
        """Пересобирает превью. Тяжёлая часть (загрузка и склейка фото) идёт
        в фоновом потоке, поэтому окно и анимации не замирают; устаревшие
        результаты отбрасываются по номеру запроса. sync=True — всё сразу."""
        self._preview_job = None
        self._preview_seq += 1
        seq = self._preview_seq

        if not any(self.photos):
            self._show_placeholder()
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)
            return

        photos = list(self.photos)
        captions = list(self.captions)
        cfg = dict(self.config.data)

        def work():
            return build_collage(photos, cfg, for_preview=True,
                                 captions=captions)

        def finish():
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)

        def done(img):
            if seq != self._preview_seq:
                return
            try:
                img = self.apply_collage_hooks(img, for_preview=True)
                img.thumbnail((620, 620), Image.LANCZOS)
                self._show_preview(img)
            except Exception as e:
                self._show_placeholder(f"Ошибка:\n{e}")
            finish()

        def fail(e):
            if seq != self._preview_seq:
                return
            self._show_placeholder(f"Ошибка:\n{e}")
            finish()

        if hasattr(self, "status_bar"):
            self.status_bar.set_progress(0.5)

        if sync:
            try:
                done(work())
            except Exception as e:
                fail(e)
        else:
            self.run_task(work, done, fail)

    # ------------------------------------------------------------------
    #  ФОНОВЫЕ ЗАДАЧИ
    # ------------------------------------------------------------------
    def run_task(self, work, on_done=None, on_error=None):
        """Выполняет work() в потоке; on_done(результат) / on_error(исключение)
        вызываются в главном потоке (через очередь — вызывать Tk из чужого
        потока нельзя)."""
        self._tasks_running += 1

        def runner():
            try:
                res = work()
            except BaseException as e:      # noqa: BLE001 — пробрасываем в UI
                self._task_queue.put((on_error, e, True))
                return
            self._task_queue.put((on_done, res, False))

        threading.Thread(target=runner, daemon=True).start()
        self._ensure_task_poll()

    def _ensure_task_poll(self):
        if self._task_poll is None:
            try:
                self._task_poll = self.root.after(20, self._poll_tasks)
            except Exception:
                self._task_poll = None

    def _poll_tasks(self):
        self._task_poll = None
        while True:
            try:
                cb, val, is_err = self._task_queue.get_nowait()
            except queue.Empty:
                break
            self._tasks_running = max(0, self._tasks_running - 1)
            if cb is None:
                if is_err:
                    print(f"[task] ошибка: {val!r}")
                continue
            try:
                cb(val)
            except Exception as e:
                print(f"[task] ошибка обработчика: {e!r}")
        if self._tasks_running > 0:
            self._ensure_task_poll()

    # ==================================================================
    #  КОПИРОВАНИЕ В БУФЕР
    # ==================================================================
    def copy_collage_to_clipboard_with_ui(self):
        result = self.copy_collage_to_clipboard()
        if result is True:
            messagebox.showinfo("Готово",
                                "Коллаж скопирован в буфер обмена.\n"
                                "Вставьте его в любую программу (Ctrl+V).")
        elif isinstance(result, str):
            messagebox.showerror("Ошибка", result)

    def copy_collage_to_clipboard(self):
        if any(p is None for p in self.photos):
            return "Сначала выберите все фотографии!"

        try:
            img = build_collage(self.photos, self.config, for_preview=False,
                                captions=self.captions)
            img = self.apply_collage_hooks(img, for_preview=False)
        except Exception as e:
            return f"Не удалось собрать коллаж:\n{e}"

        if sys.platform == "win32":
            try:
                import win32clipboard
            except ImportError:
                return ("Не установлен модуль pywin32.\n\n"
                        "Установите: pip install pywin32")
            try:
                from io import BytesIO
                output = BytesIO()
                img.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]
                output.close()

                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                finally:
                    win32clipboard.CloseClipboard()

                self.set_status("Коллаж скопирован в буфер обмена")
                return True
            except Exception as e:
                return f"Ошибка копирования:\n{e}"

        try:
            import tempfile
            from pathlib import Path
            tmp = Path(tempfile.gettempdir()) / "collage_clipboard.png"
            img.save(tmp, "PNG")
            return (f"На вашей системе прямое копирование недоступно.\n"
                    f"Коллаж сохранён в файл:\n{tmp}")
        except Exception as e:
            return f"Ошибка: {e}"

    def _copy_collage_shortcut(self):
        result = self.copy_collage_to_clipboard()
        if result is True:
            self.set_status("Коллаж скопирован в буфер обмена")
        elif isinstance(result, str):
            messagebox.showerror("Ошибка", result)

    # ==================================================================
    #  СОХРАНЕНИЕ
    # ==================================================================
    def combine_and_save(self, force_dialog=True):
        if any(p is None for p in self.photos):
            messagebox.showwarning("Внимание", "Сначала выберите все фотографии!")
            return
        if not force_dialog and self.last_save_path:
            save_path = self.last_save_path
        else:
            save_path = filedialog.asksaveasfilename(
                title="Сохранить результат",
                defaultextension=".jpg",
                filetypes=[
                    ("JPEG",   "*.jpg *.jpeg"),
                    ("PNG",    "*.png"),
                    ("WebP",   "*.webp"),
                    ("TIFF",   "*.tif *.tiff"),
                    ("BMP",    "*.bmp"),
                    ("PDF",    "*.pdf"),
                    ("Все файлы", "*.*"),
                ],
                initialfile="collage.jpg",
            )
            if not save_path:
                return
            self.last_save_path = save_path

        if self._saving:
            self.set_status("Сохранение уже идёт…")
            return
        self._saving = True
        self.set_status("Сохранение…")
        if hasattr(self, "status_bar"):
            self.status_bar.set_progress(0.15)

        photos = list(self.photos)
        captions = list(self.captions)
        cfg = dict(self.config.data)
        quality = int(self.config["quality"])

        def fail(e):
            self._saving = False
            self.set_status("Ошибка сохранения")
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

        def built(img):
            # хуки плагинов (водяной знак и т.п.) работают с Tk-данными,
            # поэтому выполняются в главном потоке
            try:
                img = self.apply_collage_hooks(img, for_preview=False)
            except Exception as e:
                fail(e)
                return
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(0.6)
            self.run_task(lambda: (img, self._write_image(img, save_path, quality)),
                          saved, fail)

        def saved(res):
            img, size_mb = res
            self._saving = False
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(1.0)
                self.root.after(500, lambda: self.status_bar.set_progress(None))
            name = os.path.basename(save_path)
            self.set_status(
                f"Сохранено: {name}  ({img.width}×{img.height}, {size_mb:.2f} МБ)")
            self.toasts.show(
                f"Сохранено: {name}\n{img.width}×{img.height} · {size_mb:.2f} МБ",
                kind="success", action=("Показать",
                                        lambda: self.reveal_path(save_path)),
                duration=6000)

        self.run_task(
            lambda: build_collage(photos, cfg, for_preview=False,
                                  captions=captions),
            built, fail)

    @staticmethod
    def _write_image(img, save_path, quality):
        """Сохраняет картинку по расширению файла; возвращает размер в МБ."""
        ext = os.path.splitext(save_path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            img.convert("RGB").save(save_path, "JPEG", quality=quality,
                                    optimize=True)
        elif ext == ".png":
            img.save(save_path, "PNG", optimize=True)
        elif ext == ".webp":
            img.save(save_path, "WEBP", quality=quality, method=6)
        elif ext in (".tif", ".tiff"):
            img.save(save_path, "TIFF", compression="tiff_lzw")
        elif ext == ".bmp":
            img.save(save_path, "BMP")
        elif ext == ".pdf":
            img.convert("RGB").save(save_path, "PDF", resolution=150,
                                    title="Collage")
        else:
            img.save(save_path)
        return os.path.getsize(save_path) / (1024 * 1024)

    # ==================================================================
    #  СТАТУС / СПРАВКА
    # ==================================================================
    def set_status(self, text):
        state = self._infer_status_state(text)

        if hasattr(self, "status_bar"):
            self.status_bar.set_status(text, state)

        if state in ("success", "error"):
            if self._status_reset_job:
                try:
                    self.root.after_cancel(self._status_reset_job)
                except Exception:
                    pass
            self._status_reset_job = self.root.after(2500, self._reset_status)

    def _infer_status_state(self, text):
        low = text.lower()
        if any(k in low for k in ("ошибка", "не удалось", "не найден", "не установлен")):
            return "error"
        # Раньше «busy» проверялся по подстроке «сохран», из-за чего «Сохранено…»
        # и «Шаблон сохранён» навсегда оставляли индикатор в режиме «занято».
        if text.rstrip().endswith(("…", "...")):
            return "busy"
        if any(k in low for k in ("готово", "сохранён", "сохранен", "скопирован",
                                  "применён", "применен", "загружен")):
            return "success"
        return "ready"

    def _reset_status(self):
        self._status_reset_job = None
        self.update_status()

    def update_status(self):
        if not hasattr(self, "status_bar"):
            return

        n = sum(1 for p in self.photos if p)
        total = len(self.photos)
        cols, rows = LAYOUTS.get(self.config["layout"], (2, 2))
        cell = int(self.config.get("cell_size", 0))
        b = int(self.config.get("border", 0))
        w = cols * cell + (cols + 1) * b
        h = rows * cell + (rows + 1) * b

        base = (
            f"{n}/{total} фото   ·   {w}×{h} px   ·   "
            f"{self.config['layout']}"
        )
        self.status_bar.set_status(base, "ready")

        metrics = []
        if self.marked:
            metrics.append(("отмечено", len(self.marked)))
        metrics += [
            ("отмены", len(self._undo_stack)),
            ("плагины", len(self.plugin_flags)),
        ]
        self.status_bar.set_metrics(metrics)

        # кнопки массовых действий
        n_marked = len(self.marked)
        if hasattr(self, "bulk_delete_btn"):
            try:
                self.bulk_delete_btn.config(
                    text=f"Удалить ({n_marked})",
                    state="normal" if n_marked else "disabled")
                filled = set(self._filled_indices())
                all_marked = bool(filled) and self.marked >= filled
                self.mark_all_btn.config(
                    text="Снять все" if all_marked else "Выбрать все",
                    state="normal" if filled else "disabled")
                self.clear_all_btn.config(
                    state="normal" if filled else "disabled")
            except tk.TclError:
                pass

    def show_hotkeys(self):
        messagebox.showinfo(
            "Горячие клавиши",
            "Ctrl+O  — выбрать фото\n"
            "Ctrl+S  — сохранить\n"
            "Ctrl+Shift+S  — сохранить как…\n"
            "Ctrl+Shift+C  — копировать коллаж в буфер\n"
            "Ctrl+Z  — отменить\n"
            "Ctrl+Y  — повторить\n"
            "Ctrl+,  — настройки\n"
            "F5      — обновить предпросмотр\n"
            "Escape  — снять отметки / выделение слота\n"
            "Ctrl+A  — отметить все фото\n"
            "Delete  — убрать отмеченные фото (или выделенное)\n"
            "Ctrl+E  — редактор фото (выделенный слот)\n\n"
            "Мышь:\n"
            "Клик по пустому слоту   — выбрать файл\n"
            "Клик по двум слотам     — swap\n"
            "Ctrl/Shift+клик         — отметить для удаления\n"
            "Двойной клик            — заменить фото\n"
            "ПКМ по слоту            — контекстное меню"
        )

    def show_about(self):
        from . import branding
        messagebox.showinfo(
            f"О программе — {branding.APP_NAME}",
            branding.about_text()
            + "\n\nПлагины: " + (", ".join(self.plugin_flags.keys()) or "нет")
        )

    # ==================================================================
    #  API ДЛЯ ПЛАГИНОВ
    # ==================================================================
    def add_menu_item(self, menu_name, label, command, accelerator=None):
        items = self.plugin_actions.setdefault(menu_name, [])
        for item in items:
            if (item.get("label") == label
                    and item.get("accelerator") == accelerator):
                return True
        items.append({
            "label": label,
            "command": command,
            "accelerator": accelerator,
        })
        return True

    def add_menu(self, name):
        self.plugin_actions.setdefault(name, [])
        return None

    def add_slot_action(self, label, command, needs_photo=True):
        """Пункт контекстного меню слота. command(idx) вызывается с номером слота."""
        for act in self.slot_actions:
            if act["label"] == label:
                act["command"] = command
                return
        self.slot_actions.append({"label": label, "command": command,
                                  "needs_photo": needs_photo})

    def add_slots_rebuilt_hook(self, fn, call_now=True):
        """fn() вызывается после каждой пересборки слотов (смена шаблона,
        undo, очистка…) и один раз сразу, если call_now."""
        if fn not in self.slots_rebuilt_hooks:
            self.slots_rebuilt_hooks.append(fn)
        if call_now:
            fn()

    def register_collage_hook(self, fn):
        self.collage_hooks.append(fn)

    def apply_collage_hooks(self, img, for_preview=False):
        for fn in list(self.collage_hooks):
            try:
                res = fn(img, self, for_preview)
                if res is not None:
                    img = res
            except Exception as e:
                print(f"collage hook error: {e}")
        return img

    # ==================================================================
    #  ПРОЧЕЕ
    # ==================================================================
    def _bind_shortcuts(self):
        self.root.bind("<Control-o>", lambda e: self.choose_photos_dialog())
        self.root.bind("<Control-s>", lambda e: self.combine_and_save(force_dialog=False))
        self.root.bind("<Control-S>", lambda e: self.combine_and_save(force_dialog=True))
        self.root.bind("<F5>", lambda e: self.update_preview())
        self.root.bind("<Escape>", lambda e: self._on_escape())
        self.root.bind("<Delete>", lambda e: self._on_delete_key())
        self.root.bind("<Control-a>", lambda e: self._on_select_all_key())
        self.root.bind("<Control-A>", lambda e: self._on_select_all_key())
        self.root.bind("<Control-Shift-C>", lambda e: self._copy_collage_shortcut())
        self.root.bind("<Control-comma>", lambda e: self.show_settings())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-Z>", lambda e: self.redo())
        self.root.bind("<Control-y>", lambda e: self.redo())

    def on_close(self):
        try:
            if hasattr(self, "status_bar"):
                self.status_bar.stop()
        except Exception:
            pass
        self.config.save()
        if self._tmp_dir:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self.root.destroy()


def run():
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
        print("ℹ tkinterdnd2 не установлен — drag & drop будет отключён.")
    app = App(root)

    # ярлык «Проверить обновления» из меню Пуск запускает программу с этим ключом
    if "--check-updates" in sys.argv:
        def _check_now():
            try:
                from .plugins import updater_ui
                updater_ui.open_update_dialog(app)
            except Exception as e:
                print(f"[update] --check-updates: {e}")
        root.after(1500, _check_now)

    root.mainloop()