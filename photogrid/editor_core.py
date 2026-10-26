"""Ядро редактора фото: чистый Pillow, без UI (поэтому легко тестируется).

Конвейер (render):
    отражение/поворот → кадр (угол, приближение, сдвиг) → цвет → фильтр →
    эффекты (размытие, виньетка) → «мозаика/размытие области» → рисунок.

Рисунок и области хранятся как операции в НОРМАЛИЗОВАННЫХ координатах
итогового кадра (0..1), а толщины — долей длинной стороны. Поэтому одно и то
же редактирование одинаково выглядит и на уменьшенном превью, и на оригинале.
"""
import math

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .core import _hex_to_rgb, _load_font

# ------------------------------------------------------------------ константы
ZOOM_MIN, ZOOM_MAX = 0.5, 4.0

FILTERS = {
    "none":     "Оригинал",
    "gray":     "Ч/Б",
    "sepia":    "Сепия",
    "vintage":  "Винтаж",
    "warm":     "Тёплый",
    "cool":     "Холодный",
    "fade":     "Выцветший",
    "poster":   "Постер",
    "sketch":   "Набросок",
    "negative": "Негатив",
}

# Параметры, которыми управляют ползунки: ключ → (мин, макс, по умолчанию)
RANGES = {
    "zoom":       (ZOOM_MIN, ZOOM_MAX, 1.0),
    "angle":      (-45.0, 45.0, 0.0),
    "brightness": (-100.0, 100.0, 0.0),
    "contrast":   (-100.0, 100.0, 0.0),
    "saturation": (-100.0, 100.0, 0.0),
    "sharpness":  (-100.0, 100.0, 0.0),
    "warmth":     (-100.0, 100.0, 0.0),
    "blur":       (0.0, 10.0, 0.0),
    "vignette":   (0.0, 100.0, 0.0),
}

FRAME_KEYS = ("zoom", "pan_x", "pan_y", "angle", "rot90", "flip_h", "flip_v")
COLOR_KEYS = ("brightness", "contrast", "saturation", "sharpness", "warmth",
              "blur", "vignette")

PAINT_TOOLS = ("brush", "eraser", "line", "arrow", "rect", "ellipse", "text")
AREA_TOOLS = ("mosaic", "blur")


def _defaults():
    d = {k: v[2] for k, v in RANGES.items()}
    d.update(pan_x=0.0, pan_y=0.0, rot90=0, flip_h=False, flip_v=False,
             filter="none")
    return d


class EditState:
    """Все параметры редактирования + список операций рисования."""

    def __init__(self):
        self.v = _defaults()
        self.ops = []        # операции рисования/областей
        self._redo = []

    # ---- значения ----
    def set(self, key, value):
        if key in RANGES:
            lo, hi, _ = RANGES[key]
            value = max(lo, min(hi, float(value)))
        elif key in ("pan_x", "pan_y"):
            value = max(-1.0, min(1.0, float(value)))
        self.v[key] = value

    def reset_frame(self):
        d = _defaults()
        for k in FRAME_KEYS:
            self.v[k] = d[k]

    def reset_color(self):
        d = _defaults()
        for k in COLOR_KEYS:
            self.v[k] = d[k]
        self.v["filter"] = "none"

    def reset_all(self):
        self.v = _defaults()
        self.ops.clear()
        self._redo.clear()

    @property
    def is_default(self):
        return self.v == _defaults() and not self.ops

    # ---- геометрия ----
    def rotate90(self, steps=1):
        self.v["rot90"] = (self.v["rot90"] + steps) % 4

    def flip(self, horizontal=True):
        key = "flip_h" if horizontal else "flip_v"
        self.v[key] = not self.v[key]

    def zoom_by(self, factor):
        self.set("zoom", self.v["zoom"] * factor)
        self.clamp_pan()

    def clamp_pan(self):
        self.v["pan_x"] = max(-1.0, min(1.0, self.v["pan_x"]))
        self.v["pan_y"] = max(-1.0, min(1.0, self.v["pan_y"]))

    # ---- операции ----
    def add_op(self, op):
        self.ops.append(op)
        self._redo.clear()

    def undo_op(self):
        if self.ops:
            self._redo.append(self.ops.pop())
            return True
        return False

    def redo_op(self):
        if self._redo:
            self.ops.append(self._redo.pop())
            return True
        return False

    def clear_ops(self):
        if self.ops:
            self._redo.extend(reversed(self.ops))
            self.ops.clear()

    @property
    def can_redo(self):
        return bool(self._redo)


