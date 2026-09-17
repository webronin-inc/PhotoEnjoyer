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


def build_collage(photos, config, for_preview=False):
    cols, rows = LAYOUTS[config["layout"]]
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

    for i, path in enumerate(photos):
        col = i % cols
        row = i // cols
        x0 = border + col * (cell + border)
        y0 = border + row * (cell + border)

        if path is None:
            canvas.paste(Image.new("RGB", (cell, cell), "#cccccc"), (x0, y0))
            continue

        img = load_rgb(path, bg_color)
        if mode == "fill":
            img = center_crop_resize(img, cell, cell)
            canvas.paste(img, (x0, y0))
        else:
            img.thumbnail((cell, cell), Image.LANCZOS)
            cell_img = Image.new("RGB", (cell, cell), bg_color)
            cell_img.paste(img, ((cell - img.width) // 2,
                                 (cell - img.height) // 2))
            canvas.paste(cell_img, (x0, y0))

    return canvas