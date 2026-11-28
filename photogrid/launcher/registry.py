"""Список модулей меню. Новый модуль добавляется одной записью."""
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    id: str
    title: str
    subtitle: str
    icon: str
    hue: str                       # ключ из icons.NEON
    windows_only: bool = False

    @property
    def available(self):
        return (sys.platform == "win32") or not self.windows_only


MODULES = (
    Module("photo", "Фото", "Коллажи из фотографий: шаблоны, редактор, подписи, библиотека",
           "collage", "violet"),
    Module("word", "Word", "Проверка и установка Microsoft Word 2021, затем запуск",
           "word", "blue", windows_only=True),
)


def by_id(module_id):
    return next((m for m in MODULES if m.id == module_id), None)
