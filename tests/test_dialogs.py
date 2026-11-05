"""Диалоги: окна обязаны открываться нормального размера и быть видимыми.

Регрессия 0.0.0.21: эффект плавного появления выставлял окну размер 1×1 —
настройки «зависали» (модальное окно-точка держало блокировку), а все
диалоги админки были неработоспособны."""
import time
import tkinter as tk
from pathlib import Path

import pytest

from photogrid import anim, fx


def pump(root, sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.005)


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("нет дисплея для Tk")
    anim.set_level("full")
    yield r
    r.destroy()


def test_dialog_in_never_changes_window_size(root):
    for geom in ("400x300", "520x260+30+40", None):
        top = fx.toplevel(root)
        tk.Label(top, text="x" * 40, width=60, height=12).pack()
        if geom:
            top.geometry(geom)
        pump(root, 0.8)
        top.update_idletasks()
        assert top.winfo_width() >= 250 and top.winfo_height() >= 150, (geom, top.geometry())
        assert float(top.attributes("-alpha")) > 0.99
        top.destroy()


def test_unhide_safety_net_restores_alpha(root):
    top = fx.toplevel(root)
    top.attributes("-alpha", 0.0)          # «анимация сломалась»
    fx._unhide(top)
    assert float(top.attributes("-alpha")) == 1.0
    top.destroy()


def test_effects_off_leaves_window_fully_visible(root):
    anim.set_level("off")
    top = fx.toplevel(root)
    pump(root, 0.3)
    assert float(top.attributes("-alpha")) == 1.0
    top.destroy()


# ------------------------------------------------------------ окна приложения
@pytest.fixture(scope="module")
def app(tmp_path_factory):
    if tk.TkVersion >= 9.0:
        pytest.skip("tkinterdnd2 не поддерживает Tk 9")
    home = tmp_path_factory.mktemp("home")
    mp = pytest.MonkeyPatch()
    mp.setattr(Path, "home", classmethod(lambda cls: home))
    try:
        from tkinterdnd2 import TkinterDnD
        r = TkinterDnD.Tk()
    except Exception:
        mp.undo()
        pytest.skip("нет дисплея/tkinterdnd2")
    r.geometry("1316x872+0+0")
    from photogrid.app import App
    a = App(r)
    pump(r, 0.4)
    yield a
    anim.set_level("full")
    try:
        r.destroy()
    finally:
        mp.undo()


def _toplevels(root):
    return [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]


def _check_dialog(app, opener, name, min_w=250, min_h=100):
    before = set(_toplevels(app.root))
    opener()
    pump(app.root, 0.9)
    new = [w for w in _toplevels(app.root) if w not in before]
    assert new, f"{name}: окно не появилось"
    top = new[-1]
    top.update_idletasks()
    assert top.winfo_viewable(), f"{name}: окно не показано"
    assert top.winfo_width() >= min_w and top.winfo_height() >= min_h, \
        f"{name}: размер {top.geometry()}"
    assert float(top.attributes("-alpha")) > 0.99, f"{name}: окно прозрачное"
    return top


def test_settings_dialog_has_real_size_and_does_not_block_forever(app):
    top = _check_dialog(app, app.show_settings, "Настройки", 400, 400)
    assert app.root.grab_current() is not None        # модальное — но видимое и нормального размера
    top.destroy()
    pump(app.root, 0.2)
    assert app.root.grab_current() is None            # после закрытия блокировка снята


def test_settings_build_failure_never_leaves_invisible_blocker(app, monkeypatch):
    from photogrid.screens import settings

    def boom(self):
        raise RuntimeError("тест")
    monkeypatch.setattr(settings.SettingsDialog, "_build", boom)
    before = set(_toplevels(app.root))
    with pytest.raises(RuntimeError):
        settings.SettingsDialog(app)
    pump(app.root, 0.2)
    assert set(_toplevels(app.root)) == before and app.root.grab_current() is None


def test_info_and_helper_dialogs_have_real_size(app):
    from photogrid.screens import about, dialogs
    cases = [
        ("О программе", lambda: about.show_about(app)),
        ("Горячие клавиши", lambda: about.show_hotkeys(app)),
        ("ask", lambda: dialogs.ask(app, "Заголовок", [("a", "Поле", "", False)], lambda v: None)),
        ("confirm", lambda: dialogs.confirm(app, "Точно?", "Описание действия", lambda: None)),
        ("show_text", lambda: dialogs.show_text(app, "Ключи", "PE-AAAA-BBBB-CCCC\nPE-DDDD-EEEE-FFFF")),
    ]
    for name, fn in cases:
        _check_dialog(app, fn, name).destroy()


def test_plugin_dialogs_have_real_size(app):
    from photogrid.plugins import captions, updater_ui
    _check_dialog(app, lambda: captions.open_dialog(app), "Подписи", 400, 300).destroy()
    info = {"available": True, "current": "0.0.0.20", "remote": "9.9.9.9", "release_date": "2026-11-02",
            "notes": "Тест", "plugins": [], "download_url": "", "sha256": "", "homepage": ""}
    _check_dialog(app, lambda: updater_ui._UpdateDialog(app, info), "Обновление", 600, 500).destroy()
    # остальные плагины открываются через зарегистрированные действия меню
    wanted = ("Водяной знак", "Пакетная обработка")
    for group in app.plugin_actions.values():
        for act in group:
            if any(w in act["label"] for w in wanted):
                _check_dialog(app, act["command"], act["label"], 250, 150).destroy()
