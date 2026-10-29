"""Горячие клавиши на любой раскладке."""
import tkinter as tk
from types import SimpleNamespace

import pytest

from photogrid import hotkeys


@pytest.mark.parametrize("keysym,keycode,expect", [
    ("Cyrillic_yeru", 83, "s"),        # Ctrl+Ы → Ctrl+S
    ("Cyrillic_YERU", 83, "s"),        # с Caps Lock / Shift
    ("Cyrillic_es", 67, "c"),
    ("Cyrillic_em", 86, "v"),
    ("Cyrillic_ef", 65, "a"),
    ("Cyrillic_ya", 90, "z"),
    ("Cyrillic_en", 89, "y"),
    ("Cyrillic_u", 69, "e"),
    ("Cyrillic_shcha", 79, "o"),
    ("Cyrillic_be", 188, "comma"),     # Ctrl+Б → Ctrl+,
])
def test_cyrillic_keys_map_to_latin_on_windows(keysym, keycode, expect):
    assert hotkeys.latin_for(keysym, keycode, platform="win32") == expect


@pytest.mark.parametrize("keysym,expect", [
    ("Cyrillic_yeru", "s"), ("Cyrillic_es", "c"), ("Cyrillic_be", "comma"),
    ("Cyrillic_zhe", "semicolon"),
])
def test_table_fallback_for_other_platforms(keysym, expect):
    assert hotkeys.latin_for(keysym, 0, platform="linux") == expect


def test_char_fallback_when_keysym_is_uninformative():
    assert hotkeys.latin_for("Cyrillic_unknown", 0, "ы", platform="linux") == "s"
    assert hotkeys.latin_for("??", 0, "ы", platform="linux") == "s"


def test_windows_unknown_keysym_uses_virtual_key_code():
    # Tk на Windows с Ctrl иногда отдаёт «??» — тогда решает код клавиши
    assert hotkeys.latin_for("??", 83, platform="win32") == "s"
    assert hotkeys.latin_for("Greek_sigma", 83, platform="win32") == "s"
    assert hotkeys.latin_for("??", 190, platform="win32") == "period"


def test_other_latin_layouts_are_not_remapped():
    # QWERTZ/AZERTY: keysym уже латинский — код клавиши игнорируем
    assert hotkeys.latin_for("z", 89, platform="win32") is None
    assert hotkeys.latin_for("comma", 188, platform="win32") is None


@pytest.mark.parametrize("keysym", ["s", "S", "comma", "Delete", "F5", "Return",
                                    "1", "Escape"])
def test_latin_and_special_keys_are_left_alone(keysym):
    assert hotkeys.latin_for(keysym, 83, platform="win32") is None


def test_windows_vk_wins_over_keysym():
    # любая кириллическая клавиша на VK 'S' — это Ctrl+S
    assert hotkeys.latin_for("Cyrillic_yeru", 83, platform="win32") == "s"


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("нет дисплея для Tk")
    hotkeys.install(r)
    yield r
    r.destroy()


def _press(root, widget, keysym, keycode, state=4):
    ev = SimpleNamespace(keysym=keysym, keycode=keycode, char="", state=state,
                         widget=widget)
    return root._hotkey_handler(ev)


def test_cyrillic_ctrl_triggers_existing_latin_binding(root):
    hits = []
    root.bind("<Control-s>", lambda e: hits.append("s"))
    root.bind("<Control-S>", lambda e: hits.append("S"))
    root.update()
    root.focus_force(); root.update()
    import sys
    keycode = 83 if sys.platform == "win32" else 0
    r = _press(root, root, "Cyrillic_yeru", keycode)
    root.update()
    assert r == "break" and hits == ["s"]
    r = _press(root, root, "Cyrillic_YERU", keycode, state=4 | 1)   # +Shift
    root.update()
    assert hits == ["s", "S"]


def test_ctrl_v_in_entry_works_on_russian_layout(root):
    ent = tk.Entry(root); ent.pack(); root.update(); ent.focus_force(); root.update()
    got = []
    ent.bind("<<Paste>>", lambda e: got.append(1))
    import sys
    _press(root, ent, "Cyrillic_em", 86 if sys.platform == "win32" else 0)
    root.update()
    assert got, "Ctrl+М должен вызывать вставку"


def test_altgr_and_latin_are_not_translated(root):
    alt = 0x20000 if __import__("sys").platform == "win32" else 0x8
    assert _press(root, root, "Cyrillic_yeru", 83, state=4 | alt) is None
    assert _press(root, root, "s", 83) is None


def test_install_is_idempotent(root):
    first = root._hotkey_handler
    hotkeys.install(root)
    assert root._hotkey_handler is first
