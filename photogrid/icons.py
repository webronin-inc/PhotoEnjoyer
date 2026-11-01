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
    "template": [("R", 3, 3.5, 18, 17, 2.4), ("L", [(3, 9.5), (21, 9.5)]),
                 ("L", [(10, 9.5), (10, 20.5)])],
    "tools": [("L", [(14.5, 4.2), (19.8, 9.5), (16.2, 13.1), (10.9, 7.8)]),
              ("L", [(14.5, 4.2), (11.5, 2.8), (8.2, 6.1), (9.6, 9.1)]),
              ("L", [(15.2, 12.4), (5.4, 20.6)]),
              ("L", [(9.2, 8.5), (16.2, 15.5)])],
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
import itertools
import tkinter as _tk

_epoch_counter = itertools.count(1)


def _epoch():
    """Номер текущего Tk-интерпретатора. PhotoImage привязан к интерпретатору,
    поэтому кэш картинок разделяется по «эпохам» (важно для тестов и для
    повторного создания окна: старая картинка в новом окне — ошибка Tcl)."""
    root = getattr(_tk, "_default_root", None)
    if root is None:
        return 0
    e = getattr(root, "_pe_epoch", None)
    if e is None:
        e = root._pe_epoch = next(_epoch_counter)
    return e


_tk_cache = {}
_TK_CACHE_MAX = 1200


