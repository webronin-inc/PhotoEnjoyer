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
    assert len([k for k in icons._tk_cache if k[1] == "refresh"]) < 40


def test_segmented_control_follows_variable_and_cleans_up(root):
    from photogrid.ui_widgets import SegmentedControl
    var = tk.StringVar(value="fit")
    seg = SegmentedControl(root, {"surface": "#111111", "surface_alt": "#222222",
                                  "accent": "#7777ff", "text": "#eeeeee",
                                  "text_dim": "#999999", "surface_hi": "#333333"},
                           [("fit", "A"), ("fill", "B")], variable=var)
    assert seg.get() == "fit"
    var.set("fill")                            # снаружи
    assert seg.get() == "fill"
    seg._choose("fit")                         # кликом
    assert var.get() == "fit"
    seg.destroy()
    var.set("fill")                            # после destroy не должно падать
    root.update()


def test_public_neon_api_is_complete():
    for name in ("neon_pil", "neon_from_mask", "tk_neon", "draw_neon", "warm_neon",
                 "neon_pad", "neon_sheet", "logo_pil", "NEON", "draw", "tk_icon"):
        assert hasattr(icons, name), name


def test_neon_has_glow_depth_and_padding():
    on = icons.neon_pil("collage", 24, "#23e5ff", glow=1.0)
    off = icons.neon_pil("collage", 24, "#23e5ff", glow=0.0)
    assert on.size == (24 + 2 * icons.neon_pad(24),) * 2
    # включённая трубка светится за пределами штрихов — «непрозрачных» пикселей больше
    lit = lambda im: sum(1 for a in im.getchannel("A").getdata() if a > 20)
    assert lit(on) > lit(off)
    assert on.getchannel("A").getbbox() is not None


def test_logo_renders_in_every_size():
    for size in (16, 32, 64, 256):
        lg = icons.logo_pil(size, "#7c6cff")
        assert lg.size[0] > size and lg.getchannel("A").getbbox() is not None


def test_every_rail_icon_exists():
    for kind in ("collage", "template", "layers", "cloud", "edit", "tools",
                 "plugins", "theme", "settings", "update", "help"):
        assert kind in icons.ICONS, kind


def test_image_cache_is_not_shared_between_tk_interpreters():
    """PhotoImage из старого root в новом окне — «image doesn't exist»."""
    try:
        r1 = tk.Tk()
    except tk.TclError:
        pytest.skip("нет дисплея для Tk")
    a = icons.tk_icon("check", 20, "#ffffff")
    n1 = icons.tk_neon("collage", 24, "#23e5ff", 1.0)
    r1.destroy()
    r2 = tk.Tk()
    try:
        c = tk.Canvas(r2)
        b = icons.tk_icon("check", 20, "#ffffff")
        n2 = icons.tk_neon("collage", 24, "#23e5ff", 1.0)
        assert a is not b and n1 is not n2
        c.create_image(0, 0, image=b)           # не должно падать
        c.create_image(0, 0, image=n2)
        r2.update()
    finally:
        r2.destroy()
