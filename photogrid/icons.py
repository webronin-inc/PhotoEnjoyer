"""Собственный набор иконок интерфейса.

Иконки описаны векторно (сетка 24×24, линия ~1.9) и рисуются через Pillow с
суперсэмплингом, поэтому выглядят одинаково на любой системе и не зависят от
шрифта Segoe MDL2. Для Tk отдаются как PhotoImage нужного цвета и размера.

Примитивы (координаты в сетке 24×24):
    ("L", [(x, y), ...])            ломаная
    ("Z", [(x, y), ...])            замкнутый контур
    ("C", cx, cy, r)                окружность (контур)
    ("D", cx, cy, r)                залитая точка
    ("R", x, y, w, h, радиус)       скруглённый прямоугольник (контур)
    ("A", cx, cy, r, a0, a1)        дуга, углы в градусах (0° — вправо,
                                    по часовой стрелке)
    ("U", [фигуры…])                контур объединения залитых фигур
    фигуры внутри "U": ("c", cx, cy, r) · ("r", x, y, w, h, радиус) ·
                       ("p", [(x, y), ...]) · ("h", cx, cy, r) — «дырка»
"""
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

GRID = 24.0
STROKE = 2.0          # толщина линии в единицах сетки
_SS = 4               # суперсэмплинг


# ----------------------------------------------------------------- геометрия
def _arc_pts(cx, cy, r, a0, a1, step=8):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))))
            for i in range(n)]


def _quad(p0, p1, p2, n=16):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / (n - 1) for i in range(n))]


