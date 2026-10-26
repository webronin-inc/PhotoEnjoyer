"""Тесты ядра редактора фото и движка анимаций (без tkinter)."""
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))

from PIL import Image, ImageChops

from photogrid import editor_core as ec
from photogrid import anim


def _halves(w=200, h=100):
    """Левая половина красная, правая синяя."""
    img = Image.new("RGB", (w, h), (0, 0, 255))
    img.paste((255, 0, 0), (0, 0, w // 2, h))
    return img


def _gradient(w=200, h=100):
    img = Image.new("RGB", (w, h))
    img.putdata([(int(255 * x / (w - 1)), 0, 0) for y in range(h) for x in range(w)])
    return img


# ------------------------------------------------------------------ геометрия
def test_default_render_is_identity():
    base = _halves()
    out = ec.render(base, ec.EditState())
    assert out.size == base.size
    assert ImageChops.difference(out, base).getbbox() is None


def test_rotate_and_flip():
    base = _halves(200, 100)
    st = ec.EditState()
    st.rotate90()
    assert ec.render(base, st).size == (100, 200)
    st.rotate90(3)                                   # вернулись
    assert ec.render(base, st).size == (200, 100)

    st.flip(horizontal=True)
    out = ec.render(base, st)
    assert out.getpixel((10, 50)) == (0, 0, 255)     # красное уехало вправо
    assert out.getpixel((190, 50)) == (255, 0, 0)


def test_rotate_clockwise_direction():
    base = _halves(200, 100)                         # красное слева
    st = ec.EditState()
    st.rotate90(1)                                   # по часовой: левое → верхнее
    out = ec.render(base, st)
    assert out.getpixel((50, 10)) == (255, 0, 0)
    assert out.getpixel((50, 190)) == (0, 0, 255)


def test_zoom_in_crops_center_and_keeps_size():
    base = _halves()
    st = ec.EditState()
    st.set("zoom", 2.0)
    out = ec.render(base, st)
    assert out.size == base.size
    # в центре кадра граница красного/синего: слева красный, справа синий
    assert out.getpixel((10, 50))[0] > 200
    assert out.getpixel((190, 50))[2] > 200


def test_zoom_out_pads_with_background():
    base = Image.new("RGB", (200, 100), (255, 0, 0))
    st = ec.EditState()
    st.set("zoom", 0.5)
    out = ec.render(base, st, bg="#00ff00")
    assert out.size == base.size
    assert out.getpixel((2, 2)) == (0, 255, 0)       # фон по углам
    assert out.getpixel((100, 50)) == (255, 0, 0)    # фото по центру


def test_zoom_is_clamped():
    st = ec.EditState()
    st.set("zoom", 99)
    assert st.v["zoom"] == ec.ZOOM_MAX
    st.set("zoom", 0.01)
    assert st.v["zoom"] == ec.ZOOM_MIN


def test_pan_moves_window():
    base = _gradient()
    st = ec.EditState()
    st.set("zoom", 2.0)
    centre = ec.render(base, st).getpixel((100, 50))[0]
    st.set("pan_x", 1.0)                             # окно уехало вправо → светлее
    right = ec.render(base, st).getpixel((100, 50))[0]
    st.set("pan_x", -1.0)
    left = ec.render(base, st).getpixel((100, 50))[0]
    assert left < centre < right


def test_pan_after_drag_photo_follows_cursor():
    """Фото должно ехать вместе с курсором, и на нужную величину."""
    base = _gradient(400, 200)
    for zoom in (2.0, 3.0, 0.6):
        st = ec.EditState()
        st.set("zoom", zoom)
        before = ec.render(base, st)
        dx = 0.10                                   # тянем на 10% ширины вправо
        st.v["pan_x"], st.v["pan_y"] = ec.pan_after_drag(st.v, dx, 0.0)
        after = ec.render(base, st)
        # ищем, на сколько пикселей сдвинулся контент: в точке x0 после сдвига
        # должен оказаться тот же цвет, что был в x0 - 40 до сдвига
        shift = int(dx * 400)
        x0 = 200
        a = after.getpixel((x0, 100))[0]
        b = before.getpixel((x0 - shift, 100))[0]
        assert abs(a - b) <= 6, (zoom, a, b)


def test_pan_after_drag_noop_at_zoom_one_and_clamped():
    st = ec.EditState()
    assert ec.pan_after_drag(st.v, 0.5, 0.5) == (0.0, 0.0)
    st.set("zoom", 1.2)
    px, py = ec.pan_after_drag(st.v, -5.0, 5.0)
    assert -1.0 <= px <= 1.0 and -1.0 <= py <= 1.0


def test_angle_hides_empty_corners():
    base = Image.new("RGB", (200, 100), (255, 0, 0))
    st = ec.EditState()
    st.set("angle", 20)
    out = ec.render(base, st, bg="#00ff00")
    for xy in ((0, 0), (199, 0), (0, 99), (199, 99)):
        assert out.getpixel(xy) == (255, 0, 0), xy   # зелёного фона нет


# ----------------------------------------------------------------------- цвет
def _mean(img):
    px = list(img.convert("L").getdata())
    return sum(px) / len(px)


def test_brightness_contrast_saturation():
    base = _gradient()                               # не насыщенные primaries: яркость видна
    st = ec.EditState()
    st.set("brightness", 50)
    assert _mean(ec.render(base, st)) > _mean(base)
    st.set("brightness", -50)
    assert _mean(ec.render(base, st)) < _mean(base)
    base = _halves()

    st = ec.EditState()
    st.set("saturation", -100)
    out = ec.render(base, st)
    r, g, b = out.getpixel((10, 10))
    assert r == g == b


def test_warmth_shifts_channels():
    base = Image.new("RGB", (20, 20), (128, 128, 128))
    st = ec.EditState()
    st.set("warmth", 100)
    r, g, b = ec.render(base, st).getpixel((5, 5))
    assert r > 128 > b
    st.set("warmth", -100)
    r, g, b = ec.render(base, st).getpixel((5, 5))
    assert b > 128 > r


def test_all_filters_work_and_keep_size():
    base = _gradient()
    for name in ec.FILTERS:
        st = ec.EditState()
        st.set("filter", name)
        out = ec.render(base, st)
        assert out.size == base.size and out.mode == "RGB", name
    st = ec.EditState()
    st.set("filter", "gray")
    r, g, b = ec.render(_halves(), st).getpixel((10, 10))
    assert r == g == b
    st.set("filter", "negative")
    assert ec.render(Image.new("RGB", (4, 4), (10, 20, 30)), st).getpixel((1, 1)) == (245, 235, 225)


def test_vignette_darkens_corners_more_than_centre():
    base = Image.new("RGB", (200, 200), (200, 200, 200))
    st = ec.EditState()
    st.set("vignette", 100)
    out = ec.render(base, st)
    assert out.getpixel((0, 0))[0] < out.getpixel((100, 100))[0] - 80
    assert out.getpixel((100, 100))[0] > 190


def test_blur_smooths_edge():
    base = _halves()
    st = ec.EditState()
    st.set("blur", 5)
    out = ec.render(base, st)
    mid = out.getpixel((100, 50))
    assert 0 < mid[0] < 255 and 0 < mid[2] < 255


# ------------------------------------------------------------ рисование/области
def test_brush_draws_and_eraser_removes():
    base = Image.new("RGB", (200, 200), (255, 255, 255))
    st = ec.EditState()
    st.add_op({"t": "brush", "pts": [(0.2, 0.5), (0.8, 0.5)], "color": "#ff0000",
               "size": 0.05, "alpha": 1.0})
    out = ec.render(base, st)
    assert out.getpixel((100, 100)) == (255, 0, 0)
    assert out.getpixel((100, 20)) == (255, 255, 255)

    st.add_op({"t": "eraser", "pts": [(0.5, 0.5)], "size": 0.2})
    assert ec.render(base, st).getpixel((100, 100)) == (255, 255, 255)
    assert ec.render(base, st).getpixel((50, 100)) == (255, 0, 0)   # вне ластика


def test_paint_is_resolution_independent():
    st = ec.EditState()
    st.add_op({"t": "rect", "p0": (0.25, 0.25), "p1": (0.75, 0.75),
               "color": "#0000ff", "size": 0.02, "alpha": 1.0, "fill": True})
    small = ec.render(Image.new("RGB", (100, 100), "white"), st)
    big = ec.render(Image.new("RGB", (400, 400), "white"), st)
    assert small.getpixel((50, 50)) == big.getpixel((200, 200)) == (0, 0, 255)
    assert small.getpixel((10, 10)) == big.getpixel((40, 40)) == (255, 255, 255)


def test_alpha_blends():
    base = Image.new("RGB", (100, 100), (255, 255, 255))
    st = ec.EditState()
    st.add_op({"t": "rect", "p0": (0, 0), "p1": (1, 1), "color": "#000000",
               "size": 0.01, "alpha": 0.5, "fill": True})
    v = ec.render(base, st).getpixel((50, 50))[0]
    assert 120 <= v <= 135


def test_shapes_line_arrow_ellipse():
    base = Image.new("RGB", (200, 200), "white")
    for t in ("line", "arrow", "ellipse", "rect"):
        st = ec.EditState()
        st.add_op({"t": t, "p0": (0.1, 0.1), "p1": (0.9, 0.9), "color": "#00aa00",
                   "size": 0.03, "alpha": 1.0})
        out = ec.render(base, st)
        assert ImageChops.difference(out, base).getbbox() is not None, t


def test_text_with_cyrillic():
    base = Image.new("RGB", (300, 200), (0, 0, 0))
    st = ec.EditState()
    st.add_op({"t": "text", "pos": (0.1, 0.1), "text": "Привет\nмир",
               "color": "#ffffff", "size": 0.1, "alpha": 1.0})
    out = ec.render(base, st)
    assert ImageChops.difference(out, base).getbbox() is not None
    # за пределами кадра — без исключений
    st.add_op({"t": "text", "pos": (-0.5, 1.2), "text": "x", "color": "#fff", "size": 0.1})
    ec.render(base, st)


def test_mosaic_changes_only_selected_area():
    base = _gradient(200, 200)
    st = ec.EditState()
    st.add_op({"t": "mosaic", "rect": (0.25, 0.25, 0.75, 0.75)})
    out = ec.render(base, st)
    diff = ImageChops.difference(out, base)
    bbox = diff.getbbox()
    assert bbox is not None
    assert bbox[0] >= 49 and bbox[2] <= 151        # только внутри области
    # область реально «поквадратилась»: соседние пиксели в блоке одинаковые
    assert out.getpixel((60, 100)) == out.getpixel((61, 100))


def test_blur_area():
    base = _halves(200, 200)
    st = ec.EditState()
    st.add_op({"t": "blur", "rect": (0.4, 0.0, 0.6, 1.0)})
    out = ec.render(base, st)
    mid = out.getpixel((100, 100))
    assert 0 < mid[0] < 255
    assert out.getpixel((10, 100)) == (255, 0, 0)


def test_ops_undo_redo_clear():
    st = ec.EditState()
    for i in range(3):
        st.add_op({"t": "brush", "pts": [(0.1 * i, 0.1)], "color": "#000", "size": 0.01})
    assert len(st.ops) == 3
    assert st.undo_op() and len(st.ops) == 2 and st.can_redo
    assert st.redo_op() and len(st.ops) == 3
    st.clear_ops()
    assert not st.ops
    assert st.redo_op() and len(st.ops) == 1          # очистку тоже можно вернуть
    st.add_op({"t": "brush", "pts": [(0, 0)], "color": "#000", "size": 0.01})
    assert not st.can_redo                            # новая операция сбрасывает redo


def test_reset_helpers_and_defaults():
    st = ec.EditState()
    assert st.is_default
    st.set("brightness", 30)
    st.set("zoom", 2)
    st.rotate90()
    st.add_op({"t": "mosaic", "rect": (0, 0, 1, 1)})
    assert not st.is_default
    st.reset_color()
    assert st.v["brightness"] == 0
    st.reset_frame()
    assert st.v["zoom"] == 1.0 and st.v["rot90"] == 0
    st.reset_all()
    assert st.is_default


def test_auto_enhance_and_preview_base():
    st = ec.EditState()
    ec.auto_enhance(st)
    assert st.v["contrast"] > 0 and st.v["saturation"] > 0
    big = Image.new("RGB", (3000, 2000))
    prev = ec.make_preview_base(big, 1000)
    assert max(prev.size) == 1000 and big.size == (3000, 2000)


def test_full_pipeline_is_fast_enough():
    base = Image.new("RGB", (1000, 1000), (120, 140, 160))
    st = ec.EditState()
    st.set("zoom", 1.7); st.set("angle", 8); st.set("brightness", 10)
    st.set("contrast", 20); st.set("saturation", 15); st.set("sharpness", 30)
    st.set("warmth", 20); st.set("blur", 1); st.set("vignette", 40)
    st.set("filter", "vintage")
    for i in range(20):
        st.add_op({"t": "brush", "pts": [(0.05 * i, 0.2), (0.05 * i + 0.1, 0.8)],
                   "color": "#ff0000", "size": 0.01, "alpha": 0.8})
    t0 = time.time()
    ec.render(base, st)
    assert time.time() - t0 < 3.0                     # для «реального времени» с запасом


# ------------------------------------------------------------- движок анимаций
class _FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.n = 0

    def after(self, ms, fn):
        self.n += 1
        self.jobs[self.n] = fn
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run_frame(self):
        jobs, self.jobs = self.jobs, {}
        for fn in jobs.values():
            fn()


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _animator():
    root, clock = _FakeRoot(), _Clock()
    return anim.Animator(root, clock=clock), root, clock


def test_tween_runs_and_finishes():
    an, root, clock = _animator()
    seen, done = [], []
    an.animate(100, seen.append, on_done=lambda: done.append(1), easing=anim.linear)
    for _ in range(20):
        clock.t += 0.02
        root.run_frame()
    assert seen[0] < 1.0 and seen[-1] == 1.0 and seen == sorted(seen)
    assert done == [1]
    assert not an.active and not root.jobs             # в простое таймера нет


def test_same_key_cancels_previous():
    an, root, clock = _animator()
    a, b = [], []
    an.animate(100, a.append, key="k", easing=anim.linear)
    clock.t += 0.03
    root.run_frame()
    an.animate(100, b.append, key="k", easing=anim.linear)
    for _ in range(10):
        clock.t += 0.02
        root.run_frame()
    assert a and a[-1] < 1.0                           # первая оборвана
    assert b[-1] == 1.0


def test_disabled_jumps_to_end():
    an, root, clock = _animator()
    an.set_enabled(False)
    seen, done = [], []
    an.animate(500, seen.append, on_done=lambda: done.append(1))
    assert seen == [1.0] and done == [1] and not root.jobs


def test_disable_midway_finishes_running_tweens():
    an, root, clock = _animator()
    seen = []
    an.animate(1000, seen.append, easing=anim.linear)
    clock.t += 0.1
    root.run_frame()
    an.set_enabled(False)
    assert seen[-1] == 1.0 and not an.active


def test_dead_widget_tween_is_dropped():
    class TclError(Exception):
        pass

    an, root, clock = _animator()

    def boom(p):
        raise TclError("widget destroyed")

    an.animate(100, boom, easing=anim.linear)
    clock.t += 0.02
    root.run_frame()
    assert not an.active                               # без падения и без утечки


def test_delay_and_easing_bounds():
    an, root, clock = _animator()
    seen = []
    an.animate(100, seen.append, delay_ms=200, easing=anim.linear)
    clock.t += 0.1
    root.run_frame()
    assert seen == []                                  # ещё не началась
    clock.t += 0.3
    root.run_frame()
    assert seen[-1] == 1.0
    for f in (anim.linear, anim.ease_out_cubic, anim.ease_in_out_cubic,
              anim.ease_out_quad, anim.ease_out_expo, anim.ease_out_back):
        assert abs(f(0.0)) < 1e-6 and abs(f(1.0) - 1.0) < 1e-6, f.__name__
    assert anim.ease_out_back(0.8) > 1.0               # «перелёт»


def test_tween_attr():
    class W:
        v = 0.0

        def __init__(self):
            self.redraws = 0
            self._r = _FakeRoot()

        def _root(self):
            return self._r

        def _redraw(self):
            self.redraws += 1

    w = W()
    anim.set_enabled(False)
    try:
        anim.tween_attr(w, "v", 1.0)
        assert w.v == 1.0 and w.redraws == 1
    finally:
        anim.set_enabled(True)
