"""Тесты сессии редактора (логика без Tk)."""
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))

from PIL import Image, ImageChops

from photogrid import editor_core as ec
from photogrid.editor_session import EditorSession


def _img(w=400, h=300, color=(200, 200, 200)):
    return Image.new("RGB", (w, h), color)


def test_undo_redo_covers_sliders_and_drawing():
    s = EditorSession(_img())
    s.checkpoint()
    s.set_value("brightness", 40)
    s.pointer_down("brush", 0.1, 0.1, {"size": 10})
    s.pointer_move(0.5, 0.5)
    assert s.pointer_up()
    assert len(s.state.ops) == 1 and s.state.v["brightness"] == 40

    assert s.undo()                                   # убрали мазок
    assert not s.state.ops and s.state.v["brightness"] == 40
    assert s.undo()                                   # убрали яркость
    assert s.state.v["brightness"] == 0
    assert not s.undo()                               # дальше некуда
    assert s.redo() and s.state.v["brightness"] == 40
    assert s.redo() and len(s.state.ops) == 1
    assert not s.redo()


def test_new_change_drops_redo():
    s = EditorSession(_img())
    s.checkpoint(); s.set_value("contrast", 10)
    s.undo()
    assert s.can_redo
    s.checkpoint(); s.set_value("contrast", 20)
    assert not s.can_redo


def test_checkpoint_dedupes_identical_states():
    s = EditorSession(_img())
    assert s.checkpoint()
    assert not s.checkpoint()


def test_brush_stroke_live_and_commit():
    s = EditorSession(_img(200, 200, (255, 255, 255)))
    s.pointer_down("brush", 0.2, 0.5, {"size": 20, "color": "#ff0000", "alpha": 1})
    s.pointer_move(0.8, 0.5)
    live = s.render_view()                      # мазок виден ещё до отпускания
    assert live.getpixel((100, 100)) == (255, 0, 0)
    assert not s.state.ops                      # но в историю не попал
    s.pointer_up()
    assert len(s.state.ops) == 1
    assert s.render_view().getpixel((100, 100)) == (255, 0, 0)


def test_shapes_and_tiny_click_ignored():
    for tool in ("line", "arrow", "rect", "ellipse"):
        s = EditorSession(_img(200, 200, (255, 255, 255)))
        s.pointer_down(tool, 0.2, 0.2, {"size": 8, "color": "#0000ff"})
        s.pointer_move(0.8, 0.8)
        assert s.pointer_up(), tool
        assert ImageChops.difference(s.render_view(), s.base).getbbox(), tool

    s = EditorSession(_img())
    s.pointer_down("rect", 0.5, 0.5)
    assert not s.pointer_up(0.5, 0.5)            # случайный клик не создаёт фигуру
    assert not s.state.ops


def test_area_tools_need_real_rectangle():
    s = EditorSession(_img(200, 200))
    s.pointer_down("mosaic", 0.2, 0.2)
    s.pointer_move(0.6, 0.7)
    assert s.area_rect() == (0.2, 0.2, 0.6, 0.7)
    assert s.pointer_up()
    assert s.state.ops[0]["t"] == "mosaic"
    s.pointer_down("blur", 0.3, 0.3)
    assert not s.pointer_up(0.3, 0.3)
    assert len(s.state.ops) == 1


def test_area_op_invalidates_stage_cache_but_brush_does_not(monkeypatch):
    calls = []
    real = ec.render_base

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(ec, "render_base", counting)

    s = EditorSession(_img())
    s.render_view(); s.render_view()
    assert len(calls) == 1                       # кэш работает

    s.pointer_down("brush", 0.1, 0.1); s.pointer_move(0.5, 0.5); s.pointer_up()
    s.render_view()
    assert len(calls) == 1                       # рисование не пересчитывает стадию

    s.set_value("brightness", 10)
    s.render_view()
    assert len(calls) == 2                       # слайдер — пересчитывает

    s.pointer_down("mosaic", 0.1, 0.1); s.pointer_up(0.6, 0.6)
    s.render_view()
    assert len(calls) == 3                       # область — тоже


