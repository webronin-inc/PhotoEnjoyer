"""Пересобирает icon.ico из неонового логотипа (icons.logo_pil).

    python tools/make_icon.py

Файл кладётся и в корень (его берёт PyInstaller/Inno Setup), и в photogrid/
(иконка окна во время работы).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from photogrid import icons  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    # плитка ~76 % холста: по краям остаётся место под свечение
    logo = icons.logo_pil(size=300, accent="#7c6cff")
    side = max(logo.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2), logo)
    big = canvas.resize((256, 256), Image.LANCZOS)
    for target in (ROOT / "icon.ico", ROOT / "photogrid" / "icon.ico"):
        big.save(target, format="ICO", sizes=[(s, s) for s in SIZES])
        print("записано:", target.relative_to(ROOT))
    big.save(ROOT / "tools" / "icon_preview.png")


if __name__ == "__main__":
    main()
