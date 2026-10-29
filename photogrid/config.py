"""Настройки, константы и их сохранение на диск."""
import json
import os
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
    "animations": True,             # анимации интерфейса (старый флаг)
    "anim_level": "full",           # full | soft | off
}

LAYOUTS = {
    # 1 ячейка
    "1×1 — одно фото":             (1, 1),
    # 2 ячейки
    "1×2 — рядом":                 (2, 1),
    "2×1 — друг над другом":       (1, 2),
    # 3 ячейки
    "3×1 — три рядом":             (3, 1),
    "1×3 — три в столбик":         (1, 3),
    # 4 ячейки
    "2×2 — квадрат":               (2, 2),
    "4×1 — горизонтальная полоса": (4, 1),
    "1×4 — вертикальная полоса":   (1, 4),
    # 6 ячеек
    "3×2 — шесть":                 (3, 2),
    "2×3 — шесть вертикально":     (2, 3),
    # 9 ячеек
    "3×3 — сетка":                 (3, 3),
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".gif"}


def layout_cells(layout_name):
    """Сколько фото нужно для раскладки (для неизвестной — как у 2×2)."""
    cols, rows = LAYOUTS.get(layout_name, (2, 2))
    return cols * rows


class Config:
    """Обёртка над JSON-файлом с настройками в домашней папке пользователя."""

    def __init__(self):
        self.path = Path.home() / f"{branding.APP_CONFIG_DIR}.json"
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if not self.path.exists():
                return
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(saved, dict):
            return
        saved_keys = set(saved)

        # Раньше подхватывались только ключи из DEFAULTS, из-за чего
        # настройки плагинов (watermark, updates…) терялись при перезапуске.
        for k, v in saved.items():
            if k in DEFAULTS:
                # тип значения должен совпадать с типом по умолчанию
                # (bool — подкласс int, поэтому сравниваем его отдельно)
                d = DEFAULTS[k]
                if isinstance(d, bool):
                    if isinstance(v, bool):
                        self.data[k] = v
                elif isinstance(v, bool):
                    continue
                elif isinstance(v, type(d)):
                    self.data[k] = v
                elif isinstance(d, float) and isinstance(v, int):
                    self.data[k] = v
            else:
                self.data[k] = v

        if self.data["layout"] not in LAYOUTS:
            self.data["layout"] = DEFAULTS["layout"]
        if self.data["mode"] not in ("fit", "fill"):
            self.data["mode"] = DEFAULTS["mode"]
        if self.data["theme"] not in ("dark", "light"):
            self.data["theme"] = DEFAULTS["theme"]
        if self.data.get("anim_level") not in ("full", "soft", "off"):
            self.data["anim_level"] = "full"
        # миграция: раньше был только флажок «анимации» — выключенный = off
        if "anim_level" not in saved_keys and not self.data.get("animations", True):
            self.data["anim_level"] = "off"

    def save(self):
        try:
            # пишем во временный файл и подменяем — чтобы сбой посреди записи
            # не оставил битый JSON
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except Exception:
            pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)