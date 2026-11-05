"""Админка: настоящие нажатия кнопок → диалоги → результат на сервере."""
import time
import tkinter as tk

import pytest

from test_account_ui import (_make_app, _session, _walk, pump, pump_until,  # noqa: F401
                             world)
from photogrid.account import gate
from photogrid.account.api import ApiClient, ApiError
from photogrid.ui_widgets import GradientButton


def _toplevels(root):
    return [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]


def _admin_view(world):
    s = _session(world, admin=True)
    app = _make_app(world, s)
    app._set_section("admin")
    pump(world.root, 0.8)
    view = app.views["admin"]
    seg = [w for w in _walk(view) if hasattr(w, "_cells") and "overview" in w._cells][0]
    return app, view, seg


def _tab(world, seg, name, view):
    seg._choose(name)
    pump(world.root, 1.0)
    return [w for w in _walk(view) if w.winfo_class() == "Treeview" and w.winfo_ismapped()][0]


def _select(tree, username):
    for iid in tree.get_children():
        if tree.item(iid, "values")[0] == username:
            tree.selection_set(iid)
            tree.event_generate("<<TreeviewSelect>>")
            return
    raise AssertionError(f"{username} нет в таблице")


def _button(view, text):
    for w in _walk(view):
        if w.winfo_class() == "Button" and w.cget("text") == text and w.winfo_ismapped():
            return w
    raise AssertionError(f"нет кнопки «{text}»")


def _new_dialog(world, before):
    assert pump_until(world.root, lambda: [w for w in _toplevels(world.root) if w not in before], 4)
    top = [w for w in _toplevels(world.root) if w not in before][-1]
    pump(world.root, 0.6)                        # дождаться конца анимации появления
    top.update_idletasks()
    assert top.winfo_width() >= 200 and top.winfo_height() >= 100, top.geometry()
    return top


def _submit(top):
    for w in _walk(top):
        if isinstance(w, GradientButton):
            w._invoke()
            return
    raise AssertionError("в диалоге нет кнопки подтверждения")


def _fill(top, *values):
    from photogrid.screens.login import _NeonField
    fields = [w for w in _walk(top) if isinstance(w, _NeonField)]
    for f, v in zip(fields, values):
        f.var.set(v)


def _click_text(top, text):
    for w in _walk(top):
        if w.winfo_class() == "Button" and w.cget("text") == text:
            w.invoke()
            return
    raise AssertionError(f"нет кнопки «{text}»")


def _user(world, name):
    api = ApiClient(world.admin_api.base, app_version="1")
    gate.authenticate(api, "register", {"key": world.key(days=5), "username": name,
                                        "password": "password-1", "consent": True}, False)
    items = world.admin_api.admin("GET", "/users", query={"q": name})["items"]
    return [u for u in items if u["username"] == name][0]


def test_ban_and_unban_from_the_users_tab(world):
    _user(world, "anna")
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "users", view)
    _select(tree, "anna")
    before = set(_toplevels(world.root))
    _button(view, "Заблокировать / разблокировать").invoke()
    top = _new_dialog(world, before)
    _fill(top, "спам")
    _submit(top)
    assert pump_until(world.root, lambda: [u for u in world.admin_api.admin("GET", "/users")["items"]
                                           if u["username"] == "anna"][0]["banned"], 5)
    pump(world.root, 0.8)                         # таблица обновилась
    _select(tree, "anna")
    _button(view, "Заблокировать / разблокировать").invoke()      # теперь — разблокировка без диалога
    assert pump_until(world.root, lambda: not [u for u in world.admin_api.admin("GET", "/users")["items"]
                                               if u["username"] == "anna"][0]["banned"], 5)
    assert not world.errors, world.errors


def test_extend_devices_unlimited_revoke_reset_note_from_ui(world):
    u = _user(world, "boris")
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "users", view)

    def fresh():
        return [x for x in world.admin_api.admin("GET", "/users")["items"] if x["username"] == "boris"][0]

    # продлить на 10 дней
    _select(tree, "boris")
    exp0 = fresh()["expires"]
    before = set(_toplevels(world.root))
    _button(view, "Продлить…").invoke()
    top = _new_dialog(world, before)
    _fill(top, "10")
    _submit(top)
    assert pump_until(world.root, lambda: fresh()["expires"] == exp0 + 10 * 86400 or
                      abs(fresh()["expires"] - exp0 - 10 * 86400) < 5, 5)
    # неверное число — диалог остаётся с сообщением, на сервер ничего не уходит
    pump(world.root, 0.8); _select(tree, "boris")
    before = set(_toplevels(world.root))
    _button(view, "Продлить…").invoke()
    top = _new_dialog(world, before)
    _fill(top, "abc")
    _submit(top)
    pump(world.root, 0.3)
    assert top.winfo_exists() and any("число" in str(w.cget("text")) for w in _walk(top)
                                      if w.winfo_class() == "Label")
    top.destroy()
    # лимит устройств
    pump(world.root, 0.5); _select(tree, "boris")
    before = set(_toplevels(world.root))
    _button(view, "Лимит устройств…").invoke()
    top = _new_dialog(world, before)
    _fill(top, "4")
    _submit(top)
    assert pump_until(world.root, lambda: fresh()["max_devices"] == 4, 5)
    # заметка
    pump(world.root, 0.8); _select(tree, "boris")
    before = set(_toplevels(world.root))
    _button(view, "Заметка").invoke()
    top = _new_dialog(world, before)
    _fill(top, "друг семьи")
    _submit(top)
    assert pump_until(world.root, lambda: fresh()["note"] == "друг семьи", 5)
    # бессрочно (без диалога) и отзыв лицензии (без диалога)
    pump(world.root, 0.8); _select(tree, "boris")
    _button(view, "Бессрочно").invoke()
    assert pump_until(world.root, lambda: fresh()["expires"] is None and fresh()["license"] == "active", 5)
    pump(world.root, 0.8); _select(tree, "boris")
    _button(view, "Отозвать лицензию").invoke()
    assert pump_until(world.root, lambda: fresh()["license"] == "revoked", 5)
    # сброс устройств
    pump(world.root, 0.8); _select(tree, "boris")
    _button(view, "Сбросить устройства").invoke()
    assert pump_until(world.root, lambda: fresh()["devices"] == 0, 5)
    assert not world.errors, world.errors