def _rays(cx, cy, r0, r1, n=8, start=0.0):
    out = []
    for i in range(n):
        a = math.radians(start + 360.0 * i / n)
        out.append(("L", [(cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                          (cx + r1 * math.cos(a), cy + r1 * math.sin(a))]))
    return out


def _moon_shapes():
    return [("c", 12, 12, 8.5), ("h", 17, 8.2, 6.6)]


def _cloud_shapes():
    return [("c", 8, 14.5, 4.6), ("c", 13.2, 10.5, 5.6),
            ("c", 18, 14.7, 3.8), ("r", 8, 13, 10, 6.4, 1)]


# ------------------------------------------------------------------ каталог
ICONS = {
    "collage": [("R", 3, 3, 8, 8, 1.8), ("R", 13, 3, 8, 8, 1.8),
                ("R", 3, 13, 8, 8, 1.8), ("R", 13, 13, 8, 8, 1.8)],
    "image": [("R", 3, 4, 18, 16, 2.2), ("C", 9, 9.6, 1.7),
              ("L", [(21, 16.5), (15.5, 11), (6, 20)])],
    "plugins": [("L", [(9, 2.5), (9, 7)]), ("L", [(15, 2.5), (15, 7)]),
                ("Z", [(5.5, 7), (18.5, 7), (18.5, 12), (15, 15.5),
                       (9, 15.5), (5.5, 12)]),
                ("L", [(12, 15.5), (12, 21.5)])],
    "batch": [("Z", [(12, 3), (21.5, 8), (12, 13), (2.5, 8)]),
              ("L", [(2.5, 12.5), (12, 17.5), (21.5, 12.5)]),
              ("L", [(2.5, 17), (12, 22), (21.5, 17)])],
    "layers": [("Z", [(12, 3), (21.5, 8), (12, 13), (2.5, 8)]),
               ("L", [(2.5, 12.5), (12, 17.5), (21.5, 12.5)]),
               ("L", [(2.5, 17), (12, 22), (21.5, 17)])],
    "cloud": [("U", _cloud_shapes())],
    "save": [("R", 3.5, 3.5, 17, 17, 2.4),
             ("L", [(7.5, 3.5), (7.5, 9), (15.5, 9), (15.5, 3.5)]),
             ("L", [(7.5, 20.5), (7.5, 14.5), (16.5, 14.5), (16.5, 20.5)])],
    "folder": [("Z", [(3, 6.5), (9, 6.5), (11.2, 9), (21, 9),
                      (21, 19.5), (3, 19.5)])],
    "refresh": [("A", 12, 12, 8, 200, 340), ("A", 12, 12, 8, 20, 160),
                ("L", [(17.2, 3.6), (18.6, 7.4), (14.8, 8.6)]),
                ("L", [(6.8, 20.4), (5.4, 16.6), (9.2, 15.4)])],
    "update": [("C", 12, 12, 9), ("L", [(12, 16.3), (12, 8)]),
               ("L", [(8.4, 11.4), (12, 7.8), (15.6, 11.4)])],
    "download": [("L", [(12, 3.5), (12, 15)]),
                 ("L", [(7, 10.3), (12, 15.3), (17, 10.3)]),
                 ("L", [(4, 20), (20, 20)])],
    "upload": [("L", [(12, 15.5), (12, 4)]),
               ("L", [(7, 8.7), (12, 3.7), (17, 8.7)]),
               ("L", [(4, 20), (20, 20)])],
    "check": [("L", [(4.5, 12.5), (9.8, 17.8), (19.5, 6.8)])],
    "plus": [("L", [(12, 4.5), (12, 19.5)]), ("L", [(4.5, 12), (19.5, 12)])],
    "delete": [("L", [(4, 7), (20, 7)]),
               ("L", [(9, 7), (9, 4), (15, 4), (15, 7)]),
               ("Z", [(6, 7), (7, 20.5), (17, 20.5), (18, 7)]),
               ("L", [(10.2, 11), (10.2, 16.5)]),
               ("L", [(13.8, 11), (13.8, 16.5)])],
    "shuffle": [("L", [(3, 7), (7.5, 7), (15.5, 17), (20, 17)]),
                ("L", [(3, 17), (7.5, 17), (9.7, 14.2)]),
                ("L", [(14.3, 9.8), (15.5, 7), (20, 7)]),
                ("L", [(17.3, 14.2), (20.2, 17), (17.3, 19.8)]),
                ("L", [(17.3, 4.2), (20.2, 7), (17.3, 9.8)])],
    "clear": [("C", 12, 12, 9), ("L", [(8.8, 8.8), (15.2, 15.2)]),
              ("L", [(15.2, 8.8), (8.8, 15.2)])],
    "theme": [("C", 12, 12, 4.2)] + _rays(12, 12, 7.4, 10.2),
    "sun": [("C", 12, 12, 4.2)] + _rays(12, 12, 7.4, 10.2),
    "theme_alt": [("U", _moon_shapes())],
    "moon": [("U", _moon_shapes())],
    "settings": [("L", [(4, 6.5), (12.7, 6.5)]), ("C", 15, 6.5, 2.3),
                 ("L", [(17.3, 6.5), (20, 6.5)]),
                 ("L", [(4, 12), (5.7, 12)]), ("C", 8, 12, 2.3),
                 ("L", [(10.3, 12), (20, 12)]),
                 ("L", [(4, 17.5), (10.7, 17.5)]), ("C", 13, 17.5, 2.3),
                 ("L", [(15.3, 17.5), (20, 17.5)])],
    "help": [("C", 12, 12, 9)]
            + [("L", _arc_pts(12, 9.6, 2.9, 190, 405) + [(12, 13.2),
                                                       (12, 14.6)])]
            + [("D", 12, 17.6, 1.05)],
    "bell": [("L", [(4.5, 17.5), (6.3, 15.7), (6.3, 10.3)]
              + _arc_pts(12, 10.3, 5.7, 180, 360)
              + [(17.7, 15.7), (19.5, 17.5), (4.5, 17.5)]),
             ("L", _arc_pts(12, 18.2, 2.2, 20, 160))],
    "info": [("C", 12, 12, 9), ("L", [(12, 11), (12, 16.8)]),
             ("D", 12, 7.7, 1.1)],
    "close": [("L", [(5.5, 5.5), (18.5, 18.5)]),
              ("L", [(18.5, 5.5), (5.5, 18.5)])],
    "menu": [("L", [(4, 6.5), (20, 6.5)]), ("L", [(4, 12), (20, 12)]),
             ("L", [(4, 17.5), (20, 17.5)])],
    # --- для подписей и интерфейса
    "caption": [("R", 3, 3.5, 18, 17, 2.4), ("L", [(7, 16.2), (17, 16.2)]),
                ("L", [(7, 12.2), (13, 12.2)])],
    "text": [("L", [(5, 7), (5, 4.5), (19, 4.5), (19, 7)]),
             ("L", [(12, 4.5), (12, 19.5)]), ("L", [(8.6, 19.5), (15.4, 19.5)])],
    "align_left": [("L", [(4, 6), (20, 6)]), ("L", [(4, 11), (14, 11)]),
                   ("L", [(4, 16), (18, 16)]), ("L", [(4, 21), (11, 21)])],
    "align_center": [("L", [(4, 6), (20, 6)]), ("L", [(7, 11), (17, 11)]),
                     ("L", [(5, 16), (19, 16)]), ("L", [(8.5, 21), (15.5, 21)])],
    "align_right": [("L", [(4, 6), (20, 6)]), ("L", [(10, 11), (20, 11)]),
                    ("L", [(6, 16), (20, 16)]), ("L", [(13, 21), (20, 21)])],
    "hash": [("L", [(9, 3.5), (7, 20.5)]), ("L", [(17, 3.5), (15, 20.5)]),
             ("L", [(4, 9), (20.5, 9)]), ("L", [(3.5, 15), (20, 15)])],
    "wand": [("L", [(4.5, 19.5), (14.5, 9.5)]),
             ("L", [(16.5, 3), (16.5, 8)]), ("L", [(14, 5.5), (19, 5.5)]),
             ("L", [(19.5, 12), (19.5, 15.5)]), ("L", [(17.7, 13.8), (21.3, 13.8)])],
    "copy": [("R", 9, 9, 12, 12, 2.2),
             ("L", [(15, 9), (15, 5.8), (14.2, 4), (12.4, 4), (5.8, 4),
                    (4, 5.8), (4, 12.4), (4, 14.2), (5.8, 15), (9, 15)])],
    "clipboard": [("R", 5, 4.5, 14, 17, 2.2), ("R", 9, 2.5, 6, 4, 1.2)],
    "edit": [("Z", [(4, 20), (4.9, 15.2), (16, 4.1), (19.9, 8), (8.8, 19.1)]),
             ("L", [(13.4, 6.7), (17.3, 10.6)])],
    "eye": [("L", _quad((2.5, 12), (12, 3.2), (21.5, 12))
                   + _quad((21.5, 12), (12, 20.8), (2.5, 12))[1:]),
            ("C", 12, 12, 3.1)],
}
KINDS = tuple(ICONS)


# ----------------------------------------------------------------- рендер
def _stroke_w(scale):
    return max(1, int(round(STROKE * scale)))


def _draw_line(d, pts, w, scale, close=False):
    pts = [(x * scale, y * scale) for x, y in pts]
    if close:
        pts = pts + [pts[0]]
    d.line(pts, fill=255, width=w, joint="curve")
    r = w / 2.0
    for x, y in pts:                         # скруглённые стыки и концы
        d.ellipse((x - r, y - r, x + r, y + r), fill=255)


def _render_union(shapes, scale, w, size_px):
    solid = Image.new("L", (size_px, size_px), 0)
    d = ImageDraw.Draw(solid)
    holes = []
    for sh in shapes:
        k = sh[0]
        if k == "c":
            _, cx, cy, r = sh
            d.ellipse(((cx - r) * scale, (cy - r) * scale,
                       (cx + r) * scale, (cy + r) * scale), fill=255)
        elif k == "r":
            _, x, y, ww, hh, rad = sh
            d.rounded_rectangle((x * scale, y * scale, (x + ww) * scale,
                                 (y + hh) * scale), radius=rad * scale, fill=255)
        elif k == "p":
            d.polygon([(x * scale, y * scale) for x, y in sh[1]], fill=255)
        elif k == "h":
            holes.append(sh)
    # дырки вырезаются после объединения
    hole_mask = Image.new("L", (size_px, size_px), 0)
    hd = ImageDraw.Draw(hole_mask)
    for _, cx, cy, r in holes:
        hd.ellipse(((cx - r) * scale, (cy - r) * scale,
                    (cx + r) * scale, (cy + r) * scale), fill=255)
    solid = ImageChops.subtract(solid, hole_mask)
    k = max(3, 2 * w - 1)             # толщина контура ≈ w (как у линий)
    inner = solid.filter(ImageFilter.MinFilter(k))
    return ImageChops.subtract(solid, inner)


_mask_cache = {}


def mask(kind, size):
    """Маска иконки (L-изображение size×size)."""
    key = (kind, int(size))
    m = _mask_cache.get(key)
    if m is not None:
        return m
    prims = ICONS.get(kind)
    if prims is None:
        prims = ICONS["image"]
    size = int(size)
    scale = size * _SS / GRID
    big = size * _SS
    w = _stroke_w(scale * (1.0 if size >= 20 else 1.05))
    img = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(img)
    for p in prims:
        k = p[0]
        if k == "L":
            _draw_line(d, p[1], w, scale)
        elif k == "Z":
            _draw_line(d, p[1], w, scale, close=True)
        elif k == "C":
            _, cx, cy, r = p
            d.ellipse(((cx - r) * scale, (cy - r) * scale,
                       (cx + r) * scale, (cy + r) * scale),
                      outline=255, width=w)
        elif k == "D":
            _, cx, cy, r = p
            d.ellipse(((cx - r) * scale, (cy - r) * scale,
                       (cx + r) * scale, (cy + r) * scale), fill=255)
        elif k == "R":
            _, x, y, ww, hh, rad = p
            d.rounded_rectangle((x * scale, y * scale, (x + ww) * scale,
                                 (y + hh) * scale), radius=rad * scale,
                                outline=255, width=w)
        elif k == "A":
            _, cx, cy, r, a0, a1 = p
            _draw_line(d, _arc_pts(cx, cy, r, a0, a1, 6), w, scale)
        elif k == "U":
            img = ImageChops.lighter(img, _render_union(p[1], scale, w, big))
            d = ImageDraw.Draw(img)
    out = img.resize((size, size), Image.LANCZOS)
    _mask_cache[key] = out
    return out


def pil_icon(kind, size, color):
    """Иконка как RGBA-изображение."""
    m = mask(kind, size)
    rgb = _hex_to_rgb(color)
    img = Image.new("RGBA", m.size, rgb + (0,))
    img.putalpha(m)
    return img


def _hex_to_rgb(color):
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


# ------------------------------------------------------------- Tk-слой
_tk_cache = {}
_TK_CACHE_MAX = 1200


def tk_icon(kind, size, color, pad_right=0):
    """PhotoImage иконки; цвет квантуется, чтобы анимации не плодили картинки.

    pad_right — прозрачный отступ справа (зазор между иконкой и текстом
    на кнопках с compound="left").
    """
    r, g, b = _hex_to_rgb(color)
    q = lambda v: min(255, (v + 2) // 4 * 4)          # шаг 4 — незаметно глазу
    key = (kind, int(size), q(r), q(g), q(b), int(pad_right))
    img = _tk_cache.get(key)
    if img is None:
        if len(_tk_cache) >= _TK_CACHE_MAX:
            for old in list(_tk_cache)[:_TK_CACHE_MAX // 4]:
                _tk_cache.pop(old, None)
        pil = pil_icon(kind, size, "#%02x%02x%02x" % key[2:5])
        if pad_right:
            wide = Image.new("RGBA", (pil.width + int(pad_right), pil.height),
                             (0, 0, 0, 0))
            wide.paste(pil, (0, 0))
            pil = wide
        img = ImageTk.PhotoImage(pil)
        _tk_cache[key] = img
    return img


def draw(canvas, kind, cx, cy, size=20, color="#ffffff"):
    """Рисует иконку на canvas по центру (cx, cy)."""
    img = tk_icon(kind, max(8, int(round(size))), color)
    # картинку держит сам canvas: кэш может вытеснить старые записи, а
    # элемент на холсте без ссылки стал бы пустым
    refs = getattr(canvas, "_icon_refs", None)
    if refs is None:
        refs = canvas._icon_refs = []
    refs.append(img)
    if len(refs) > 8:
        del refs[:-8]
    return canvas.create_image(cx, cy, image=img, anchor="center")


def contact_sheet(size=48, cols=8, color="#e6e6ef", bg="#18181f"):
    """Лист со всеми иконками — для проверки глазами."""
    names = list(ICONS)
    rows = (len(names) + cols - 1) // cols
    cell = size + 28
    sheet = Image.new("RGB", (cols * cell, rows * cell), bg)
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        x, y = (i % cols) * cell, (i // cols) * cell
        ic = pil_icon(n, size, color)
        sheet.paste(ic, (x + (cell - size) // 2, y + 6), ic)
        d.text((x + 4, y + size + 12), n, fill="#8a8aa0")
    return sheet
