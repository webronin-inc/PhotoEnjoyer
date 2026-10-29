"""Всплывающее меню: пункты, клавиатура, закрытие, отключённые пункты."""
import tkinter as tk

import pytest

from photogrid import popup

P = {"surface": "#18181f", "surface_hi": "#262633", "border": "#333344",
     "border_soft": "#2a2a38", "text": "#eeeeee", "text_dim": "#aaaaaa",
     "text_faint": "#777777", "danger": "#ff5470"}


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("нет дисплея для Tk")
    yield r
    popup.close_current()
    r.destroy()


def pump(root, n=15):
    for _ in range(n):
        root.update()
        root.after(10)


def test_click_runs_command_and_closes(root):
    hits = []
    m = popup.show(root, P, [{"title": "Группа"},
                             {"label": "Раз", "command": lambda: hits.append(1),
                              "icon": "copy", "shortcut": "Ctrl+1"}, "-",
                             {"label": "Два", "command": lambda: hits.append(2)}],
                   50, 50)
    pump(root)
    m._activate(0)
    pump(root)
    assert hits == [1] and m._closed
    assert not m.top.winfo_exists()


def test_disabled_item_does_not_fire(root):
    hits = []
    m = popup.show(root, P, [{"label": "Нельзя", "enabled": False,
                              "command": lambda: hits.append(1)}], 10, 10)
    pump(root)
    m._activate(0)
    pump(root)
    assert hits == [] and not m._closed
    m.close()


def test_keyboard_navigation_skips_disabled(root):
    hits = []
    m = popup.show(root, P, [{"label": "A", "command": lambda: hits.append("A")},
                             {"label": "B", "enabled": False},
                             {"label": "C", "command": lambda: hits.append("C")}],
                   10, 10)
    pump(root)
    m._move(1); m._move(1)            # A → C (B пропущен)
    m._activate(m._index)
    pump(root)
    assert hits == ["C"]


def test_second_menu_closes_first_and_escape_closes(root):
    a = popup.show(root, P, [{"label": "A"}], 10, 10)
    b = popup.show(root, P, [{"label": "B"}], 20, 20)
    pump(root)
    assert a._closed and not b._closed
    b.top.event_generate("<Escape>")
    pump(root)
    assert b._closed


def test_stays_on_screen(root):
    m = popup.show(root, P, [{"label": "Очень длинный пункт меню"}] * 3,
                   root.winfo_screenwidth() + 500, root.winfo_screenheight() + 500)
    pump(root)
    w, h, x, y = m._geom
    assert x + w <= root.winfo_screenwidth() and y + h <= root.winfo_screenheight()
    m.close()
