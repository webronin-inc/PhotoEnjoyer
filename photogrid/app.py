"""Главный класс приложения PhotoGrid."""
import os
import random
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser

from PIL import Image, ImageTk

from .config import Config, LAYOUTS, IMAGE_EXTS, DEFAULTS
from . import branding
from .core import build_collage
from .theme import apply_theme, DARK, LIGHT
from .ui_widgets import (
    HoverButton, Slot, LogoMark, IconButton, ColorSwatch,
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

        # История для отмены/повтора
        self._undo_stack = []
        self._redo_stack = []
        self._undo_limit = 50
        self._last_layout_cols_rows = (_cols, _rows)
        self._status_reset_job = None       # ← инициализация до использования

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

        # ---- tk-переменные ----
        self.layout_var  = tk.StringVar(value=self.config["layout"])
        self.mode_var    = tk.StringVar(value=self.config["mode"])
        self.cell_var    = tk.IntVar(value=self.config["cell_size"])
        self.border_var  = tk.IntVar(value=self.config["border"])
        self.quality_var = tk.DoubleVar(value=self.config["quality"])

        self.ttk = apply_theme(self.root, self.config["theme"])

        self._build_layout()
        self._build_rail()
        self._build_body()
        self._build_statusbar()
        self._bind_shortcuts()

        for v in (self.layout_var, self.mode_var, self.cell_var, self.border_var):
            v.trace_add("write", lambda *a: self._on_settings_change())

        # Плагины
        from .plugins import loader
        loader.load_all(self)
        self._plugins_loaded = True

        self.update_preview()
        self.update_status()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ==================================================================
    #  ИКОНКА ОКНА
    # ==================================================================
    def _set_window_icon(self):
        """Устанавливает свою иконку для окна и панели задач."""
        from pathlib import Path
        candidates = [
            Path(__file__).parent / "icon.ico",
        ]
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

        sections = [
            ("collage", "Коллаж", "Собрать коллаж из фото"),
            ("plugins", "Плагины", "Загруженные плагины и их действия"),
            ("batch",   "Пакетная обработка", "Обработать сразу много папок"),
            ("cloud",   "Облако", "Экспорт в облако (скоро)"),
        ]
        for key, tip, desc in sections:
            icon_kind = {"collage": "collage", "plugins": "plugins",
                         "batch": "batch", "cloud": "cloud"}[key]
            btn = RailButton(self.rail, p, kind=icon_kind, size=42,
                             command=lambda k=key: self._set_section(k),
                             tooltip=tip)
            btn.pack(pady=3)
            self.rail_buttons[key] = btn

        tk.Frame(self.rail, bg=p["bg"]).pack(fill=tk.BOTH, expand=True)

        bottom = [
            ("theme",    "Тема",         self.toggle_theme),
            ("settings", "Настройки",    self.show_settings),
            ("help",     "Справка",      self.show_about),
        ]
        for icon_kind, tip, cmd in bottom:
            btn = RailButton(self.rail, p, kind=icon_kind, size=42,
                             command=cmd, tooltip=tip)
            btn.pack(pady=3)
            self.rail_buttons[icon_kind] = btn

        tk.Frame(self.rail, bg=p["bg"], height=16).pack()
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

        for v in self.views.values():
            v.pack_forget()

        target = self.views.get(key)
        if target is not None:
            target.pack(fill=tk.BOTH, expand=True,
                        padx=(0, 14), pady=(14, 0))

        for k, btn in self.rail_buttons.items():
            btn.set_active(k == key)
        self.active_section = key

    def show_settings(self):
        from .screens.settings import open_settings_dialog
        open_settings_dialog(self)

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

        hint_text = ("Клик — выбрать / swap · Двойной — заменить\n"
                     "ПКМ — действия · перетащите файлы")
        tk.Label(left, text=hint_text, bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 8), justify="left"
                 ).pack(fill=tk.X, padx=18, pady=(0, 12))

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
        mode_frame = tk.Frame(sec1, bg=p["surface"])
        mode_frame.grid(row=1, column=1, sticky="w", padx=(16, 0), pady=6)
        ttk.Radiobutton(mode_frame, text="Вписать",
                        variable=self.mode_var, value="fit"
                        ).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Radiobutton(mode_frame, text="Заполнить",
                        variable=self.mode_var, value="fill"
                        ).pack(side=tk.LEFT)

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

        copy_btn = tk.Button(btnbox, text="  Копировать в буфер",
                             bg=p["surface_alt"], fg=p["text"],
                             activebackground=p["surface_hi"],
                             activeforeground=p["text"],
                             bd=0, relief="flat", cursor="hand2",
                             font=("Segoe UI", 10), anchor="w",
                             padx=14, pady=10,
                             command=self.copy_collage_to_clipboard_with_ui)
        copy_btn.pack(fill=tk.X, pady=(0, 6))

        b2 = tk.Button(btnbox, text="  Загрузить из папки",
                       bg=p["surface_alt"], fg=p["text"],
                       activebackground=p["surface_hi"],
                       activeforeground=p["text"],
                       bd=0, relief="flat", cursor="hand2",
                       font=("Segoe UI", 10), anchor="w",
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

        # Регистрируем как collage view
        self.views["collage"] = body

    # ==================================================================
    #  СЛОТЫ — динамические
    # ==================================================================
    def _build_slots(self):
        """Пересоздаёт слоты под текущую раскладку."""
        p = self.palette
        for w in self.slots_grid.winfo_children():
            w.destroy()

        self.slot_widgets = []
        cols, rows = LAYOUTS.get(self.config["layout"], (2, 2))
        total = cols * rows

        # Нормализуем список фото под новое количество слотов
        if len(self.photos) < total:
            self.photos.extend([None] * (total - len(self.photos)))
        elif len(self.photos) > total:
            self.photos = self.photos[:total]

        self.thumb_refs = [None] * total

        # Сетка слотов: не более 3 в ряд
        grid_cols = max(2, min(cols, 3))

        for i in range(total):
            slot = Slot(
                self.slots_grid, p, i,
                on_click=lambda e, idx=i: self.on_slot_click(idx),
                on_right_click=lambda e, idx=i: self.on_slot_context_menu(e, idx),
                on_double_click=lambda e, idx=i: self.on_slot_replace(idx),
            )
            slot.grid(row=i // grid_cols, column=i % grid_cols,
                      padx=6, pady=6)
            self.slot_widgets.append(slot)

        self.slot_containers = self.slot_widgets
        self.slot_labels = self.slot_widgets

        for i in range(total):
            self.update_slot(i)

    # ==================================================================
    #  STATUS BAR
    # ==================================================================
    def _build_statusbar(self):
        p = self.palette
        tk.Frame(self.root, bg=p["border_soft"], height=1).pack(
            fill=tk.X, side=tk.BOTTOM)

        self.status_bar = AnimatedStatusBar(self.root, p, height=34)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Для совместимости со старым кодом
        self.status_var = tk.StringVar(value="Готово")

        # Сброс отложенных сообщений (инициализация)
        self._status_reset_job = None

    # ==================================================================
    #  СЛОТЫ: содержимое и миниатюры
    # ==================================================================
    def update_slot(self, idx):
        if idx >= len(self.slot_widgets):
            return
        slot = self.slot_widgets[idx]
        path = self.photos[idx] if idx < len(self.photos) else None
        if path is None:
            slot.set_thumb(None)
            if idx < len(self.thumb_refs):
                self.thumb_refs[idx] = None
        else:
            try:
                thumb = self._make_thumb(path, 145)
                slot.set_thumb(thumb)
                if idx < len(self.thumb_refs):
                    self.thumb_refs[idx] = thumb
            except Exception as e:
                print(f"Ошибка загрузки миниатюры слота {idx}: {e}")
                slot.set_thumb(None)
                if idx < len(self.thumb_refs):
                    self.thumb_refs[idx] = None
        slot.update_border(selected=(self.selected_slot == idx))

    def _make_thumb(self, path, size):
        from .core import load_rgb
        img = load_rgb(path, self.palette["slot_bg"])
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGB", (size, size), self.palette["slot_bg"])
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
        return ImageTk.PhotoImage(canvas)

    # ==================================================================
    #  КЛИКИ ПО СЛОТАМ
    # ==================================================================
    def on_slot_click(self, idx):
        if self.photos[idx] is None:
            path = filedialog.askopenfilename(
                title=f"Выберите фото {idx + 1}",
                filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                           ("Все файлы", "*.*")]
            )
            if path:
                self._push_undo("Выбор фото")
                self.photos[idx] = path
                self.update_slot(idx)
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
            self.update_slot(a)
            self.update_slot(b)
            self.schedule_preview()

    def on_slot_context_menu(self, event, idx):
        """ПКМ-меню на слоте."""
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

    def on_slot_replace(self, idx):
        path = filedialog.askopenfilename(
            title=f"Заменить фото {idx + 1}",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                       ("Все файлы", "*.*")]
        )
        if path:
            self._push_undo("Замена фото")
            self.photos[idx] = path
            self.update_slot(idx)
            self.schedule_preview()
            self.update_status()

    def _deselect(self):
        if self.selected_slot is not None:
            old = self.selected_slot
            self.selected_slot = None
            self.update_slot(old)

    # ==================================================================
    #  ПОВОРОТ / ОТРАЖЕНИЕ / ПРОВОДНИК / ПУТЬ
    # ==================================================================
    def rotate_slot(self, idx, degrees):
        import tempfile
        from pathlib import Path
        path = self.photos[idx]
        if path is None:
            return
        try:
            img = Image.open(path)
            rotated = img.rotate(-degrees, expand=True)
            out = Path(tempfile.gettempdir()) / f"pe_rot_{idx}_{abs(degrees)}.png"
            rotated.convert("RGB").save(out, "PNG")
            self._push_undo("Поворот фото")
            self.photos[idx] = str(out)
            self.update_slot(idx)
            self.schedule_preview()
            self.set_status(f"Фото {idx + 1} повёрнуто на {degrees}°")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось повернуть:\n{e}")

    def flip_slot(self, idx, direction="h"):
        import tempfile
        from pathlib import Path
        path = self.photos[idx]
        if path is None:
            return
        try:
            img = Image.open(path)
            if direction == "h":
                flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
            else:
                flipped = img.transpose(Image.FLIP_TOP_BOTTOM)
            out = Path(tempfile.gettempdir()) / f"pe_flip_{idx}_{direction}.png"
            flipped.convert("RGB").save(out, "PNG")
            self._push_undo("Отражение фото")
            self.photos[idx] = str(out)
            self.update_slot(idx)
            self.schedule_preview()
            self.set_status(f"Фото {idx + 1} отражено")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось отразить:\n{e}")

    def reveal_in_explorer(self, idx):
        path = self.photos[idx]
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
            "config": {k: self.config.get(k) for k in cfg_keys},
            "label": "",
        }
        state = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._apply_state(state)
        self.set_status("Повторено")

    def _apply_state(self, state):
        self.photos = list(state["photos"])
        cfg = state["config"]
        for k, v in cfg.items():
            self.config[k] = v
        self.config.save()

        self.layout_var.set(self.config["layout"])
        self.mode_var.set(self.config["mode"])
        self.cell_var.set(self.config["cell_size"])
        self.border_var.set(self.config["border"])
        self.quality_var.set(self.config["quality"])
        if hasattr(self, "quality_label"):
            self.quality_label.config(text=f"{self.config['quality']}%")
        if hasattr(self, "quality_slider"):
            self.quality_slider.set(self.config["quality"])
        if hasattr(self, "border_color_btn"):
            self.border_color_btn.set_color(self.config["border_color"])
        if hasattr(self, "bg_color_btn"):
            self.bg_color_btn.set_color(self.config["bg_color"])

        self._last_layout_cols_rows = LAYOUTS.get(
            self.config["layout"], (2, 2))
        self._build_slots()
        self.schedule_preview()
        self.update_status()

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
            self.update_slot(i)
        self.selected_slot = None
        self.schedule_preview()
        self.update_status()

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
            self.update_slot(i)
        self.selected_slot = None
        self.schedule_preview()
        self.update_status()

    def clear_all(self):
        if not any(self.photos):
            return
        if not messagebox.askyesno("Подтверждение", "Очистить все выбранные фото?"):
            return
        self._push_undo("Очистка")
        self.photos = [None] * len(self.photos)
        self.selected_slot = None
        for i in range(len(self.photos)):
            self.update_slot(i)
        self.schedule_preview()
        self.update_status()

    def shuffle_photos(self):
        self._push_undo("Перемешивание")
        filled = [p for p in self.photos if p is not None]
        random.shuffle(filled)
        for i in range(len(self.photos)):
            self.photos[i] = filled[i] if i < len(filled) else None
            self.update_slot(i)
        self.selected_slot = None
        self.schedule_preview()

    def reset_settings(self):
        if not messagebox.askyesno("Сброс", "Сбросить все настройки по умолчанию?"):
            return
        for k, v in DEFAULTS.items():
            if k != "theme":
                self.config[k] = v
        self.layout_var.set(self.config["layout"])
        self.mode_var.set(self.config["mode"])
        self.cell_var.set(self.config["cell_size"])
        self.border_var.set(self.config["border"])
        self.quality_var.set(self.config["quality"])
        if hasattr(self, "quality_label"):
            self.quality_label.config(text=f"{self.config['quality']}%")
        if hasattr(self, "border_color_btn"):
            self.border_color_btn.set_color(self.config["border_color"])
        if hasattr(self, "bg_color_btn"):
            self.bg_color_btn.set_color(self.config["bg_color"])
        if hasattr(self, "quality_slider"):
            self.quality_slider.set(self.config["quality"])
        self.config.save()
        self.update_preview()

    def toggle_theme(self):
        self.config["theme"] = "light" if self.config["theme"] == "dark" else "dark"
        self.config.save()
        self.reload_ui()

    def reload_ui(self):
        saved_photos = list(self.photos)
        saved_selected = self.selected_slot
        saved_last_save = self.last_save_path

        # Останавливаем старую анимацию статус-бара
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
            loader.load_all(self)
        except Exception as e:
            print(f"reload_ui: плагины не перезагружены: {e}")

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

    def update_preview(self):
        self._preview_job = None
        p = self.palette
        if not any(self.photos):
            self.preview_label.config(
                image="",
                text="Здесь появится коллаж\n\nВыберите фото\nили перетащите их в слоты",
                bg=p["bg"],
            )
            self.preview_ref = None
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)
            return
        try:
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(0.5)
                self.root.update_idletasks()
            img = build_collage(self.photos, self.config, for_preview=True)
            img = self.apply_collage_hooks(img, for_preview=True)
            img.thumbnail((620, 620), Image.LANCZOS)
            self.preview_ref = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_ref, text="", bg=p["bg"])
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)
        except Exception as e:
            self.preview_label.config(image="", text=f"Ошибка:\n{e}", bg=p["bg"])
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)

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
            img = build_collage(self.photos, self.config, for_preview=False)
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
                filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("Все файлы", "*.*")],
                initialfile="collage.jpg",
            )
            if not save_path:
                return
            self.last_save_path = save_path

        self.set_status("Сохранение…")
        if hasattr(self, "status_bar"):
            self.status_bar.set_progress(0.15)
            self.root.update_idletasks()
        try:
            img = build_collage(self.photos, self.config, for_preview=False)
            img = self.apply_collage_hooks(img, for_preview=False)
            ext = os.path.splitext(save_path)[1].lower()
            if ext in (".jpg", ".jpeg"):
                img.save(save_path, "JPEG",
                         quality=int(self.config["quality"]), optimize=True)
            elif ext == ".png":
                img.save(save_path, "PNG")
            else:
                img.save(save_path)

            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(1.0)
                self.root.update_idletasks()

            size_mb = os.path.getsize(save_path) / (1024 * 1024)
            self.set_status(
                f"Сохранено: {os.path.basename(save_path)}  ({img.width}×{img.height}, {size_mb:.2f} МБ)")
            messagebox.showinfo(
                "Готово!",
                f"Файл сохранён:\n{save_path}\n\n"
                f"Размер: {img.width}×{img.height}\nОбъём: {size_mb:.2f} МБ")

            # Сбрасываем прогресс с небольшой задержкой, чтобы пользователь увидел «100%»
            if hasattr(self, "status_bar"):
                self.root.after(400, lambda: self.status_bar.set_progress(None))
        except Exception as e:
            self.set_status("Ошибка сохранения")
            if hasattr(self, "status_bar"):
                self.status_bar.set_progress(None)
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

    # ==================================================================
    #  СТАТУС / СПРАВКА
    # ==================================================================
    def set_status(self, text):
        """Короткое сообщение (успех/ошибка/работа). Автосброс к базовому."""
        state = self._infer_status_state(text)

        if hasattr(self, "status_bar"):
            self.status_bar.set_status(text, state)

        # Автосброс для временных сообщений
        if state in ("success", "error"):
            if self._status_reset_job:
                try:
                    self.root.after_cancel(self._status_reset_job)
                except Exception:
                    pass
            self._status_reset_job = self.root.after(2500, self._reset_status)

    def _infer_status_state(self, text):
        """Определяет визуальное состояние по тексту сообщения."""
        low = text.lower()
        if any(k in low for k in ("ошибка", "не удалось", "не найден", "не установлен")):
            return "error"
        if any(k in low for k in ("сохран", "загруз", "обновля", "обработ",
                                  "примен", "проверка", "подготовка")):
            return "busy"
        if any(k in low for k in ("готово", "сохранено", "скопирован",
                                  "применена", "применено")):
            return "success"
        return "ready"

    def _reset_status(self):
        """Возвращает базовый статус после временного сообщения."""
        self._status_reset_job = None
        self.update_status()

    def update_status(self):
        """Базовый статус — постоянный, пока не перебит временным."""
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

        # Метрики справа
        self.status_bar.set_metrics([
            ("отмены", len(self._undo_stack)),
            ("плагины", len(self.plugin_flags)),
        ])

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
            "Escape  — снять выделение слота\n\n"
            "Мышь:\n"
            "Клик по пустому слоту   — выбрать файл\n"
            "Клик по двум слотам     — swap\n"
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
        self.root.bind("<Escape>", lambda e: self._deselect())
        self.root.bind("<Control-Shift-C>", lambda e: self._copy_collage_shortcut())
        self.root.bind("<Control-comma>", lambda e: self.show_settings())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-Z>", lambda e: self.redo())   # Ctrl+Shift+Z
        self.root.bind("<Control-y>", lambda e: self.redo())

    def on_close(self):
        try:
            if hasattr(self, "status_bar"):
                self.status_bar.stop()
        except Exception:
            pass
        self.config.save()
        self.root.destroy()


def run():
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
        print("ℹ tkinterdnd2 не установлен — drag & drop будет отключён.")
    app = App(root)
    root.mainloop()