# -------------------------------------------------------------------- вспомог.
def _lut_scale(factor):
    return [max(0, min(255, int(i * factor + 0.5))) for i in range(256)]


def _scale_channels(img, r=1.0, g=1.0, b=1.0):
    rr, gg, bb = img.split()
    return Image.merge("RGB", (rr.point(_lut_scale(r)),
                               gg.point(_lut_scale(g)),
                               bb.point(_lut_scale(b))))


def _rgb(color):
    try:
        return _hex_to_rgb(color)
    except Exception:
        return (255, 255, 255)


def _cover_scale(w, h, angle_deg):
    """Во сколько раз увеличить повёрнутый кадр, чтобы не было пустых углов."""
    a = math.radians(abs(angle_deg))
    ratio = max(w / h, h / w)
    return math.cos(a) + math.sin(a) * ratio


# --------------------------------------------------------------------- кадр
def apply_frame(img, v, bg="#ffffff"):
    """Угол, приближение/отдаление и сдвиг. Размер результата = размеру входа."""
    w, h = img.size
    angle = float(v.get("angle", 0.0))
    zoom = float(v.get("zoom", 1.0))
    px, py = float(v.get("pan_x", 0.0)), float(v.get("pan_y", 0.0))

    if abs(angle) > 0.01:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False,
                         fillcolor=_rgb(bg))
        zoom *= _cover_scale(w, h, angle)      # скрываем пустые углы

    if abs(zoom - 1.0) < 1e-3 and abs(px) < 1e-6 and abs(py) < 1e-6:
        return img

    if zoom >= 1.0:
        cw, ch = w / zoom, h / zoom
        cx = w / 2 + px * (w - cw) / 2
        cy = h / 2 + py * (h - ch) / 2
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        return img.resize((w, h), Image.BICUBIC, box=box)

    # «дальше»: уменьшаем фото и кладём на фон
    nw, nh = max(1, int(round(w * zoom))), max(1, int(round(h * zoom)))
    small = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), _rgb(bg))
    x = int(round((w - nw) / 2 + px * (w - nw) / 2))
    y = int(round((h - nh) / 2 + py * (h - nh) / 2))
    canvas.paste(small, (x, y))
    return canvas


def pan_after_drag(v, dx_norm, dy_norm, size=None):
    """Новые (pan_x, pan_y) после перетаскивания кадра мышью.

    dx_norm/dy_norm — смещение курсора в долях ширины/высоты показанного кадра
    (вправо/вниз — положительные). Фото «едет» за курсором.

    Приближение (z>1): центр кропа cx = W/2 + pan·(W − W/z)/2, а на экране
    виден кроп шириной W/z, поэтому Δpan = −2·Δ/(z − 1).
    Отдаление (z<1): смещение мини-фото = pan·(W − zW)/2, поэтому
    Δpan = 2·Δ/(1 − z).
    """
    zoom = float(v.get("zoom", 1.0))
    if abs(float(v.get("angle", 0.0))) > 0.01 and size:
        zoom *= _cover_scale(size[0], size[1], v["angle"])
    px, py = float(v.get("pan_x", 0.0)), float(v.get("pan_y", 0.0))

    if zoom > 1.0 + 1e-6:
        k = 2.0 / (zoom - 1.0)
        px -= dx_norm * k
        py -= dy_norm * k
    elif zoom < 1.0 - 1e-6:
        k = 2.0 / (1.0 - zoom)
        px += dx_norm * k
        py += dy_norm * k
    return max(-1.0, min(1.0, px)), max(-1.0, min(1.0, py))