def test_reset_password_shows_temporary_password_that_works(world):
    _user(world, "vera")
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "users", view)
    _select(tree, "vera")
    before = set(_toplevels(world.root))
    _button(view, "Новый пароль").invoke()
    confirm = _new_dialog(world, before)
    before2 = set(_toplevels(world.root))
    _click_text(confirm, "Да")
    shown = _new_dialog(world, before2)
    box = [w for w in _walk(shown) if w.winfo_class() == "Text"][0]
    new_pw = box.get("1.0", "end").strip()
    assert len(new_pw) >= 10
    from photogrid.account import device
    r = ApiClient(world.admin_api.base, app_version="1").login("vera", new_pw, device.hwid(), "x")
    assert r["user"]["must_change_pw"] is True


def test_delete_user_and_role_change_from_ui(world):
    _user(world, "gleb")
    _user(world, "dasha")
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "users", view)
    names = lambda: {x["username"] for x in world.admin_api.admin("GET", "/users")["items"]}
    _select(tree, "gleb")
    before = set(_toplevels(world.root))
    _button(view, "Удалить").invoke()
    d = _new_dialog(world, before)
    _click_text(d, "Удалить")
    assert pump_until(world.root, lambda: "gleb" not in names(), 5)
    pump(world.root, 0.8); _select(tree, "dasha")
    before = set(_toplevels(world.root))
    _button(view, "Роль").invoke()
    d = _new_dialog(world, before)
    _click_text(d, "Да")
    assert pump_until(world.root, lambda: [x for x in world.admin_api.admin("GET", "/users")["items"]
                                           if x["username"] == "dasha"][0]["role"] == "admin", 5)
    assert not world.errors, world.errors


def test_search_and_actions_without_selection_are_harmless(world):
    _user(world, "egor")
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "users", view)
    _button(view, "Продлить…").invoke()                  # ничего не выбрано
    pump(world.root, 0.3)
    assert not [w for w in _toplevels(world.root) if w.winfo_viewable()]
    entry = [w for w in _walk(view) if w.winfo_class() == "Entry" and w.winfo_ismapped()][0]
    entry.insert(0, "egor"); _button(view, "Найти").invoke()
    assert pump_until(world.root, lambda: [tree.item(i, "values")[0] for i in tree.get_children()] == ["egor"], 5)


def test_issue_keys_from_the_keys_tab(world):
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "keys", view)
    total0 = len(world.admin_api.admin("GET", "/keys")["items"])
    before = set(_toplevels(world.root))
    _button(view, "Выпустить").invoke()
    top = _new_dialog(world, before)
    text = [w for w in _walk(top) if w.winfo_class() == "Text"][0].get("1.0", "end").strip()
    assert text.startswith("PE-") and len(text.splitlines()) == 1
    assert len(world.admin_api.admin("GET", "/keys")["items"]) == total0 + 1
    assert pump_until(world.root, lambda: len(tree.get_children()) == total0 + 1, 5)


def test_news_publish_and_delete_from_ui(world):
    app, view, seg = _admin_view(world)
    tree = _tab(world, seg, "news", view)
    entries = [w for w in _walk(view) if w.winfo_class() == "Entry" and w.winfo_ismapped()]
    entries[0].insert(0, "Заголовок новости"); entries[1].insert(0, "Текст")
    _button(view, "Опубликовать").invoke()
    assert pump_until(world.root, lambda: any(a["title"] == "Заголовок новости"
                                              for a in world.admin_api.announcements()), 5)
    assert pump_until(world.root, lambda: len(tree.get_children()) == 1, 5)
    tree.selection_set(tree.get_children()[0])
    _button(view, "Удалить выбранную").invoke()
    assert pump_until(world.root, lambda: world.admin_api.announcements() == [], 5)


def test_account_dialogs_work_from_ui(world):
    s = _session(world, "hugo")
    app = _make_app(world, s)
    app.open_account()
    pump(world.root, 1.0)
    view = app.views["account"]
    before = set(_toplevels(world.root))
    _button(view, "Сменить пароль").invoke()
    top = _new_dialog(world, before)
    _fill(top, "password-1", "brand-new-pass", "brand-new-pass")
    _submit(top)
    assert pump_until(world.root, lambda: _can_login(world, "hugo", "brand-new-pass"), 5)


def _can_login(world, user, pw):
    from photogrid.account import device
    try:
        ApiClient(world.admin_api.base, app_version="1").login(user, pw, device.hwid(), "x")
        return True
    except ApiError:
        return False
