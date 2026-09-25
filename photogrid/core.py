"""Логика сборки коллажа. Не зависит от UI."""
from PIL import Image
from .config import LAYOUTS


def load_rgb(path, bg):
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, bg)
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert("RGB")


def center_crop_resize(img, w, h):
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h = img.height
        new_w = max(1, int(new_h * dst_ratio))
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, new_h))
    else:
        new_w = img.width
        new_h = max(1, int(new_w / dst_ratio))
        top = (img.height - new_h) // 2
        img = img.crop((0, top, new_w, top + new_h))
    return img.resize((w, h), Image.LANCZOS)


def build_collage(photos, config, for_preview=False, captions=None):
    """Собирает коллаж из N фото по раскладке.

    photos   — список путей (или None). Количество ячеек определяется раскладкой.
    captions — список подписей (по одной на слот), либо None.
    """
    cols, rows = LAYOUTS[config["layout"]]
    total_cells = cols * rows

    real_cell = max(50, int(config["cell_size"]))
    real_border = max(0, int(config["border"]))

    if for_preview:
        cell = 220
        border = int(round(real_border * cell / real_cell)) if real_cell else 0
    else:
        cell = real_cell
        border = real_border

    border_color = config["border_color"]
    bg_color = config["bg_color"]
    mode = config["mode"]

    total_w = cols * cell + (cols + 1) * border
    total_h = rows * cell + (rows + 1) * border
    canvas = Image.new("RGB", (total_w, total_h), border_color)

    for i in range(total_cells):
        path = photos[i] if i < len(photos) else None
        col = i % cols
        row = i // cols
        x0 = border + col * (cell + border)
        y0 = border + row * (cell + border)

        # ---- формируем ячейку ----
        if path is None:
            cell_img = Image.new("RGB", (cell, cell), "#cccccc")
        else:
            img = load_rgb(path, bg_color)
            if mode == "fill":
                img = center_crop_resize(img, cell, cell)
                cell_img = img
            else:  # fit
                img.thumbnail((cell, cell), Image.LANCZOS)
                cell_img = Image.new("RGB", (cell, cell), bg_color)
                cell_img.paste(img, ((cell - img.width) // 2,
                                     (cell - img.height) // 2))

        # ---- рисуем подпись, если есть ----
        caption_text = ""
        if captions and i < len(captions) and captions[i]:
            caption_text = captions[i].strip()

        if caption_text:
            cell_img = _draw_caption(cell_img, caption_text, config, cell,
                                     for_preview=for_preview)

        canvas.paste(cell_img, (x0, y0))

    return canvas


# ==============================================================
#  ПОДПИСИ ПОД ФОТО
# ==============================================================
def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_font_cache = {}


def _load_font(size):
    """Подбирает системный шрифт для подписи."""
    if size in _font_cache:
        return _font_cache[size]
    from PIL import ImageFont
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
    ]
    for name in candidates:
        try:
            font = ImageFont.truetype(name, size)
            _font_cache[size] = font
            return font
        except Exception:
            continue
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _draw_caption(cell_img, text, config, cell_size, for_preview=False):
    """Рисует подпись внизу ячейки на полупрозрачной плашке."""
    from PIL import ImageDraw

    # параметры из config с разумными умолчаниями
    size_ratio   = float(config.get("caption_size_ratio", 0.055))
    bg_color     = config.get("caption_bg_color", "#000000")
    bg_opacity   = int(config.get("caption_bg_opacity", 150))
    text_color   = config.get("caption_color", "#ffffff")
    position     = config.get("caption_position", "bottom")  # bottom | top

    # Уменьшаем параметры в превью, чтобы пропорции были как в финале
    if for_preview:
        size_ratio = size_ratio
        bg_opacity = bg_opacity

    font_size = max(8, int(cell_size * size_ratio))
    font = _load_font(font_size)

    # временный draw для измерения текста
    temp_overlay = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_overlay)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    padding_x = max(4, int(cell_size * 0.025))
    padding_y = max(3, int(cell_size * 0.015))
    cap_h = th + padding_y * 2

    if position == "top":
        cap_y = 0
    else:
        cap_y = cell_size - cap_h

    # плашка
    bg_rgb = _hex_to_rgb(bg_color)
    overlay = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([0, cap_y, cell_size, cap_y + cap_h],
                   fill=(*bg_rgb, bg_opacity))

    # текст по центру
    tx = (cell_size - tw) // 2 - bbox[0]
    ty = cap_y + (cap_h - th) // 2 - bbox[1]
    text_rgb = _hex_to_rgb(text_color)
    draw.text((tx, ty), text, font=font, fill=(*text_rgb, 255))

    # композит
    if cell_img.mode != "RGBA":
        cell_img = cell_img.convert("RGBA")
    cell_img = Image.alpha_composite(cell_img, overlay)
    return cell_img.convert("RGB")