def tk_icon(kind, size, color, pad_right=0):
    """PhotoImage иконки; цвет квантуется, чтобы анимации не плодили картинки.

    pad_right — прозрачный отступ справа (зазор между иконкой и текстом
    на кнопках с compound="left").
    """
    r, g, b = _hex_to_rgb(color)
    q = lambda v: min(255, (v + 2) // 4 * 4)          # шаг 4 — незаметно глазу
    key = (_epoch(), kind, int(size), q(r), q(g), q(b), int(pad_right))
    img = _tk_cache.get(key)
    if img is None:
        if len(_tk_cache) >= _TK_CACHE_MAX:
            for old in list(_tk_cache)[:_TK_CACHE_MAX // 4]:
                _tk_cache.pop(old, None)
        pil = pil_icon(kind, size, "#%02x%02x%02x" % key[3:6])
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


# ==============================================================
#  3D-неон: светящаяся «трубка» с объёмом
# ==============================================================
NEON = {                      # яркие оттенки, одинаково читаются на любой теме
    "violet": "#a07bff", "cyan": "#23e5ff", "pink": "#ff4fd8",
    "lime": "#86ff6b", "orange": "#ffa23d", "blue": "#4f8bff",
    "red": "#ff5470", "white": "#e9ecff",
}

_NSS = 2                      # суперсэмплинг неона


def _mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def neon_pil(kind, size, color, glow=1.0, extrude=True):
    """RGBA-картинка (size + 2·отступ) квадратная; отступ вмещает свечение.

    glow 0 — «выключенная» трубка (только объём), 1 — горит, >1 — ярче.
    """
    return neon_from_mask(mask(kind, int(size) * _NSS), int(size), color,
                          glow, extrude)


def neon_from_mask(m_small, size, color, glow=1.0, extrude=True):
    """Неон по готовой маске размера size·_NSS (иконка, буква логотипа…)."""
    size = int(size)
    pad = max(4, int(round(size * 0.30)))
    total = size + 2 * pad
    T = total * _NSS
    base = _hex_to_rgb(color)
    glow = max(0.0, float(glow))

    M = Image.new("L", (T, T), 0)
    M.paste(m_small, (pad * _NSS, pad * _NSS))

    out = Image.new("RGBA", (T, T), base + (0,))

    # --- свечение: два размытия разного радиуса
    if glow > 0.02:
        r1 = max(1.0, size * _NSS * 0.075)
        r2 = max(2.0, size * _NSS * 0.19)
        g = ImageChops.add(M.filter(ImageFilter.GaussianBlur(r1)).point(lambda v: min(255, int(v * 1.0))),
                           M.filter(ImageFilter.GaussianBlur(r2)).point(lambda v: min(255, int(v * 1.1))))
        g = g.point(lambda v: min(255, int(v * 0.85 * min(glow, 1.6))))
        layer = Image.new("RGBA", (T, T), base + (0,))
        layer.putalpha(g)
        out = Image.alpha_composite(out, layer)

    # --- объём: сдвинутые тёмные копии позади (выдавливание вниз-вправо)
    if extrude:
        depth = max(1, int(round(size * _NSS * 0.055)))
        dark = _mix(base, (8, 6, 24), 0.62)
        for i in range(depth, 0, -1):
            sh = ImageChops.offset(M, int(round(i * 0.55)), i)
            t = i / depth
            col = _mix(dark, _mix(base, (8, 6, 24), 0.35), 1 - t)
            lay = Image.new("RGBA", (T, T), col + (0,))
            lay.putalpha(sh)
            out = Image.alpha_composite(out, lay)

    # --- лицевая грань: вертикальный градиент (светлее сверху) — «цилиндр»
    top = _mix(base, (255, 255, 255), 0.42 * min(1.0, 0.35 + glow))
    bot = _mix(base, (0, 0, 20), 0.20 * (1.2 - min(1.0, glow)) + 0.05)
    grad = Image.new("RGB", (1, T))
    for y in range(T):
        grad.putpixel((0, y), _mix(top, bot, y / (T - 1)))
    face = grad.resize((T, T)).convert("RGBA")
    face.putalpha(M)
    out = Image.alpha_composite(out, face)

    # --- раскалённая сердцевина трубки (светлая линия по центру штриха)
    k = max(3, int(size * _NSS * 0.10) | 1)
    core_m = M.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.GaussianBlur(0.6))
    core_col = _mix(base, (255, 255, 255), 0.55 + 0.35 * min(1.0, glow))
    core = Image.new("RGBA", (T, T), core_col + (0,))
    core.putalpha(core_m.point(lambda v: int(v * (0.55 + 0.45 * min(1.0, glow)))))
    out = Image.alpha_composite(out, core)

    # --- глянцевый блик по верхне-левой кромке
    edge = ImageChops.subtract(M, ImageChops.offset(M, max(1, _NSS), max(1, _NSS)))
    hl = Image.new("RGBA", (T, T), (255, 255, 255, 0))
    hl.putalpha(edge.point(lambda v: int(v * 0.55)))
    out = Image.alpha_composite(out, hl)

    return out.resize((total, total), Image.LANCZOS)


_neon_cache = {}
_neon_pil_cache = {}          # готовые PIL-картинки (их греет фоновый поток)


def _neon_key(kind, size, color, glow, extrude=True):
    r, g, b = _hex_to_rgb(color)
    q = lambda v: min(255, (v + 4) // 8 * 8)
    gq = round(max(0.0, glow) * 4) / 4.0                  # шаг 0.25
    return (kind, int(size), q(r), q(g), q(b), gq, bool(extrude))


def tk_neon(kind, size, color, glow=1.0, extrude=True):
    """PhotoImage неоновой иконки; цвет и свечение квантуются для кэша."""
    key = _neon_key(kind, size, color, glow, extrude)
    tkey = (_epoch(),) + key
    img = _neon_cache.get(tkey)
    if img is None:
        if len(_neon_cache) >= 400:
            for old in list(_neon_cache)[:100]:
                _neon_cache.pop(old, None)
        pil = _neon_pil_cache.get(key)
        if pil is None:
            pil = neon_pil(kind, size, "#%02x%02x%02x" % key[2:5],
                           glow=key[5], extrude=extrude)
            _neon_pil_cache[key] = pil
        img = ImageTk.PhotoImage(pil)
        _neon_cache[tkey] = img
    return img


def warm_neon(specs):
    """Рендерит неон заранее в фоновом потоке.

    specs — список (kind, size, color, glow). Создание PhotoImage остаётся в
    главном потоке (в tk_neon), здесь только Pillow — это безопасно.
    """
    import threading

    def work():
        for kind, size, color, glow in specs:
            key = _neon_key(kind, size, color, glow)
            if key in _neon_pil_cache:
                continue
            try:
                _neon_pil_cache[key] = neon_pil(
                    kind, size, "#%02x%02x%02x" % key[2:5], glow=key[5])
            except Exception:
                pass

    threading.Thread(target=work, daemon=True).start()


def neon_pad(size):
    """Отступ, который неон добавляет вокруг иконки (для расчёта раскладки)."""
    return max(4, int(round(int(size) * 0.30)))


def draw_neon(canvas, kind, cx, cy, size=24, color="#a07bff", glow=1.0):
    """Рисует неоновую иконку по центру (cx, cy) и держит ссылку на картинку."""
    img = tk_neon(kind, size, color, glow)
    refs = getattr(canvas, "_neon_refs", None)
    if refs is None:
        refs = canvas._neon_refs = []
    refs.append(img)
    if len(refs) > 6:
        del refs[:-6]
    return canvas.create_image(cx, cy, image=img, anchor="center")


def neon_sheet(size=44, cols=8, glow=1.0, bg="#10101a"):
    """Лист-образец неоновых иконок (для проверки глазами)."""
    names = ["collage", "template", "layers", "cloud", "edit", "tools", "plugins",
             "settings", "help", "caption", "wand", "copy", "sun", "refresh",
             "folder", "eye"]
    hues = list(NEON.values())
    cell = size + 2 * neon_pad(size) + 24
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), bg)
    for i, n in enumerate(names):
        ic = neon_pil(n, size, hues[i % len(hues)], glow=glow)
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(ic, (x + (cell - ic.width) // 2, y + 8), ic)
    return sheet


# ==============================================================
#  Логотип приложения: объёмная неоновая плитка с буквой
# ==============================================================
def _vgrad(size, top, bottom):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        g.putpixel((0, y), _mix(top, bottom, y / max(1, size - 1)))
    return g.resize((size, size))


def logo_pil(size=256, accent="#7c6cff", letter="P", glow=1.0):
    """Квадратный логотип с запасом под свечение (размер плитки = size)."""
    from .caption_render import load_font
    pad = int(size * 0.16)
    total = size + 2 * pad
    S = 2                                           # суперсэмплинг
    T, tile = total * S, size * S
    base = _hex_to_rgb(accent)
    r = int(tile * 0.27)
    off = pad * S

    plate = Image.new("L", (T, T), 0)
    ImageDraw.Draw(plate).rounded_rectangle(
        (off, off, off + tile - 1, off + tile - 1), radius=r, fill=255)

    out = Image.new("RGBA", (T, T), base + (0,))
    # свечение вокруг плитки
    halo = plate.filter(ImageFilter.GaussianBlur(tile * 0.07)).point(
        lambda v: int(v * 0.75 * min(1.4, glow)))
    layer = Image.new("RGBA", (T, T), base + (0,)); layer.putalpha(halo)
    out = Image.alpha_composite(out, layer)

    # «толщина» плитки: тёмная копия, сдвинутая вниз
    thick = max(2, int(tile * 0.035))
    for i in range(thick, 0, -1):
        sh = ImageChops.offset(plate, 0, i)
        lay = Image.new("RGBA", (T, T), _mix(base, (6, 4, 20), 0.6) + (0,))
        lay.putalpha(sh)
        out = Image.alpha_composite(out, lay)

    # лицо плитки: диагональ-подобный вертикальный градиент
    face = _vgrad(T, _mix(base, (255, 255, 255), 0.30),
                  _mix(base, (10, 6, 40), 0.40)).convert("RGBA")
    face.putalpha(plate)
    out = Image.alpha_composite(out, face)

    # верхний глянец
    gloss = Image.new("L", (T, T), 0)
    ImageDraw.Draw(gloss).ellipse(
        (off - tile * 0.2, off - tile * 0.78, off + tile * 1.2, off + tile * 0.52),
        fill=255)
    gloss = ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(tile * 0.01)), plate)
    gl = Image.new("RGBA", (T, T), (255, 255, 255, 0))
    gl.putalpha(gloss.point(lambda v: int(v * 0.20)))
    out = Image.alpha_composite(out, gl)

    # фаска: светлая кромка сверху, тёмная снизу
    inner = plate.filter(ImageFilter.MinFilter(max(3, int(tile * 0.02) | 1)))
    rim = ImageChops.subtract(plate, inner)
    up = ImageChops.multiply(rim, ImageChops.subtract(plate, ImageChops.offset(plate, 0, max(2, S * 2))))
    rl = Image.new("RGBA", (T, T), (255, 255, 255, 0)); rl.putalpha(up.point(lambda v: int(v * 0.8)))
    out = Image.alpha_composite(out, rl)

    # буква: белая «трубка» с неоном и объёмом
    font = load_font(int(tile * 0.62), "Segoe UI", bold=True)
    gm = Image.new("L", (T, T), 0)
    gd = ImageDraw.Draw(gm)
    bb = gd.textbbox((0, 0), letter, font=font)
    gw, gh = bb[2] - bb[0], bb[3] - bb[1]
    gd.text((off + (tile - gw) / 2 - bb[0], off + (tile - gh) / 2 - bb[1] - tile * 0.01),
            letter, font=font, fill=255)
    # тень под буквой
    shadow = ImageChops.offset(gm, 0, int(tile * 0.03)).filter(ImageFilter.GaussianBlur(tile * 0.02))
    sl = Image.new("RGBA", (T, T), (8, 4, 40, 0)); sl.putalpha(shadow.point(lambda v: int(v * 0.55)))
    out = Image.alpha_composite(out, sl)
    for i in range(max(1, int(tile * 0.02)), 0, -1):
        lay = Image.new("RGBA", (T, T), _mix(base, (0, 0, 30), 0.55) + (0,))
        lay.putalpha(ImageChops.offset(gm, 0, i))
        out = Image.alpha_composite(out, lay)
    gface = _vgrad(T, (255, 255, 255), _mix((255, 255, 255), base, 0.35)).convert("RGBA")
    gface.putalpha(gm)
    out = Image.alpha_composite(out, gface)
    return out.resize((total, total), Image.LANCZOS)
