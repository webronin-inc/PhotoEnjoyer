"""Интерфейс аккаунтов целиком: окно входа, кабинет, библиотека, админка."""
import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("cryptography")

from server import security                              # noqa: E402
from server.app import App as Server                      # noqa: E402
from photogrid import anim                                 # noqa: E402
from photogrid.account import gate, store                  # noqa: E402
from photogrid.account.api import ApiClient               # noqa: E402


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def pump(root, sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.005)


def pump_until(root, cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


@pytest.fixture
def world(tmp_path, monkeypatch):
    if tk.TkVersion >= 9.0:
        pytest.skip("tkinterdnd2 не поддерживает Tk 9")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("PE_ADMIN_USER", "boss")
    monkeypatch.setenv("PE_ADMIN_PASSWORD", "super-secret-1")
    server = Server(str(tmp_path / "data"))
    httpd = make_server("127.0.0.1", 0, server, handler_class=_Quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    pem = tmp_path / "pub.pem"
    pem.write_bytes(security.public_pem(server.priv))
    monkeypatch.setenv("PE_SERVER_URL", f"http://127.0.0.1:{httpd.server_port}")
    monkeypatch.setenv("PE_LICENSE_PUB", str(pem))
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        httpd.shutdown()
        pytest.skip("нет дисплея")
    errors = []
    root.report_callback_exception = lambda *a: errors.append(a)
    root.geometry("1316x872+0+0")

    class W:
        pass
    w = W()
    w.server, w.root, w.errors = server, root, errors
    w.admin_api = ApiClient(f"http://127.0.0.1:{httpd.server_port}", timeout=3, app_version="1.0.0.0")
    w.admin_api.token = w.admin_api.login("boss", "super-secret-1", "e" * 32, "adm")["token"]
    w.key = lambda **kw: w.admin_api.admin("POST", "/keys", {"count": 1, "days": 30, "max_devices": 1,
                                                             "plan": "T", **kw})["keys"][0]
    yield w
    anim.set_level("full")
    try:
        root.destroy()
    finally:
        httpd.shutdown()
        httpd.server_close()


def _login_screen(w, **kw):
    from photogrid.screens.login import LoginScreen
    ls = LoginScreen(w.root, **kw)
    return ls


def test_login_screen_register_flow_and_gate_steps(world):
    ls = _login_screen(world, resume=False)
    pump(world.root, 0.4)
    ls.tab_var.set("register")
    pump(world.root, 0.3)
    ls.rg_key.var.set(world.key().replace("-", "").lower())      # ввод «как попало» → формат
    pump(world.root, 0.1)
    assert ls.rg_key.get().startswith("PE-") and ls.rg_key.get().count("-") == 3
    ls.rg_user.var.set("anna"); ls.rg_pass.var.set("password-1")
    ls._submit()                                                  # без согласия — не отправляет
    assert ls.view == "register" and not ls._busy
    ls.consent.set(True)
    ls._submit()
    assert ls._busy
    assert pump_until(world.root, lambda: ls._done.get(), 8.0), "вход не завершился"
    assert ls.result.username == "anna" and ls.result.license_active
    assert not world.errors


def test_login_screen_wrong_password_shows_error_and_recovers(world):
    key = world.key()
    gate.authenticate(ApiClient(world.admin_api.base, app_version="1"), "register",
                      {"key": key, "username": "bob", "password": "password-1", "consent": True}, False)
    ls = _login_screen(world, resume=False)
    pump(world.root, 0.3)
    ls.in_user.var.set("bob"); ls.in_pass.var.set("wrong-pass-1")
    ls._submit()
    assert pump_until(world.root, lambda: "Неверный" in ls.err.cget("text"))
    assert ls.steps.state["account"][0] == "fail" and not ls._busy
    ls._back()
    assert ls.view == "login"
    ls.in_pass.var.set("password-1")
    ls._submit()
    assert pump_until(world.root, lambda: ls._done.get(), 8.0)
    assert ls.result.username == "bob"


def test_login_screen_auto_resume_uses_saved_session(world):
    gate.authenticate(ApiClient(world.admin_api.base, app_version="1"), "register",
                      {"key": world.key(), "username": "carl", "password": "password-1",
                       "consent": True}, True)
    assert store.load()
    ls = _login_screen(world)
    assert pump_until(world.root, lambda: ls._done.get(), 8.0)
    assert ls.result.username == "carl"


def test_login_screen_expired_license_asks_for_key(world):
    s = gate.authenticate(ApiClient(world.admin_api.base, app_version="1"), "register",
                          {"key": world.key(days=1), "username": "dina", "password": "password-1",
                           "consent": True}, False)
    from server import db
    con = db.connect(world.server.db_path)
    con.execute("UPDATE users SET lic_expires=? WHERE username='dina'", (int(time.time()) - 5,))
    con.commit(); con.close()
    ls = _login_screen(world, resume=False)
    pump(world.root, 0.3)
    ls.in_user.var.set("dina"); ls.in_pass.var.set("password-1")
    ls._submit()
    assert pump_until(world.root, lambda: ls.view == "activate")
    ls.act_key.var.set(world.key(days=10))
    pump(world.root, 0.1)
    ls._submit()
    assert pump_until(world.root, lambda: ls._done.get(), 8.0)
    assert ls.result.license_active


def test_login_screen_device_limit_offers_release(world):
    gate.authenticate(ApiClient(world.admin_api.base, app_version="1"), "register",
                      {"key": world.key(), "username": "emil", "password": "password-1",
                       "consent": True}, False)
    from photogrid.account import device
    # «другой компьютер»: чужой hwid
    orig = device.hwid
    device.hwid = lambda: "9" * 32
    try:
        ls = _login_screen(world, resume=False)
        pump(world.root, 0.3)
        ls.in_user.var.set("emil"); ls.in_pass.var.set("password-1")
        ls._submit()
        assert pump_until(world.root, lambda: "лимит" in ls.err.cget("text").lower())
        radios = [w for w in ls.extra.winfo_children() if isinstance(w, tk.Radiobutton)]
        assert radios, "должен быть список устройств для отключения"
    finally:
        device.hwid = orig


def _make_app(world, session):
    from photogrid.app import App
    app = App(world.root, session=session)
    pump(world.root, 0.4)
    return app


def _session(world, user="gina", admin=False):
    api = ApiClient(world.admin_api.base, app_version="1.0.0.0")
    if admin:
        return gate.authenticate(api, "login", {"username": "boss", "password": "super-secret-1"}, False)
    return gate.authenticate(api, "register", {"key": world.key(), "username": user,
                                               "password": "password-1", "consent": True}, False)


def test_app_with_user_session_account_and_library(world):
    s = _session(world)
    app = _make_app(world, s)
    assert "account" in app.rail_buttons and "admin" not in app.rail_buttons
    app.open_account()
    pump(world.root, 0.8)
    assert app.active_section == "account"
    # публикуем пакет и ставим его через интерфейс
    from photogrid.account import library as lib
    pack = lib.build_pack("neon-night", "Неон", "Яркие", "me",
                          {"Ночной": {"layout": "2×2 — квадрат", "mode": "fill", "cell_size": 700,
                                      "border": 8, "border_color": "#111111", "bg_color": "#0b0b14"}})
    world.admin_api.admin("POST", "/library", raw=pack)
    app._set_section("library")
    assert pump_until(world.root, lambda: app.views["library"].winfo_children() and any(
        c.winfo_class() == "Canvas" and hasattr(c, "item") for c in _walk(app.views["library"])), 5)
    card = next(c for c in _walk(app.views["library"]) if hasattr(c, "item"))
    card.on_install(card.item)
    assert pump_until(world.root, lambda: card.state == "installed", 8)
    from photogrid.screens.templates import _load_user_templates
    assert "Ночной" in _load_user_templates()
    assert app.config["installed_packs"]["neon-night"] == "1"
    assert not world.errors


def test_account_actions_change_password_and_stats_toggle(world):
    s = _session(world, "hugo")
    app = _make_app(world, s)
    app.open_account()
    pump(world.root, 0.8)
    seg = [w for w in _walk(app.views["account"]) if w.winfo_class() == "Canvas" and hasattr(w, "_cells")
           and "on" in w._cells][0]
    seg._choose("off")
    pump(world.root, 0.3)
    assert s.usage_stats is False
    me = s.api.me()
    assert me["user"]["usage_stats"] is False
    s.api.change_password("password-1", "newpass-123")
    assert gate.authenticate(ApiClient(world.admin_api.base, app_version="1"), "login",
                             {"username": "hugo", "password": "newpass-123"}, False)


def test_admin_panel_all_tabs_and_actions(world):
    world.admin_api.admin("POST", "/announcements", {"title": "Привет", "body": "Мир"})
    sess_user = _session(world, "iris")                  # есть кого показывать
    sess_user.track("app_start"); sess_user.telemetry.flush()
    s = _session(world, admin=True)
    app = _make_app(world, s)
    assert "admin" in app.rail_buttons
    app._set_section("admin")
    pump(world.root, 0.6)
    view = app.views["admin"]
    seg = [w for w in _walk(view) if hasattr(w, "_cells") and "overview" in w._cells][0]
    for tab in ("overview", "users", "keys", "logs", "library", "news", "server"):
        seg._choose(tab)
        pump(world.root, 0.7)
    # вкладка «Пользователи» показывает iris
    seg._choose("users"); pump(world.root, 0.8)
    trees = [w for w in _walk(view) if w.winfo_class() == "Treeview" and w.winfo_ismapped()]
    names = [trees[0].item(i, "values")[0] for i in trees[0].get_children()]
    assert "iris" in names
    # логи содержат событие
    seg._choose("logs"); pump(world.root, 0.8)
    tree = [w for w in _walk(view) if w.winfo_class() == "Treeview" and w.winfo_ismapped()][0]
    assert any("запуск" in str(tree.item(i, "values")) for i in tree.get_children())
    assert not world.errors, world.errors


def test_non_admin_cannot_open_admin_view(world):
    s = _session(world, "jack")
    app = _make_app(world, s)
    assert "admin" not in app.rail_buttons
    from photogrid.screens.admin import build_admin_view
    v = build_admin_view(app.content, app)
    pump(world.root, 0.2)
    assert any("только администратору" in str(w.cget("text")) for w in _walk(v)
               if w.winfo_class() == "Label")


def test_session_watch_closes_app_when_banned(world, monkeypatch):
    s = _session(world, "kate")
    app = _make_app(world, s)
    uid = s.info["user"]["id"]
    world.admin_api.admin("POST", f"/users/{uid}/ban", {"reason": "test"})
    shown, closed = [], []
    monkeypatch.setattr("photogrid.app.messagebox.showwarning", lambda *a, **k: shown.append(a))
    monkeypatch.setattr(app, "on_close", lambda: closed.append(1))
    app._session_watch()
    assert pump_until(world.root, lambda: closed, 6)
    assert shown and "заблокирован" in shown[0][1]


def test_app_without_session_still_works_and_hides_account(world, monkeypatch):
    monkeypatch.delenv("PE_SERVER_URL", raising=False)
    app = _make_app(world, None)
    assert "account" not in app.rail_buttons and "admin" not in app.rail_buttons
    app._set_section("library"); pump(world.root, 0.3)
    app._set_section("collage")
    app.track("export_save", w=1)                         # без сессии — просто ничего не делает


def test_telemetry_hooks_fire_from_app(world):
    s = _session(world, "lena")
    app = _make_app(world, s)
    app.track("export_save", w=10, h=10)
    s.telemetry.flush()
    ev = world.admin_api.admin("GET", "/events", query={"user": "lena"})["items"]
    assert {"app_start", "export_save"} <= {e["type"] for e in ev}


def _walk(w):
    yield w
    for c in w.winfo_children():
        yield from _walk(c)


def test_plural_forms_for_pack_cards():
    from photogrid.screens.library import _plural
    f = ("шаблон", "шаблона", "шаблонов")
    assert [_plural(n, f) for n in (1, 2, 4, 5, 11, 12, 21, 22, 25, 101, 111)] == [
        "шаблон", "шаблона", "шаблона", "шаблонов", "шаблонов", "шаблонов",
        "шаблон", "шаблона", "шаблонов", "шаблон", "шаблонов"]
