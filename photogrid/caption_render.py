"""Отрисовка подписей под/на фото. Не зависит от UI (только Pillow).

Настройки читаются из config по ключам ``caption_*`` (см. CAPTION_DEFAULTS).
Значения по умолчанию воспроизводят прежний вид подписи: полупрозрачная
плашка по всей ширине ячейки, Times New Roman, по центру, до 3 строк.
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------- настройки
CAPTION_DEFAULTS = {
    "caption_style": "bar",          # bar | pill | outline
    "caption_position": "bottom",    # bottom | top
    "caption_size_ratio": 0.045,     # размер шрифта от стороны ячейки
    "caption_color": "#ffffff",
    "caption_bg_color": "#000000",
    "caption_bg_opacity": 170,       # 0..255
    "caption_font": "Times New Roman",
    "caption_bold": False,
    "caption_italic": False,
    "caption_align": "center",       # left | center | right
    "caption_max_lines": 3,
    "caption_shadow": True,
}

STYLES = (("bar", "Плашка"), ("pill", "Капсула"), ("outline", "Контур"))
POSITIONS = (("top", "Сверху"), ("bottom", "Снизу"))
ALIGNS = (("left", "Слева"), ("center", "По центру"), ("right", "Справа"))


def caption_settings(config):
    """Настройки подписи с подстановкой значений по умолчанию и проверкой."""
    s = {}
    for k, default in CAPTION_DEFAULTS.items():
        v = config.get(k, default) if config is not None else default
        if isinstance(default, bool):
            v = bool(v)
        elif isinstance(default, int):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = default
        elif isinstance(default, float):
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = default
        elif v is None:
            v = default
        s[k] = v
    s["caption_style"] = s["caption_style"] if s["caption_style"] in dict(STYLES) else "bar"
    s["caption_position"] = "top" if s["caption_position"] == "top" else "bottom"
    s["caption_align"] = s["caption_align"] if s["caption_align"] in dict(ALIGNS) else "center"
    s["caption_size_ratio"] = min(0.12, max(0.02, s["caption_size_ratio"]))
    s["caption_bg_opacity"] = min(255, max(0, s["caption_bg_opacity"]))
    s["caption_max_lines"] = min(6, max(1, s["caption_max_lines"]))
    return s


# ------------------------------------------------------------------ шрифты
# семейство → файлы (обычный, жирный, курсив, жирный курсив);
# для каждого стиля несколько кандидатов: Windows, macOS, Linux-аналоги
_DJV = ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf")
_DJV_SERIF = ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf",
              "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf")


def _fam(win, extra=_DJV):
    return [[win[i], extra[i]] for i in range(4)]


FONT_FAMILIES = {
    "Times New Roman": [
        ["times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf",
         "Times_New_Roman.ttf"],
        ["timesbd.ttf", "Times New Roman Bold.ttf", "LiberationSerif-Bold.ttf"],
        ["timesi.ttf", "Times New Roman Italic.ttf", "LiberationSerif-Italic.ttf"],
        ["timesbi.ttf", "Times New Roman Bold Italic.ttf",
         "LiberationSerif-BoldItalic.ttf"]],
    "Arial": [
        ["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"],
        ["arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"],
        ["ariali.ttf", "Arial Italic.ttf", "LiberationSans-Italic.ttf"],
        ["arialbi.ttf", "Arial Bold Italic.ttf", "LiberationSans-BoldItalic.ttf"]],
    "Segoe UI": _fam(("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf")),
    "Georgia": _fam(("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
                    _DJV_SERIF),
    "Calibri": [
        ["calibri.ttf", "Calibri.ttf", "Carlito-Regular.ttf"],
        ["calibrib.ttf", "Calibri Bold.ttf", "Carlito-Bold.ttf"],
        ["calibrii.ttf", "Calibri Italic.ttf", "Carlito-Italic.ttf"],
        ["calibriz.ttf", "Calibri Bold Italic.ttf", "Carlito-BoldItalic.ttf"]],
    "Verdana": _fam(("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf")),
    "Courier New": [
        ["cour.ttf", "Courier New.ttf", "LiberationMono-Regular.ttf"],
        ["courbd.ttf", "Courier New Bold.ttf", "LiberationMono-Bold.ttf"],
        ["couri.ttf", "Courier New Italic.ttf", "LiberationMono-Italic.ttf"],
        ["courbi.ttf", "Courier New Bold Italic.ttf",
         "LiberationMono-BoldItalic.ttf"]],
    "Impact": [["impact.ttf", "Impact.ttf"], [], [], []],
    "Comic Sans MS": [
        ["comic.ttf", "Comic Sans MS.ttf"], ["comicbd.ttf", "Comic Sans MS Bold.ttf"],
        ["comici.ttf"], ["comicz.ttf"]],
}
DEFAULT_FONT = "Times New Roman"

_font_index = None


def _font_dirs():
    dirs = []
    if sys.platform == "win32":
        win = os.environ.get("WINDIR", "C:/Windows")
        dirs += [Path(win) / "Fonts"]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                 Path("/System/Library/Fonts/Supplemental"),
                 Path.home() / "Library" / "Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                 Path.home() / ".fonts", Path.home() / ".local/share/fonts"]
    return [d for d in dirs if d.exists()]


def _index():
    """Имя файла (в нижнем регистре) → полный путь, по системным папкам."""
    global _font_index
    if _font_index is None:
        idx = {}
        for d in _font_dirs():
            try:
                for root, _dirs, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith((".ttf", ".otf", ".ttc")):
                            idx.setdefault(f.lower(), os.path.join(root, f))
            except Exception:
                continue
        _font_index = idx
    return _font_index


def _resolve(family, style_idx):
    """Путь к файлу шрифта; style_idx: 0 обычный, 1 жирный, 2 курсив, 3 жирный курсив."""
    spec = FONT_FAMILIES.get(family) or FONT_FAMILIES[DEFAULT_FONT]
    idx = _index()
    for name in spec[style_idx]:
        path = idx.get(name.lower())
        if path:
            return path
    return None


def available_fonts():
    """Семейства, реально установленные в системе (без дублей файлов)."""
    out, seen = [], set()
    for fam in FONT_FAMILIES:
        path = _resolve(fam, 0)
        if path and path not in seen:
            seen.add(path)
            out.append(fam)
    return out or [DEFAULT_FONT]


_fonts = {}


def load_font(size, family=DEFAULT_FONT, bold=False, italic=False):
    key = (int(size), family, bool(bold), bool(italic))
    f = _fonts.get(key)
    if f is not None:
        return f
    style = (1 if bold else 0) + (2 if italic else 0)
    # если нужного начертания нет — мягко откатываемся к более простому
    order = [style] + [s for s in (1 if bold else 0, 2 if italic else 0, 0)
                       if s != style]
    font = None
    for fam in (family, DEFAULT_FONT):
        for st in order:
            path = _resolve(fam, st)
            if path:
                try:
                    font = ImageFont.truetype(path, int(size))
                    break
                except Exception:
                    font = None
        if font:
            break
    if font is None:
        for name in ("arial.ttf", "DejaVuSans.ttf"):
            try:
                font = ImageFont.truetype(name, int(size))
                break
            except Exception:
                continue
    if font is None:
        try:
            font = ImageFont.load_default(int(size))
        except TypeError:
            font = ImageFont.load_default()
    _fonts[key] = font
    return font


def _load_font(size):
    """Совместимость: шрифт подписи по умолчанию (используется редактором)."""
    return load_font(size)


# ------------------------------------------------------------------ утилиты
def _hex_to_rgb(h):
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0, 0, 0


def _luma(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _wrap_text(text, font, max_width):
    """Переносит текст по пробелам так, чтобы строка влезала в max_width.

    Явные переносы строк (Enter/«\\n») сохраняются. Слово шире строки
    остаётся целым (резать по буквам некрасиво).
    """
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = []
    for para in str(text).replace("\r", "").split("\n"):
        words = para.split()
        if not words:
            continue
        current = ""
        for w in words:
            candidate = (current + " " + w) if current else w
            if tmp.textlength(candidate, font=font) <= max_width:
                current = candidate
            elif current:
                lines.append(current)
                current = w
            else:
                lines.append(w)
                current = ""
        if current:
            lines.append(current)
    return lines


def _ellipsize(draw, line, font, max_width):
    test = line
    while test:
        cand = test.rstrip() + "…"
        if draw.textlength(cand, font=font) <= max_width:
            return cand
        test = test[:-1]
    return "…"


# ------------------------------------------------------------------ рисование
def draw_caption(cell_img, text, config, cell_size, for_preview=False):
    """Рисует подпись на квадратной ячейке и возвращает RGB-изображение."""
    s = caption_settings(config)
    style = s["caption_style"]
    font_size = max(9, int(cell_size * s["caption_size_ratio"]))
    font = load_font(font_size, s["caption_font"],
                     s["caption_bold"], s["caption_italic"])

    pad_x = max(6, int(cell_size * 0.03))
    pad_y = max(4, int(cell_size * 0.02))
    edge = max(4, int(cell_size * 0.025))          # отступ капсулы/контура от края
    if style == "pill":
        max_w = int(cell_size * 0.86) - pad_x * 2
    else:
        max_w = cell_size - pad_x * 2

    lines = _wrap_text(text, font, max_w)
    if not lines:
        return cell_img

    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_lines = s["caption_max_lines"]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(probe, lines[-1], font, max_w)

    try:
        asc, desc = font.getmetrics()
    except Exception:
        asc, desc = font_size, int(font_size * 0.25)
    line_h = asc + desc
    spacing = max(1, int(font_size * 0.16))
    widths = [probe.textlength(ln, font=font) for ln in lines]
    block_w = int(max(widths))
    block_h = line_h * len(lines) + spacing * (len(lines) - 1)

    bg_rgb = _hex_to_rgb(s["caption_bg_color"])
    text_rgb = _hex_to_rgb(s["caption_color"])
    opacity = s["caption_bg_opacity"]
    top = s["caption_position"] == "top"

    overlay = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # --- геометрия блока с текстом
    if style == "bar":
        box_h = block_h + pad_y * 2
        y0 = 0 if top else cell_size - box_h
        d.rectangle([0, y0, cell_size, y0 + box_h], fill=(*bg_rgb, opacity))
        left, right = pad_x, cell_size - pad_x
        text_y = y0 + pad_y
    elif style == "pill":
        px, py = int(pad_x * 1.3), int(pad_y * 1.2)
        box_w, box_h = block_w + px * 2, block_h + py * 2
        x0 = (cell_size - box_w) // 2
        y0 = edge if top else cell_size - box_h - edge
        d.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h],
                            radius=min(box_h // 2, int(font_size * 1.0)),
                            fill=(*bg_rgb, opacity))
        left, right = x0 + px, x0 + box_w - px
        text_y = y0 + py
    else:  # outline — без подложки
        y0 = edge if top else cell_size - block_h - edge
        left, right = pad_x, cell_size - pad_x
        text_y = y0

    # --- текст построчно
    stroke = 0
    stroke_fill = None
    if style == "outline":
        stroke = max(1, font_size // 12)
        dark_text = _luma(text_rgb) < 110
        stroke_fill = (255, 255, 255, 235) if dark_text else (0, 0, 0, 235)
    shadow_off = max(1, font_size // 22)

    y = text_y
    for ln, w in zip(lines, widths):
        if s["caption_align"] == "left":
            x = left
        elif s["caption_align"] == "right":
            x = right - w
        else:
            x = left + (right - left - w) / 2
        if style != "outline" and s["caption_shadow"]:
            _text(d, (x + shadow_off, y + shadow_off), ln, font, (0, 0, 0, 120))
        _text(d, (x, y), ln, font, (*text_rgb, 255), stroke, stroke_fill)
        y += line_h + spacing

    if cell_img.mode != "RGBA":
        cell_img = cell_img.convert("RGBA")
    return Image.alpha_composite(cell_img, overlay).convert("RGB")


def _text(draw, xy, text, font, fill, stroke=0, stroke_fill=None):
    kw = {"font": font, "fill": fill}
    if stroke:
        kw.update(stroke_width=stroke, stroke_fill=stroke_fill)
    try:
        draw.text(xy, text, anchor="la", **kw)      # одинаковая высота строк
    except (ValueError, TypeError):                 # растровый шрифт без anchor
        draw.text(xy, text, **kw)
