"""Логика сборки коллажа. Не зависит от UI."""
from PIL import Image, ImageOps
from .config import LAYOUTS
from .caption_render import (  # noqa: F401  (часть имён — для совместимости)
    draw_caption, _hex_to_rgb, _load_font, _wrap_text,
)


def load_rgb(path, bg):
    """Открывает изображение как RGB.

    * учитывает EXIF-ориентацию (фото с телефона не «лежат на боку»);
    * прозрачность заливает цветом bg;
    * закрывает файл сразу (на Windows открытый файл нельзя удалить/перезаписать).
    """
    with Image.open(path) as im:
        im.load()
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if im.mode in ("RGBA", "LA", "PA") or (
                im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            background = Image.new("RGB", rgba.size, bg)
            background.paste(rgba, mask=rgba.split()[-1])
            return background
        return im.convert("RGB")


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
    cols, rows = LAYOUTS.get(config["layout"], (2, 2))
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
#  ПОДПИСИ ПОД ФОТО — см. caption_render.py
# ==============================================================
def _draw_caption(cell_img, text, config, cell_size, for_preview=False):
    return draw_caption(cell_img, text, config, cell_size, for_preview)
