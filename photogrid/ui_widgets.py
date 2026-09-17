"""Кастомные виджеты для современного вида."""
import tkinter as tk


class HoverButton(tk.Button):
    """Плоская кнопка с hover-эффектом."""

    def __init__(self, master, normal_bg, hover_bg, normal_fg=None, hover_fg=None, **kwargs):
        kwargs.setdefault("bg", normal_bg)
        kwargs.setdefault("fg", normal_fg or "#ffffff")
        kwargs.setdefault("activebackground", hover_bg)
        kwargs.setdefault("activeforeground", hover_fg or "#ffffff")
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor", "hand2")

        super().__init__(master, **kwargs)

        self._normal_bg = normal_bg
        self._hover_bg = hover_bg
        self._normal_fg = normal_fg
        self._hover_fg = hover_fg

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        self.config(bg=self._hover_bg)
        if self._hover_fg:
            self.config(fg=self._hover_fg)

    def _on_leave(self, _):
        self.config(bg=self._normal_bg)
        if self._normal_fg:
            self.config(fg=self._normal_fg)


class ModernMenuButton(tk.Menubutton):
    """Кнопка верхнего меню — плоская, с подсветкой при hover."""

    def __init__(self, master, text, palette, **kwargs):
        super().__init__(
            master, text=text,
            bg=palette["surface"], fg=palette["text_dim"],
            activebackground=palette["surface_alt"],
            activeforeground=palette["text"],
            bd=0, relief="flat", highlightthickness=0,
            padx=14, pady=6, cursor="hand2",
            font=("Segoe UI", 10),
            **kwargs,
        )
        self._palette = palette
        self.bind("<Enter>", lambda e: self.config(bg=palette["surface_alt"],
                                                   fg=palette["text"]))
        self.bind("<Leave>", lambda e: self.config(bg=palette["surface"],
                                                   fg=palette["text_dim"]))


def style_dropdown(menu: tk.Menu, palette):
    """Применяет современные цвета к выпадающему меню (там, где ОС позволяет)."""
    try:
        menu.configure(
            bg=palette["surface"],
            fg=palette["text"],
            activebackground=palette["accent"],
            activeforeground="#ffffff",
            bd=0, relief="flat",
            activeborderwidth=0,
            font=("Segoe UI", 10),
        )
    except tk.TclError:
        pass


class Slot(tk.Frame):
    """Слот под одно фото: карточка с рамкой и hover-эффектом."""

    def __init__(self, master, palette, index, on_click, on_right_click, on_double_click):
        super().__init__(
            master,
            width=160, height=160,
            bg=palette["slot_bg"],
            highlightthickness=2,
            highlightbackground=palette["slot_border"],
            highlightcolor=palette["slot_border"],
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.palette = palette
        self.index = index

        self.label = tk.Label(
            self,
            text=f"＋\n\nФото {index + 1}",
            bg=palette["slot_bg"], fg=palette["text_dim"],
            justify="center", font=("Segoe UI", 10),
            cursor="hand2",
        )
        self.label.pack(fill=tk.BOTH, expand=True)

        for w in (self, self.label):
            w.bind("<Button-1>", on_click)
            w.bind("<Button-3>", on_right_click)
            w.bind("<Double-Button-1>", on_double_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if self.cget("highlightbackground") != self.palette["accent"]:
            self.config(highlightbackground=self.palette["accent"])

    def _on_leave(self, _):
        self.update_border(selected=False)

    def update_border(self, selected=False):
        color = self.palette["accent"] if selected else self.palette["slot_border"]
        self.config(highlightbackground=color, highlightcolor=color)