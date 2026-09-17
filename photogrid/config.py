"""Настройки, константы и их сохранение на диск."""
import json
from pathlib import Path
from . import branding 

DEFAULTS = {
    "layout": "2×2 — квадрат",
    "mode": "fit",                  # fit | fill
    "cell_size": 800,
    "border": 10,
    "border_color": "#ffffff",
    "bg_color": "#ffffff",
    "quality": 92,
    "theme": "dark",                # dark | light
}

LAYOUTS = {
    "2×2 — квадрат":               (2, 2),
    "4×1 — горизонтальная полоса": (4, 1),
    "1×4 — вертикальная полоса":   (1, 4),
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".gif"}


class Config:
    """Обёртка над JSON-файлом с настройками в домашней папке пользователя."""

    def __init__(self):
        self.path = Path.home() / f"{branding.APP_CONFIG_DIR}.json"
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if self.path.exists():
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                for k in DEFAULTS:
                    if k in saved:
                        self.data[k] = saved[k]
                if self.data["layout"] not in LAYOUTS:
                    self.data["layout"] = DEFAULTS["layout"]
        except Exception:
            pass

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)