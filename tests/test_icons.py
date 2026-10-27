"""Иконки: набор векторный, не зависит от системных шрифтов."""
import tkinter as tk

import pytest
from PIL import ImageChops

from photogrid import icons


def test_every_icon_renders_nonempty_at_ui_sizes():
    for kind in icons.ICONS:
        for size in (14, 18, 22, 30):
            m = icons.mask(kind, size)
            assert m.size == (size, size)
            assert m.getbbox() is not None, (kind, size)


def test_icons_stay_inside_their_box():
    # линии с округлыми краями не должны упираться в границу (обрезаться)
    for kind in icons.ICONS:
        x0, y0, x1, y1 = icons.mask(kind, 48).getbbox()
        assert x0 >= 0 and y0 >= 0 and x1 <= 48 and y1 <= 48, kind


def test_all_kinds_used_by_the_app_exist():
    used = {"collage", "plugins", "batch", "cloud", "save", "folder", "refresh",
            "download", "upload", "check", "plus", "delete", "shuffle", "clear",
            "theme", "theme_alt", "settings", "help", "bell", "info", "close",
            "menu", "layers", "image", "update", "sun", "caption", "copy"}
    assert used <= set(icons.ICONS)


def test_unknown_kind_falls_back_instead_of_crashing():
    assert icons.mask("no-such-icon", 20).getbbox() is not None


def test_color_applied():
    img = icons.pil_icon("check", 24, "#ff0000")
    px = [p for p in img.getdata() if p[3] > 200]
    assert px and all(p[:3] == (255, 0, 0) for p in px)


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("нет дисплея для Tk")
    yield r
    r.destroy()


def test_draw_keeps_references_and_quantizes_colors(root):
    c = tk.Canvas(root, width=60, height=60)
    for i in range(40):                       # «анимация» цвета
        c.delete("all")
        icons.draw(c, "refresh", 30, 30, 22, "#%02x%02x%02x" % (100 + i, 100, 100))
    assert len(c._icon_refs) <= 8
    assert len([k for k in icons._tk_cache if k[0] == "refresh"]) < 40


def test_segmented_control_follows_variable_and_cleans_up(root):
    from photogrid.ui_widgets import SegmentedControl
    var = tk.StringVar(value="fit")
    seg = SegmentedControl(root, {"surface_alt": "#222", "accent": "#77f",
                                  "text": "#eee", "text_dim": "#999",
                                  "surface_hi": "#333"},
                           [("fit", "A"), ("fill", "B")], variable=var)
    assert seg.get() == "fit"
    var.set("fill")                            # снаружи
    assert seg.get() == "fill"
    seg._choose("fit")                         # кликом
    assert var.get() == "fit"
    seg.destroy()
    var.set("fill")                            # после destroy не должно падать
    root.update()
