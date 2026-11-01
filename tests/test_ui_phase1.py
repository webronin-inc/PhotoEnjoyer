"""Интерфейс: боковая панель, разделы, меню, «О программе», анимации."""
import tkinter as tk
from pathlib import Path

import pytest

from photogrid import anim, icons


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    if tk.TkVersion >= 9.0:
        # tkdnd (перетаскивание файлов) собран под Tk 8.6 — на Tk 9 повторная
        # инициализация обрывает процесс; в поставке программы Tk 8.6
        pytest.skip("tkinterdnd2 не поддерживает Tk 9")
    home = tmp_path_factory.mktemp("home")
    mp = pytest.MonkeyPatch()
    mp.setattr(Path, "home", classmethod(lambda cls: home))
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        mp.undo()
        pytest.skip("нет дисплея/tkinterdnd2")
    from photogrid.app import App
    root.geometry("1316x872+0+0")
    a = App(root)
    pump(root, 0.3)
    yield a
    anim.set_level("full")
    try:
        root.destroy()
    finally:
        mp.undo()


def pump(root, sec=0.2):
    import time
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.005)


def test_rail_has_all_sections_and_neon_hues(app):
    for key in ("collage", "templates", "batch", "cloud", "editor", "tools",
                "plugins", "theme", "settings", "help"):
        assert key in app.rail_buttons, key
    assert app.rail_buttons["templates"].hue == icons.NEON["pink"]


@pytest.mark.parametrize("section", ["templates", "batch", "cloud", "plugins", "collage"])
def test_every_section_opens(app, section):
    app._set_section(section)
    pump(app.root, 0.25)
    assert app.active_section == section
    assert section in app.views or section == "collage"


def test_actions_do_not_become_active_sections(app):
    app._set_section("collage")
    app._set_section("tools")           # меню, а не раздел
    pump(app.root, 0.2)
    from photogrid import popup
    assert popup._current is not None
    popup.close_current()
    assert app.active_section == "collage"


def test_tools_menu_is_built_from_plugin_actions_without_templates(app):
    from photogrid import popup
    app._open_tools_menu()
    pump(app.root, 0.2)
    labels = [r[2]["label"] for r in popup._current._rows]
    popup.close_current()
    assert any("Подписи" in l for l in labels)
    assert not any("шаблон" in l.lower() for l in labels)


def test_slot_context_menu_opens(app):
    from photogrid import popup

    class E:
        x_root, y_root = 400, 300
    app.on_slot_context_menu(E, 0)
    pump(app.root, 0.2)
    assert popup._current is not None
    popup.close_current()


def test_about_and_hotkeys_dialogs_build(app):
    from photogrid.screens import about
    for fn in (about.show_about, about.show_hotkeys):
        top = fn(app)
        pump(app.root, 0.3)
        assert top.winfo_exists()
        top.destroy()


def test_hotkeys_table_has_no_duplicates():
    from photogrid.screens import about
    keys = [k for _, rows in about.HOTKEYS for k, _ in rows]
    assert len(keys) == len(set(keys))


def test_animation_levels_change_behaviour(app):
    anim.set_level("off")
    assert not anim.is_enabled() and not anim.effects_enabled()
    done = []
    anim.get(app.root).animate(300, lambda t: None, on_done=lambda: done.append(1))
    assert done == [1]                  # без анимаций завершается сразу
    anim.set_level("soft")
    assert anim.is_enabled() and not anim.effects_enabled()
    anim.set_level("full")
    assert anim.effects_enabled()


def test_config_migrates_old_animations_flag(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    from photogrid import branding
    from photogrid.config import Config
    (tmp_path / f"{branding.APP_CONFIG_DIR}.json").write_text(
        json.dumps({"animations": False}), encoding="utf-8")
    assert Config().data["anim_level"] == "off"
    (tmp_path / f"{branding.APP_CONFIG_DIR}.json").write_text(
        json.dumps({"animations": True, "anim_level": "bogus"}), encoding="utf-8")
    assert Config().data["anim_level"] == "full"


def test_segmented_thumb_reaches_target_and_stays_in_track(app):
    from photogrid.ui_widgets import SegmentedControl
    var = tk.StringVar(value="a")
    seg = SegmentedControl(app.root, app.palette,
                           [("a", "Раз"), ("b", "Два"), ("c", "Три")], variable=var)
    seg.pack()
    pump(app.root, 0.1)
    var.set("c")
    pump(app.root, 0.5)
    x0, x1, _, _ = seg._cells["c"]
    assert abs(seg._tx - x0) < 0.6 and abs(seg._tw - (x1 - x0)) < 0.6
    seg.destroy()


def test_gradient_button_ripple_and_burst_finish_cleanly(app):
    from photogrid.ui_widgets import GradientButton
    hits = []
    b = GradientButton(app.root, app.palette, text="Тест", icon="save",
                       height=40, command=lambda: hits.append(1))
    b.pack()
    pump(app.root, 0.1)
    b.event_generate("<ButtonPress-1>", x=20, y=10)
    pump(app.root, 0.15)
    assert b._ripple is not None or not anim.effects_enabled()
    b.event_generate("<ButtonRelease-1>", x=20, y=10)
    b.burst()
    pump(app.root, 1.0)
    assert b._ripple is None and b._burst_t is None and hits == [1]
    b.destroy()


def test_status_counters_count_up(app):
    bar = app.status_bar
    bar.set_metrics([("отмены", 0), ("плагины", 0)])
    pump(app.root, 0.3)
    bar.set_metrics([("отмены", 0), ("плагины", 40)])
    pump(app.root, 0.15)
    mid = bar._shown.get("плагины", 0)
    assert 0 < mid < 40, mid            # число «накручивается», а не прыгает
    pump(app.root, 1.2)
    assert bar._shown["плагины"] == 40


def test_rail_power_on_returns_to_rest(app):
    btn = app.rail_buttons["cloud"]
    btn.power_on(0)
    pump(app.root, 1.2)
    assert btn._boost == 0.0


def test_templates_screen_cards_follow_layout(app):
    from photogrid.screens.templates import BUILTIN, _TemplateCard
    app._set_section("templates")
    pump(app.root, 0.3)
    grid_cards = [w for w in _walk(app.views["templates"]) if isinstance(w, _TemplateCard)]
    assert len(grid_cards) >= len(BUILTIN)
    app._set_section("collage")


def _walk(w):
    yield w
    for c in w.winfo_children():
        yield from _walk(c)