# --------------------------------------------------------------------- цвет
def apply_color(img, v):
    b = v.get("brightness", 0.0)
    if b:
        img = ImageEnhance.Brightness(img).enhance(1 + b / 100.0)
    c = v.get("contrast", 0.0)
    if c:
        img = ImageEnhance.Contrast(img).enhance(1 + c / 100.0)
    s = v.get("saturation", 0.0)
    if s:
        img = ImageEnhance.Color(img).enhance(1 + s / 100.0)
    sh = v.get("sharpness", 0.0)
    if sh:
        factor = 1 + sh / 50.0 if sh > 0 else 1 + sh / 100.0
        img = ImageEnhance.Sharpness(img).enhance(factor)
    w = v.get("warmth", 0.0)
    if w:
        k = w / 100.0
        img = _scale_channels(img, r=1 + 0.22 * k, g=1 + 0.02 * k, b=1 - 0.22 * k)
    return img


# ------------------------------------------------------------------ фильтры
def _sepia(img):
    gray = ImageOps.grayscale(img)
    return ImageOps.colorize(gray, black="#2a1b0c", white="#fff0d4",
                             mid="#a98660")


def apply_filter(img, name):
    if name in (None, "none"):
        return img
    if name == "gray":
        return ImageOps.grayscale(img).convert("RGB")
    if name == "sepia":
        return _sepia(img)
    if name == "negative":
        return ImageOps.invert(img)
    if name == "vintage":
        out = Image.blend(img, _sepia(img), 0.65)
        out = ImageEnhance.Contrast(out).enhance(0.9)
        return ImageEnhance.Brightness(out).enhance(1.05)
    if name == "warm":
        return _scale_channels(img, r=1.10, g=1.02, b=0.88)
    if name == "cool":
        return _scale_channels(img, r=0.90, g=1.0, b=1.12)
    if name == "fade":
        out = ImageEnhance.Contrast(img).enhance(0.8)
        out = ImageEnhance.Brightness(out).enhance(1.08)
        return Image.blend(out, Image.new("RGB", img.size, (232, 232, 232)), 0.14)
    if name == "poster":
        return ImageOps.posterize(img, 3)
    if name == "sketch":
        gray = ImageOps.grayscale(img)
        edges = ImageOps.invert(gray.filter(ImageFilter.FIND_EDGES))
        return ImageOps.autocontrast(edges).convert("RGB")
    return img


# ------------------------------------------------------------------ эффекты
def apply_effects(img, v):
    long_side = max(img.size)
    blur = v.get("blur", 0.0)
    if blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur * 0.004 * long_side))
    vig = v.get("vignette", 0.0)
    if vig > 0:
        strength = vig / 100.0
        grad = Image.radial_gradient("L").resize(img.size, Image.BILINEAR)
        mask = grad.point([int(255 * strength * (i / 255.0) ** 1.6)
                           for i in range(256)])
        img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask)
    return img


# ---------------------------------------------------------- области/рисунок
def _px_box(rect, size):
    w, h = size
    x0, y0, x1, y1 = rect
    xa, xb = sorted((x0 * w, x1 * w))
    ya, yb = sorted((y0 * h, y1 * h))
    box = (max(0, int(xa)), max(0, int(ya)), min(w, int(math.ceil(xb))),
           min(h, int(math.ceil(yb))))
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        return None
    return box