def test_pan_gesture_moves_frame_and_is_undoable():
    s = EditorSession(_img())
    s.state.set("zoom", 2.0)
    s.pointer_down("pan", 0.5, 0.5)
    s.pointer_move(0.4, 0.5)
    s.pointer_up()
    assert s.state.v["pan_x"] > 0                # потянули влево → окно вправо
    s.undo()
    assert s.state.v["pan_x"] == 0.0


def test_text_and_eraser():
    s = EditorSession(_img(300, 200, (0, 0, 0)))
    assert not s.add_text(0.1, 0.1, "   ")
    assert s.add_text(0.1, 0.1, "Привет", {"color": "#ffffff", "size": 20})
    assert ImageChops.difference(s.render_view(), s.base).getbbox()

    s2 = EditorSession(_img(200, 200, (255, 255, 255)))
    s2.pointer_down("brush", 0.1, 0.5, {"size": 30, "color": "#ff0000"})
    s2.pointer_up(0.9, 0.5)
    s2.pointer_down("eraser", 0.5, 0.5, {"size": 30})
    s2.pointer_up(0.5, 0.5)
    assert s2.render_view().getpixel((100, 100)) == (255, 255, 255)


def test_compare_shows_original():
    s = EditorSession(_img())
    s.set_value("brightness", -60)
    assert s.render_view(compare=True).getpixel((5, 5)) == (200, 200, 200)
    assert s.render_view().getpixel((5, 5)) != (200, 200, 200)


def test_render_full_matches_preview_and_is_full_size():
    big = Image.new("RGB", (2400, 1600), (120, 90, 60))
    s = EditorSession(big, preview_side=800)
    assert max(s.base.size) == 800
    s.set_value("zoom", 1.5)
    s.set_value("saturation", 30)
    s.pointer_down("rect", 0.2, 0.2, {"size": 10, "fill": True, "color": "#00ff00"})
    s.pointer_up(0.6, 0.6)
    full = s.render_full()
    assert full.size == (2400, 1600)
    prev = s.render_view()
    from PIL import ImageFilter, ImageStat
    small = full.resize(prev.size)
    diff = ImageChops.difference(small, prev).convert("L")
    assert ImageStat.Stat(diff).mean[0] < 1.0    # те же цвета/то же место
    soft = ImageChops.difference(small.filter(ImageFilter.GaussianBlur(2)),
                                 prev.filter(ImageFilter.GaussianBlur(2)))
    assert soft.convert("L").getextrema()[1] < 40   # различия только по краям
    assert full.getpixel((int(0.4 * 2400), int(0.4 * 1600))) == (0, 255, 0)


def test_render_full_does_not_touch_live_state():
    s = EditorSession(_img(300, 200))
    s.set_value("brightness", 20)
    before = dict(s.state.v)
    s.render_full()
    assert s.state.v == before


def test_filter_previews_and_set_filter():
    s = EditorSession(_img(400, 300))
    prev = s.filter_previews(60)
    assert set(prev) == set(ec.FILTERS)
    assert all(max(im.size) <= 60 for im in prev.values())
    s.set_filter("nonsense")
    assert s.state.v["filter"] == "none"
    s.set_filter("sepia")
    assert s.state.v["filter"] == "sepia"
    s.undo()
    assert s.state.v["filter"] == "none"


def test_reset_and_clear():
    s = EditorSession(_img())
    s.set_value("blur", 3)
    s.state.add_op({"t": "mosaic", "rect": (0, 0, 1, 1)})
    assert s.changed
    s.reset_all()
    assert not s.changed
    s.undo()
    assert s.changed                              # сброс тоже отменяется
    assert s.clear_drawing() and not s.state.ops
