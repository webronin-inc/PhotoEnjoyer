"""Главный класс приложения PhotoGrid."""
import os
import random
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser

from PIL import Image, ImageTk

from .config import Config, LAYOUTS, IMAGE_EXTS, DEFAULTS
from . import branding
from .core import build_collage
from .theme import apply_theme, DARK, LIGHT
from .ui_widgets import HoverButton, ModernMenuButton, style_dropdown, Slot
import sys

# Страховка: если приложение запущено с console=True и cp1251 —
# переключаем stdout/stderr на UTF-8.
for _s in (sys.stdout, sys.stderr):
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
            
class App:
    """Главное окно приложения. Плагины получают этот объект в register(app)."""

    def __init__(self, root):
        self.root = root
        self.config = Config()
        self.palette = DARK if self.config["theme"] == "dark" else LIGHT

        self.root.title(branding.window_title())
        self.root.geometry("1260x820")
        self.root.minsize(1050, 700)

        # --- состояние ---
        self.photos = [None, None, None, None]
        self.selected_slot = None
        self.thumb_refs = [None] * 4
        self.preview_ref = None
        self.last_save_path = None
        self._preview_job = None
        self.plugin_flags = {}
        self.collage_hooks = []
        self.menus = {}                 # имя меню -> tk.Menu
        self.menu_buttons = []          # кнопки верхнего бара

        # --- tk-переменные ---
        self.layout_var  = tk.StringVar(value=self.config["layout"])
        self.mode_var    = tk.StringVar(value=self.config["mode"])
        self.cell_var    = tk.IntVar(value=self.config["cell_size"])
        self.border_var  = tk.IntVar(value=self.config["border"])
        self.quality_var = tk.DoubleVar(value=self.config["quality"])

        # --- тема ---
        self.ttk = apply_theme(self.root, self.config["theme"])

        # --- построение ---
        self._build_header()
        self._build_body()
        self._build_statusbar()
        self._bind_shortcuts()

        for v in (self.layout_var, self.mode_var, self.cell_var, self.border_var):
            v.trace_add("write", lambda *a: self._on_settings_change())

        # --- плагины (после UI, чтобы могли добавлять пункты в меню и цепляться к слотам) ---
        from .plugins import loader
        loader.load_all(self)

        # --- финальный апдейт ---
        self.update_preview()
        self.update_status()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ==================================================================
    #  HEADER (современное меню)
    # ==================================================================
    def _build_header(self):
        p = self.palette
        header = tk.Frame(self.root, bg=p["surface"], height=52)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        # Логотип/название
        brand = tk.Frame(header, bg=p["surface"])
        brand.pack(side=tk.LEFT, padx=(18, 8))
        tk.Label(brand, text="◆", bg=p["surface"], fg=p["accent"],
                 font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        tk.Label(brand, text=branding.APP_NAME, bg=p["surface"], fg=p["text"],
                font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT, padx=(8, 0))

        # Разделитель
        tk.Frame(header, bg=p["border"], width=1).pack(side=tk.LEFT, fill=tk.Y,
                                                       padx=14, pady=12)

        # --- Меню: Файл ---
        file_menu = self._make_menu()
        self.menus["Файл"] = file_menu
        file_menu.add_command(label="Выбрать фото…", accelerator="Ctrl+O",
                              command=self.choose_photos_dialog)
        file_menu.add_command(label="Загрузить из папки (авто)…",
                              command=self.load_from_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить", accelerator="Ctrl+S",
                              command=lambda: self.combine_and_save(force_dialog=False))
        file_menu.add_command(label="Сохранить как…", accelerator="Ctrl+Shift+S",
                              command=lambda: self.combine_and_save(force_dialog=True))
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.on_close)
        self._add_menu_button(header, "Файл", file_menu)

        # --- Меню: Правка ---
        edit_menu = self._make_menu()
        self.menus["Правка"] = edit_menu
        edit_menu.add_command(label="Очистить всё", command=self.clear_all)
        edit_menu.add_command(label="Перемешать", command=self.shuffle_photos)
        edit_menu.add_separator()
        edit_menu.add_command(label="Сбросить настройки", command=self.reset_settings)
        self._add_menu_button(header, "Правка", edit_menu)

        # --- Меню: Вид ---
        view_menu = self._make_menu()
        self.menus["Вид"] = view_menu
        for name in LAYOUTS:
            view_menu.add_radiobutton(label=name, variable=self.layout_var, value=name)
        view_menu.add_separator()
        view_menu.add_command(label="Переключить тему", command=self.toggle_theme)
        self._add_menu_button(header, "Вид", view_menu)

        # --- Меню: Справка ---
        help_menu = self._make_menu()
        self.menus["Справка"] = help_menu
        help_menu.add_command(label="Горячие клавиши", command=self.show_hotkeys)
        help_menu.add_command(label="О программе", command=self.show_about)
        self._add_menu_button(header, "Справка", help_menu)

        # --- Правая сторона: переключатель темы ---
        right = tk.Frame(header, bg=p["surface"])
        right.pack(side=tk.RIGHT, padx=14)
        theme_btn = HoverButton(
            right,
            normal_bg=p["surface"], hover_bg=p["surface_alt"],
            normal_fg=p["text_dim"], hover_fg=p["text"],
            text="☀" if self.config["theme"] == "dark" else "☾",
            font=("Segoe UI", 14), padx=10, pady=4,
            command=self.toggle_theme,
        )
        theme_btn.pack(side=tk.RIGHT)
        self.theme_button = theme_btn

        # разделительная полоса
        tk.Frame(self.root, bg=p["border"], height=1).pack(fill=tk.X)

    def _make_menu(self):
        """Создаёт tk.Menu с современным стилем."""
        m = tk.Menu(self.root, tearoff=0)
        style_dropdown(m, self.palette)
        return m

    def _add_menu_button(self, parent, text, menu):
        btn = ModernMenuButton(parent, text, self.palette, menu=menu)
        btn.pack(side=tk.LEFT, padx=2, pady=8)
        self.menu_buttons.append(btn)

    # ==================================================================
    #  BODY
    # ==================================================================
    def _build_body(self):
        p = self.palette
        body = tk.Frame(self.root, bg=p["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        # ---------- ЛЕВАЯ: слоты ----------
        left = tk.Frame(body, bg=p["surface"], bd=0)
        left.pack(side=tk.LEFT, fill=tk.Y)

        # заголовок карточки
        head = tk.Frame(left, bg=p["surface"])
        head.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(head, text="ФОТОГРАФИИ", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        hint_text = ("Клик — выбрать / swap • Двойной — заменить\n"
                     "ПКМ — очистить"
                     + ("  •  перетащите файлы" if True else ""))
        tk.Label(left, text=hint_text, bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 8), justify="left"
                 ).pack(fill=tk.X, padx=16, pady=(0, 10))

        grid = tk.Frame(left, bg=p["surface"])
        grid.pack(padx=16, pady=(0, 16))

        self.slot_widgets = []
        for i in range(4):
            slot = Slot(
                grid, p, i,
                on_click=lambda e, idx=i: self.on_slot_click(idx),
                on_right_click=lambda e, idx=i: self.on_slot_clear(idx),
                on_double_click=lambda e, idx=i: self.on_slot_replace(idx),
            )
            slot.grid(row=i // 2, column=i % 2, padx=6, pady=6)
            self.slot_widgets.append(slot)

        # алиасы для совместимости с плагинами
        self.slot_containers = self.slot_widgets
        self.slot_labels = [s.label for s in self.slot_widgets]

        # ---------- ЦЕНТР: настройки ----------
        mid = tk.Frame(body, bg=p["surface"])
        mid.pack(side=tk.LEFT, fill=tk.Y, padx=(14, 0))

        tk.Label(mid, text="НАСТРОЙКИ", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(14, 12))

        form = tk.Frame(mid, bg=p["surface"])
        form.pack(fill=tk.X, padx=18)
        form.columnconfigure(1, weight=1)

        row = 0

        # Раскладка
        tk.Label(form, text="Раскладка", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        import tkinter.ttk as ttk
        ttk.Combobox(form, textvariable=self.layout_var,
                     values=list(LAYOUTS.keys()), state="readonly", width=24
                     ).grid(row=row, column=1, sticky="ew", pady=6, padx=(12, 0))
        row += 1

        # Режим
        tk.Label(form, text="Режим", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        mf = tk.Frame(form, bg=p["surface"])
        mf.grid(row=row, column=1, sticky="w", pady=6, padx=(12, 0))
        ttk.Radiobutton(mf, text="Вписать", variable=self.mode_var,
                        value="fit").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(mf, text="Заполнить", variable=self.mode_var,
                        value="fill").pack(side=tk.LEFT)
        row += 1

        # Размер ячейки
        tk.Label(form, text="Размер ячейки, px", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=50, to=4000, increment=50,
                    textvariable=self.cell_var, width=8
                    ).grid(row=row, column=1, sticky="w", pady=6, padx=(12, 0))
        row += 1

        # Рамка
        tk.Label(form, text="Рамка, px", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=300, increment=5,
                    textvariable=self.border_var, width=8
                    ).grid(row=row, column=1, sticky="w", pady=6, padx=(12, 0))
        row += 1

        # Цвета
        tk.Label(form, text="Цвет рамки", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        self.border_color_btn = HoverButton(
            form,
            normal_bg=self.config["border_color"],
            hover_bg=self.config["border_color"],
            text="", width=6, height=1, bd=0, relief="flat",
            command=self._choose_border_color,
        )
        self.border_color_btn.grid(row=row, column=1, sticky="w", pady=6, padx=(12, 0))
        row += 1

        tk.Label(form, text="Фон ячейки", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        self.bg_color_btn = HoverButton(
            form,
            normal_bg=self.config["bg_color"],
            hover_bg=self.config["bg_color"],
            text="", width=6, height=1, bd=0, relief="flat",
            command=self._choose_bg_color,
        )
        self.bg_color_btn.grid(row=row, column=1, sticky="w", pady=6, padx=(12, 0))
        row += 1

        # Качество
        tk.Label(form, text="Качество JPEG", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        qf = tk.Frame(form, bg=p["surface"])
        qf.grid(row=row, column=1, sticky="ew", pady=6, padx=(12, 0))
        qf.columnconfigure(0, weight=1)
        ttk.Scale(qf, from_=60, to=100, orient=tk.HORIZONTAL,
                  variable=self.quality_var, command=self._on_quality_change
                  ).grid(row=0, column=0, sticky="ew")
        self.quality_label = tk.Label(qf, text=f"{int(self.config['quality'])}%",
                                      bg=p["surface"], fg=p["text"],
                                      font=("Segoe UI", 9), width=4)
        self.quality_label.grid(row=0, column=1, padx=(8, 0))

        # Разделитель
        tk.Frame(mid, bg=p["border"], height=1).pack(fill=tk.X, padx=18, pady=14)

        # Кнопки
        btnbox = tk.Frame(mid, bg=p["surface"])
        btnbox.pack(fill=tk.X, padx=18, pady=(0, 18))

        ttk.Button(btnbox, text="💾  Сохранить как…", style="Accent.TButton",
                   command=lambda: self.combine_and_save(force_dialog=True)
                   ).pack(fill=tk.X, pady=(0, 6))

        ttk.Button(btnbox, text="📂  Загрузить из папки",
                   command=self.load_from_folder
                   ).pack(fill=tk.X, pady=3)

        ttk.Button(btnbox, text="🔄  Обновить предпросмотр", style="Ghost.TButton",
                   command=self.update_preview
                   ).pack(fill=tk.X, pady=(10, 0))

        # ---------- ПРАВАЯ: предпросмотр ----------
        right = tk.Frame(body, bg=p["surface"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))

        rh = tk.Frame(right, bg=p["surface"])
        rh.pack(fill=tk.X, padx=18, pady=(14, 4))
        tk.Label(rh, text="ПРЕДПРОСМОТР", bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        self.preview_label = tk.Label(
            right,
            text="Здесь появится коллаж\n\nВыберите 4 фото или перетащите их в слоты",
            bg=p["surface_alt"], fg=p["text_dim"],
            font=("Segoe UI", 11), justify="center",
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=18, pady=(4, 18))

    # ==================================================================
    #  STATUS BAR
    # ==================================================================
    def _build_statusbar(self):
        p = self.palette
        tk.Frame(self.root, bg=p["border"], height=1).pack(fill=tk.X, side=tk.BOTTOM)
        bar = tk.Frame(self.root, bg=p["surface"], height=30)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        self.status_var = tk.StringVar(value="Готово")
        tk.Label(bar, textvariable=self.status_var, bg=p["surface"], fg=p["text_dim"],
                 font=("Segoe UI", 9), anchor="w", padx=16
                 ).pack(fill=tk.BOTH, expand=True)

    # ==================================================================
    #  СЛОТЫ
    # ==================================================================
    def update_slot(self, idx):
        slot = self.slot_widgets[idx]
        path = self.photos[idx]

        if path is None:
            slot.label.config(image="", text=f"＋\n\nФото {idx + 1}",
                              bg=self.palette["slot_bg"], fg=self.palette["text_dim"])
            self.thumb_refs[idx] = None
        else:
            try:
                thumb = self._make_thumb(path, 150)
                slot.label.config(image=thumb, text="",
                                  bg=self.palette["slot_bg"])
                self.thumb_refs[idx] = thumb
            except Exception as e:
                slot.label.config(image="", text=f"Ошибка:\n{e}",
                                  bg="#3a1a1a", fg="#ff8888")
                self.thumb_refs[idx] = None

        slot.update_border(selected=(self.selected_slot == idx))

    def _make_thumb(self, path, size):
        from .core import load_rgb
        img = load_rgb(path, self.palette["slot_bg"])
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGB", (size, size), self.palette["slot_bg"])
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
        return ImageTk.PhotoImage(canvas)

    def on_slot_click(self, idx):
        if self.photos[idx] is None:
            path = filedialog.askopenfilename(
                title=f"Выберите фото {idx + 1}",
                filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                           ("Все файлы", "*.*")]
            )
            if path:
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
            self.photos[a], self.photos[b] = self.photos[b], self.photos[a]
            self.selected_slot = None
            self.update_slot(a)
            self.update_slot(b)
            self.schedule_preview()

    def on_slot_clear(self, idx):
        if self.photos[idx] is not None:
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
    #  ДЕЙСТВИЯ
    # ==================================================================
    def choose_photos_dialog(self):
        paths = filedialog.askopenfilenames(
            title="Выберите до 4 фотографий",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif"),
                       ("Все файлы", "*.*")]
        )
        if not paths:
            return
        paths = list(paths)[:4]
        for i in range(4):
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
        if len(files) < 4:
            messagebox.showinfo("Информация",
                                f"В папке найдено {len(files)} фото.\n"
                                f"Будут заполнены только они.")

        for i in range(4):
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
        self.photos = [None, None, None, None]
        self.selected_slot = None
        for i in range(4):
            self.update_slot(i)
        self.schedule_preview()
        self.update_status()

    def shuffle_photos(self):
        filled = [p for p in self.photos if p is not None]
        random.shuffle(filled)
        for i in range(4):
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
        self.quality_label.config(text=f"{self.config['quality']}%")
        self.border_color_btn.config(bg=self.config["border_color"])
        self.bg_color_btn.config(bg=self.config["bg_color"])
        self.config.save()
        self.update_preview()

    def toggle_theme(self):
        self.config["theme"] = "light" if self.config["theme"] == "dark" else "dark"
        self.config.save()
        messagebox.showinfo(
            "Тема изменена",
            "Тема будет применена после перезапуска приложения."
        )

    # ==================================================================
    #  ЦВЕТА
    # ==================================================================
    def _choose_border_color(self):
        color = colorchooser.askcolor(color=self.config["border_color"],
                                      title="Цвет рамки")[1]
        if color:
            self.config["border_color"] = color
            self.border_color_btn.config(bg=color)
            self.config.save()
            self.schedule_preview()

    def _choose_bg_color(self):
        color = colorchooser.askcolor(color=self.config["bg_color"],
                                      title="Цвет фона ячейки")[1]
        if color:
            self.config["bg_color"] = color
            self.bg_color_btn.config(bg=color)
            self.config.save()
            self.schedule_preview()

    def _on_quality_change(self, val):
        q = int(float(val))
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
                text="Здесь появится коллаж\n\nВыберите 4 фото или перетащите их в слоты",
                bg=p["surface_alt"],
            )
            self.preview_ref = None
            return
        try:
            img = build_collage(self.photos, self.config, for_preview=True)
            img = self.apply_collage_hooks(img, for_preview=True)
            img.thumbnail((620, 620), Image.LANCZOS)
            self.preview_ref = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_ref, text="",
                                      bg=p["surface_alt"])
        except Exception as e:
            self.preview_label.config(image="", text=f"Ошибка:\n{e}",
                                      bg=p["surface_alt"])

    # ==================================================================
    #  СОХРАНЕНИЕ
    # ==================================================================
    def combine_and_save(self, force_dialog=True):
        if any(p is None for p in self.photos):
            messagebox.showwarning("Внимание", "Сначала выберите все 4 фотографии!")
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

            size_mb = os.path.getsize(save_path) / (1024 * 1024)
            self.set_status(
                f"Сохранено: {save_path}  ({img.width}×{img.height}, {size_mb:.2f} МБ)"
            )
            messagebox.showinfo(
                "Готово!",
                f"Файл сохранён:\n{save_path}\n\n"
                f"Размер: {img.width}×{img.height}\nОбъём: {size_mb:.2f} МБ"
            )
        except Exception as e:
            self.set_status("Ошибка сохранения")
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

    # ==================================================================
    #  СТАТУС / СПРАВКА
    # ==================================================================
    def set_status(self, text):
        self.status_var.set(text)

    def update_status(self):
        n = sum(1 for p in self.photos if p)
        cols, rows = LAYOUTS.get(self.config["layout"], (2, 2))
        cell = int(self.config.get("cell_size", 0))
        b = int(self.config.get("border", 0))
        w = cols * cell + (cols + 1) * b
        h = rows * cell + (rows + 1) * b
        plugins = ", ".join(self.plugin_flags.keys()) or "нет"
        self.status_var.set(
            f"Выбрано: {n}/4   •   {w}×{h} px   •   "
            f"{self.config['layout']}   •   "
            f"{'вписать' if self.config['mode'] == 'fit' else 'заполнить'}   •   "
            f"плагины: {plugins}"
        )

    def show_hotkeys(self):
        dnd = ""
        if self.plugin_flags.get("drag_drop"):
            dnd = ("\n\nDrag & Drop:\n"
                   "Перетащите 1–4 файла (или папку) на слот —\n"
                   "они разложатся, начиная с этого слота.")
        messagebox.showinfo(
            "Горячие клавиши",
            "Ctrl+O            — выбрать фото\n"
            "Ctrl+S            — сохранить\n"
            "Ctrl+Shift+S   — сохранить как…\n"
            "F5                    — обновить предпросмотр\n"
            "Escape            — снять выделение слота\n\n"
            "Мышь:\n"
            "Клик по пустому слоту     — выбрать файл\n"
            "Клик по двум слотам       — swap\n"
            "Двойной клик               — заменить фото\n"
            "ПКМ по слоту                — очистить слот"
            + dnd
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
        """Добавить пункт в существующее меню ('Файл', 'Правка', 'Вид', 'Справка')."""
        menu = self.menus.get(menu_name)
        if menu is None:
            return False
        menu.add_command(label=label, command=command, accelerator=accelerator)
        return True

    def add_menu(self, name):
        """Создать новое верхнее меню. Возвращает tk.Menu."""
        menu = self._make_menu()
        self.menus[name] = menu
        header = self.menu_buttons[0].master if self.menu_buttons else self.root
        btn = ModernMenuButton(header, name, self.palette, menu=menu)
        if self.menu_buttons:
            last = self.menu_buttons[-1]
            btn.pack(side=tk.LEFT, padx=2, pady=8, before=last)
        else:
            btn.pack(side=tk.LEFT, padx=2, pady=8)
        self.menu_buttons.append(btn)
        return menu
    def register_collage_hook(self, fn):
        """Плагин регистрирует post-обработку готового коллажа.
        fn(image, app, for_preview) -> image | None
        """
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

    def on_close(self):
        self.config.save()
        self.root.destroy()


def run():
    """Точка входа. Пытается использовать DnD-root, если библиотека есть."""
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
        print("ℹ tkinterdnd2 не установлен — drag & drop будет отключён.")
        print("  Установите: pip install tkinterdnd2")

    app = App(root)
    root.mainloop()