def apply_area_ops(img, ops):
    """Мозаика и размытие выбранных областей."""
    area = [o for o in ops if o.get("t") in AREA_TOOLS]
    if not area:
        return img
    img = img.copy()
    long_side = max(img.size)
    for op in area:
        box = _px_box(op["rect"], img.size)
        if box is None:
            continue
        region = img.crop(box)
        if op["t"] == "mosaic":
            block = max(6, int(long_side * 0.02))
            small = region.resize((max(1, region.width // block),
                                   max(1, region.height // block)),
                                  Image.BILINEAR)
            region = small.resize(region.size, Image.NEAREST)
        else:
            region = region.filter(
                ImageFilter.GaussianBlur(max(2.0, long_side * 0.012)))
        img.paste(region, box[:2])
    return img


_FONT_FILES = (
    "arial.ttf", "Arial.ttf", "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
    "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
_font_cache = {}


def _font(size):
    from PIL import ImageFont
    size = max(8, int(size))
    if size in _font_cache:
        return _font_cache[size]
    font = None
    for name in _FONT_FILES:
        try:
            font = ImageFont.truetype(name, size)
            break
        except Exception:
            continue
    if font is None:
        font = _load_font(size)
    _font_cache[size] = font
    return font


def _stroke_width(op, long_side):
    return max(1, int(round(float(op.get("size", 0.01)) * long_side)))


def _op_bbox(op, size, pad):
    """Прямоугольник (в пикселях), который занимает операция."""
    w, h = size
    long_side = max(size)
    t = op["t"]
    if t in ("brush", "eraser"):
        pts = [(x * w, y * h) for x, y in op["pts"]]
    elif t in ("line", "arrow", "rect", "ellipse"):
        pts = [(op["p0"][0] * w, op["p0"][1] * h),
               (op["p1"][0] * w, op["p1"][1] * h)]
    else:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    sw = _stroke_width(op, long_side)
    extra = pad + sw * (3 if t == "arrow" else 1)
    box = (int(min(xs) - extra), int(min(ys) - extra),
           int(max(xs) + extra) + 1, int(max(ys) + extra) + 1)
    box = (max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _draw_shape_mask(op, size, box):
    """Рисует операцию на маске L размером с box (маска в локальных координатах)."""
    w, h = size
    long_side = max(size)
    sw = _stroke_width(op, long_side)
    ox, oy = box[0], box[1]
    mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
    d = ImageDraw.Draw(mask)
    t = op["t"]

    def P(pt):
        return (pt[0] * w - ox, pt[1] * h - oy)

    def dot(p, r):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)

    r = sw / 2.0
    if t in ("brush", "eraser"):
        pts = [P(p) for p in op["pts"]]
        if len(pts) == 1:
            dot(pts[0], r)
        else:
            for a, b in zip(pts, pts[1:]):
                d.line((a, b), fill=255, width=sw)
            for p in pts:
                dot(p, r)
    elif t == "line":
        a, b = P(op["p0"]), P(op["p1"])
        d.line((a, b), fill=255, width=sw)
        dot(a, r)
        dot(b, r)
    elif t == "arrow":
        a, b = P(op["p0"]), P(op["p1"])
        d.line((a, b), fill=255, width=sw)
        dot(a, r)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        head = max(sw * 4.0, 10.0)
        for side in (-1, 1):
            tip = (b[0] - head * math.cos(ang + side * math.radians(28)),
                   b[1] - head * math.sin(ang + side * math.radians(28)))
            d.line((b, tip), fill=255, width=sw)
            dot(tip, r)
        dot(b, r)
    elif t in ("rect", "ellipse"):
        a, b = P(op["p0"]), P(op["p1"])
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        shape = d.rectangle if t == "rect" else d.ellipse
        if op.get("fill"):
            shape((x0, y0, x1, y1), fill=255)
        else:
            shape((x0, y0, x1, y1), outline=255, width=sw)
    return mask


def render_paint(size, ops):
    """Слой рисунка RGBA (прозрачный фон) с повтором всех операций по порядку."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    long_side = max(size)
    for op in ops:
        t = op.get("t")
        if t == "text":
            _paint_text(layer, op, long_side)
            continue
        if t not in PAINT_TOOLS:
            continue
        box = _op_bbox(op, size, 2)
        if box is None:
            continue
        mask = _draw_shape_mask(op, size, box)
        if t == "eraser":
            region = layer.crop(box)
            alpha = ImageChops.multiply(region.getchannel("A"),
                                        ImageChops.invert(mask))
            region.putalpha(alpha)
            layer.paste(region, box[:2])
            continue
        alpha = max(0.0, min(1.0, float(op.get("alpha", 1.0))))
        if alpha < 1.0:
            mask = mask.point([int(i * alpha) for i in range(256)])
        overlay = Image.new("RGBA", mask.size, _rgb(op.get("color", "#ff0000")) + (255,))
        overlay.putalpha(mask)
        layer.alpha_composite(overlay, dest=box[:2])
    return layer


def _paint_text(layer, op, long_side):
    text = op.get("text", "")
    if not text.strip():
        return
    font = _font(float(op.get("size", 0.05)) * long_side)
    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    l, t, r, b = probe.multiline_textbbox((0, 0), text, font=font)
    pad = 4
    ov = Image.new("RGBA", (r - l + pad * 2, b - t + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(ov).multiline_text(
        (pad - l, pad - t), text, font=font,
        fill=_rgb(op.get("color", "#ffffff")) +
        (int(255 * max(0.0, min(1.0, float(op.get("alpha", 1.0))))),))
    x = int(op["pos"][0] * layer.width) - pad
    y = int(op["pos"][1] * layer.height) - pad
    # alpha_composite не принимает отрицательные dest — подрезаем
    sx, sy = max(0, -x), max(0, -y)
    if sx >= ov.width or sy >= ov.height:
        return
    ov = ov.crop((sx, sy, ov.width, ov.height))
    x, y = max(0, x), max(0, y)
    cw, ch = min(ov.width, layer.width - x), min(ov.height, layer.height - y)
    if cw <= 0 or ch <= 0:
        return
    layer.alpha_composite(ov.crop((0, 0, cw, ch)), dest=(x, y))


# ------------------------------------------------------------------- рендер
def render_base(base, st, bg="#ffffff"):
    """Всё, кроме рисования: геометрия → цвет → фильтр → эффекты → области.
    Результат можно кэшировать, пока меняется только рисунок."""
    v = st.v
    img = base
    if v["flip_h"]:
        img = ImageOps.mirror(img)
    if v["flip_v"]:
        img = ImageOps.flip(img)
    k = int(v["rot90"]) % 4
    if k:
        img = img.rotate(-90 * k, expand=True)

    img = apply_frame(img, v, bg)
    img = apply_color(img, v)
    img = apply_filter(img, v["filter"])
    img = apply_effects(img, v)
    return apply_area_ops(img, st.ops)


def compose_paint(img, st, extra_ops=()):
    """Накладывает кисть/фигуры/текст (и необязательные временные extra_ops)."""
    paint_ops = [o for o in list(st.ops) + list(extra_ops)
                 if o.get("t") in PAINT_TOOLS]
    if not paint_ops:
        return img
    layer = render_paint(img.size, paint_ops)
    out = img.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def render(base, st, bg="#ffffff"):
    """Применяет всё редактирование к base (RGB) и возвращает RGB-результат."""
    return compose_paint(render_base(base, st, bg), st)


def make_preview_base(img, max_side=1000):
    """Уменьшенная копия для работы в реальном времени."""
    base = img.copy()
    base.thumbnail((max_side, max_side), Image.LANCZOS)
    return base


def auto_enhance(st):
    """Мягкое «автоулучшение»: чуть контраста, насыщенности и резкости."""
    st.set("brightness", 4)
    st.set("contrast", 14)
    st.set("saturation", 14)
    st.set("sharpness", 20)
