"""Регрессия: виджеты редактора не должны затирать внутренние атрибуты Tk.

В 0.0.0.13–0.0.0.18 _TabBar писал число в self._w (внутреннее имя виджета в
tkinter), из-за чего редактор фото не открывался: invalid command name "330".
"""
import tkinter as tk

import pytest


class _Palette(dict):
    def __missing__(self, key):
        return "#202020"


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("нет дисплея для Tk")
    yield r
    r.destroy()


def test_tabbar_keeps_tk_path_name(root):
    from photogrid.plugins.photo_editor import _TabBar
    bar = _TabBar(root, _Palette(), [("a", "A"), ("b", "B")], lambda k: None)
    bar.pack()
    root.update()
    assert isinstance(bar._w, str) and bar._w.startswith(".")
    bar.select("b", animate=False)
    root.update()
    assert bar.find_all()          # холст реально перерисован


def test_slider_releases_wheel_binding_on_destroy(root):
    from photogrid import ui_widgets as uw
    sl = uw.GradientSlider(root, _Palette(), 0, 100, 50)
    sl.pack()
    root.update()
    sl.event_generate("<Enter>")           # слайдер забрал колесо (bind_all)
    root.update()
    assert uw._wheel_owner.get("<MouseWheel>") is sl
    sl.destroy()                           # <Leave> не придёт
    root.update()
    assert "<MouseWheel>" not in uw._wheel_owner
    errors = []
    root.report_callback_exception = lambda *a: errors.append(a)
    root.event_generate("<MouseWheel>", delta=120)
    root.update()
    assert not errors
