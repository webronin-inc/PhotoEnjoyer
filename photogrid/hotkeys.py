"""Горячие клавиши, не зависящие от раскладки клавиатуры.

Tk сопоставляет сочетания по keysym, а с русской раскладкой Ctrl+S приходит
как «Ctrl + Cyrillic_yeru» — и привязка ``<Control-s>`` не срабатывает.
Поэтому один глобальный обработчик ловит Ctrl+клавиша, определяет, какую
латинскую клавишу пользователь на самом деле нажал (по коду клавиши на
Windows, по таблице ЙЦУКЕН на остальных системах) и пересылает в то же окно
обычное латинское событие. Все существующие привязки (``<Control-s>``,
``<Control-Shift-C>``, стандартные Ctrl+C/V/X в полях ввода) работают как есть.
"""
import sys

# ЙЦУКЕН → QWERTY по keysym и по символу (на случай, когда keysym неинформативен)
_KEYSYM_TO_LATIN = {
    "cyrillic_shorti": "q", "cyrillic_tse": "w", "cyrillic_u": "e",
    "cyrillic_ka": "r", "cyrillic_ie": "t", "cyrillic_en": "y",
    "cyrillic_ghe": "u", "cyrillic_sha": "i", "cyrillic_shcha": "o",
    "cyrillic_ze": "p", "cyrillic_ha": "bracketleft",
    "cyrillic_hardsign": "bracketright",
    "cyrillic_ef": "a", "cyrillic_yeru": "s", "cyrillic_ve": "d",
    "cyrillic_a": "f", "cyrillic_pe": "g", "cyrillic_er": "h",
    "cyrillic_o": "j", "cyrillic_el": "k", "cyrillic_de": "l",
    "cyrillic_zhe": "semicolon", "cyrillic_e": "apostrophe",
    "cyrillic_ya": "z", "cyrillic_che": "x", "cyrillic_es": "c",
    "cyrillic_em": "v", "cyrillic_i": "b", "cyrillic_te": "n",
    "cyrillic_softsign": "m", "cyrillic_be": "comma", "cyrillic_yu": "period",
    "cyrillic_io": "grave",
}
_CHAR_TO_LATIN = {c: v for c, v in zip(
    "йцукенгшщзхъфывапролджэячсмитьбюё",
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "bracketleft",
     "bracketright", "a", "s", "d", "f", "g", "h", "j", "k", "l", "semicolon",
     "apostrophe", "z", "x", "c", "v", "b", "n", "m", "comma", "period",
     "grave"])}

# Windows: код клавиши (VK) не зависит от раскладки
_VK_PUNCT = {186: "semicolon", 188: "comma", 190: "period", 191: "slash",
             192: "grave", 219: "bracketleft", 221: "bracketright",
             222: "apostrophe", 189: "minus", 187: "equal", 220: "backslash"}

_SHIFT = 0x0001
_ALT_WIN = 0x20000          # Alt (и AltGr = Ctrl+Alt) на Windows
_ALT_X11 = 0x0008


_FOREIGN_PREFIXES = ("cyrillic", "ukrainian", "serbian", "macedonia", "byelorussian",
                     "greek", "hebrew", "arabic", "thai", "armenian", "georgian",
                     "kana", "hangul", "farsi")


def _is_foreign(keysym):
    """keysym не латинский: «Cyrillic_es», «Greek_sigma», «??» (Tk не распознал)."""
    ks = str(keysym or "")
    if ks in ("", "??") or not ks.isascii():
        return True
    return ks.split("_", 1)[0].lower() in _FOREIGN_PREFIXES


def latin_for(keysym, keycode=0, char="", platform=None):
    """Латинский keysym клавиши или None, если перевод не нужен/невозможен.

    None возвращается и для обычных латинских клавиш — их трогать не надо.
    """
    platform = platform or sys.platform
    ks = str(keysym or "")
    if len(ks) == 1 and ks.isascii():
        return None                       # уже латиница (или цифра/знак)
    if not _is_foreign(ks):
        return None                       # Delete, F5, comma, Return, …
    if platform == "win32":               # код клавиши не зависит от раскладки
        if 65 <= keycode <= 90:
            return chr(keycode).lower()
        if keycode in _VK_PUNCT:
            return _VK_PUNCT[keycode]
    got = _KEYSYM_TO_LATIN.get(ks.lower())
    if got:
        return got
    return _CHAR_TO_LATIN.get(str(char or "").lower())


def install(root):
    """Включает перевод Ctrl+<кириллица> → Ctrl+<латиница> для всего приложения."""
    if getattr(root, "_hotkeys_installed", False):
        return
    root._hotkeys_installed = True

    def handler(event):
        state = int(event.state)
        if state & (_ALT_WIN if sys.platform == "win32" else _ALT_X11):
            return None                   # AltGr/Alt — не наши сочетания
        lat = latin_for(event.keysym, getattr(event, "keycode", 0),
                        getattr(event, "char", ""))
        if lat is None:
            return None
        # С Shift Tk присылает заглавный keysym (<Control-S>, <Control-Shift-C>)
        if len(lat) == 1 and state & _SHIFT:
            lat = lat.upper()
        target = event.widget
        try:
            target.event_generate("<KeyPress>", keysym=lat, state=state)
        except Exception:
            return None
        return "break"

    root._hotkey_handler = handler        # для тестов
    root.bind_all("<Control-KeyPress>", handler, add="+")
