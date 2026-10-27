"""Подписи: движок отрисовки, настройки и быстрые действия."""
import pytest
from PIL import Image, ImageChops

from photogrid import caption_render as cr
from photogrid.plugins import captions as cap

TEXT = "Закат у моря: длинная подпись, чтобы проверить перенос и обрезку строк"


def base(size=400):
    return Image.new("RGB", (size, size), (90, 140, 200))


def changed_rows(img, ref):
    diff = ImageChops.difference(img, ref).convert("L").point(lambda v: 255 if v else 0)
    bbox = diff.getbbox()
    return bbox


def test_settings_defaults_and_validation():
    s = cr.caption_settings({})
    assert s == {**cr.CAPTION_DEFAULTS, "caption_size_ratio": 0.045}
    bad = cr.caption_settings({"caption_style": "???", "caption_align": 5,
                               "caption_size_ratio": 9, "caption_max_lines": 99,
                               "caption_bg_opacity": -4})
    assert bad["caption_style"] == "bar" and bad["caption_align"] == "center"
    assert bad["caption_size_ratio"] == 0.12 and bad["caption_max_lines"] == 6
    assert bad["caption_bg_opacity"] == 0


def test_default_bar_is_at_bottom_full_width():
    out = cr.draw_caption(base(), "Вид на горы", {}, 400)
    x0, y0, x1, y1 = changed_rows(out, base())
    assert x0 == 0 and x1 == 400            # плашка по всей ширине
    assert y1 == 400 and y0 > 300           # прижата к низу


def test_position_top():
    out = cr.draw_caption(base(), "Вид", {"caption_position": "top"}, 400)
    x0, y0, x1, y1 = changed_rows(out, base())
    assert y0 == 0 and y1 < 100


@pytest.mark.parametrize("style", ["bar", "pill", "outline"])
def test_each_style_draws_and_keeps_size(style):
    out = cr.draw_caption(base(), TEXT, {"caption_style": style}, 400)
    assert out.size == (400, 400) and out.mode == "RGB"
    assert changed_rows(out, base()) is not None


def test_styles_differ():
    imgs = [cr.draw_caption(base(), "Вид на горы", {"caption_style": s}, 400)
            for s in ("bar", "pill", "outline")]
    assert not ImageChops.difference(imgs[0], imgs[1]).getbbox() is None
    assert not ImageChops.difference(imgs[1], imgs[2]).getbbox() is None


def test_pill_is_narrower_than_cell_and_centered():
    out = cr.draw_caption(base(), "Вид", {"caption_style": "pill"}, 400)
    x0, y0, x1, y1 = changed_rows(out, base())
    assert 0 < x0 and x1 < 400 and abs((x0 + x1) / 2 - 200) <= 3


def test_max_lines_limits_height():
    one = cr.draw_caption(base(), TEXT, {"caption_max_lines": 1}, 400)
    four = cr.draw_caption(base(), TEXT, {"caption_max_lines": 4}, 400)
    h1 = changed_rows(one, base())[3] - changed_rows(one, base())[1]
    h4 = changed_rows(four, base())[3] - changed_rows(four, base())[1]
    assert h4 - h1 > 15              # три лишние строки текста (плашка включает отступы)


def test_align_moves_text():
    def text_bbox(align):
        out = cr.draw_caption(base(), "Привет", {"caption_align": align,
                                                 "caption_bg_opacity": 0,
                                                 "caption_shadow": False}, 400)
        return changed_rows(out, base())
    left, center, right = text_bbox("left"), text_bbox("center"), text_bbox("right")
    assert left[0] < center[0] < right[0]


def test_explicit_newline_is_kept():
    f = cr.load_font(20)
    assert len(cr._wrap_text("раз\nдва", f, 1000)) == 2


def test_unknown_font_falls_back():
    f = cr.load_font(20, "Нет Такого Шрифта", bold=True, italic=True)
    assert f is not None
    out = cr.draw_caption(base(), "Тест", {"caption_font": "Нет Такого Шрифта"}, 400)
    assert changed_rows(out, base()) is not None


def test_available_fonts_nonempty_and_unique():
    fonts = cr.available_fonts()
    assert fonts and len(fonts) == len(set(fonts))


def test_empty_text_returns_image_untouched():
    img = base()
    assert cr.draw_caption(img, "   ", {}, 400) is img


# ----------------------------------------------------- быстрые действия
def test_from_filenames():
    photos = ["/x/IMG_01-sunset.jpg", None, "/x/до ремонта.png"]
    out = cap.captions_from_filenames(photos, ["", "keep", ""])
    assert out == ["IMG 01 sunset", "keep", "до ремонта"]


def test_numbered_template_and_missing_placeholder():
    photos = ["a", "b", None, "d"]
    assert cap.captions_numbered(photos, [""] * 4, "Шаг {n}") == ["Шаг 1", "Шаг 2", "", "Шаг 4"]
    assert cap.captions_numbered(photos, [""] * 4, "Фото")[0] == "Фото 1"
    # без фото вообще — нумеруем все слоты
    assert cap.captions_numbered([None] * 2, ["", ""], "{n}") == ["1", "2"]


def test_same_for_all_and_noop_when_empty():
    photos = ["a", "b", "c"]
    assert cap.captions_same_for_all(photos, ["", " Привет ", "x"]) == ["Привет"] * 3
    assert cap.captions_same_for_all(photos, ["", "", ""]) == ["", "", ""]
