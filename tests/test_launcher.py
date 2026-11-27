"""Общее меню, панель Word и вкладка админки «Word»."""
import hashlib
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("cryptography")

from test_account_ui import (_make_app, _session, _walk, pump, pump_until,   # noqa: E402,F401
                             world)
from test_admin_actions import _admin_view, _button                          # noqa: E402
from photogrid.launcher import registry                                      # noqa: E402
from photogrid.launcher.hub import HubScreen                                 # noqa: E402
from photogrid.word import flow as wflow                                     # noqa: E402


class Script:
    """Подставной сценарий Word: проигрывает заранее заданные шаги."""

    def __init__(self, steps, outcome, ask=None):
        self.steps, self.outcome, self.ask_ctx = steps, outcome, ask

    def __call__(self, session, ask, report, progress, cancel, log=None):
        script = self

        class F:
            def run(self_inner):
                for st in script.steps:
                    if st[0] == "ask":
                        script.answer = ask(script.ask_ctx)
                        if not script.answer:
                            return wflow.Outcome("declined", "Установка отменена по вашему желанию.")
                    elif st[0] == "progress":
                        progress("download", st[1], st[2])
                        time.sleep(0.15)
                    else:
                        report(*st)
                return script.outcome
        return F()


CTX = {"target": "Word 2021", "current": "Word 2019 (сборка 16.0.1)", "installed": True,
       "size_text": "3.2 ГБ", "host": "files.example.com", "notes": ""}


def _run_hub(world, session=None, action=None, delay=0.4):
    h = HubScreen(world.root, session)
    world.root.after(int(delay * 1000), lambda: action(h))
    return h, h.run()


def test_registry_has_photo_and_word():
    assert [m.id for m in registry.MODULES] == ["photo", "word"]
    assert registry.by_id("word").windows_only and registry.by_id("photo").available


def test_hub_photo_logout_and_close(world):
    assert _run_hub(world, None, lambda h: h.cards[0].on_click())[1] == "photo"
    s = _session(world, "ivan")
    assert _run_hub(world, s, lambda h: h.btn_logout.invoke())[1] == "logout"
    assert _run_hub(world, None, lambda h: h._close())[1] is None


def test_word_card_is_disabled_off_windows(world):
    h = HubScreen(world.root, None)
    pump(world.root, 0.4)
    word = h.cards[1]
    if sys.platform != "win32":
        called = []
        word.on_click = lambda: called.append(1)
        word._click(None)
        pump(world.root, 0.3)
        assert not word.module.available and word.cursor == "arrow" and called == []
    h._close()


def _open_panel(world, script, session=None):
    h = HubScreen(world.root, session)
    h.flow_factory = script
    pump(world.root, 0.3)
    h._show_word()
    return h


def test_panel_consent_yes_then_back(world):
    script = Script([("check", "warn", "Word 2019"), ("ask",), ("download", "running"),
                     ("progress", 100 * 1024 ** 2, 3 * 1024 ** 3), ("download", "ok"),
                     ("install", "running"), ("install", "ok")],
                    wflow.Outcome("launched", "Word запущен."), ask=CTX)
    h = _open_panel(world, script)
    assert pump_until(world.root, lambda: h._panel.consent.winfo_ismapped(), 5)
    assert "3.2 ГБ" in h._panel.consent_body.cget("text")
    h._panel.btn_yes._invoke()
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 8)
    assert script.answer is True and h._panel.outcome.kind == "launched"
    h._back_from_word()
    assert h._panel is None
    h._close()


def test_panel_consent_no_installs_nothing(world):
    script = Script([("check", "warn", "нет"), ("ask",)], None, ask={**CTX, "installed": False})
    h = _open_panel(world, script)
    assert pump_until(world.root, lambda: h._panel.consent.winfo_ismapped(), 5)
    h._panel.btn_no.invoke()
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    assert h._panel.outcome.kind == "declined" and script.answer is False
    h._close()


def test_panel_error_has_retry_log_and_back(world):
    calls = []

    def factory(session, ask, report, progress, cancel, log=None):
        calls.append(1)
        return Script([("package", "fail", "нет связи")],
                      wflow.Outcome("error", "Нет связи с сервером.", "package:network"))(
            session, ask, report, progress, cancel, log)
    h = _open_panel(world, factory)
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    texts = [w.cget("text") for w in _walk(h._panel.actions) if w.winfo_class() == "Button"]
    assert "Открыть журнал" in texts and "Назад в меню" in texts
    [w for w in _walk(h._panel.actions) if w.__class__.__name__ == "GradientButton"][0]._invoke()
    assert pump_until(world.root, lambda: len(calls) == 2 and h._panel.outcome is not None, 6)
    h._close()


def test_panel_survives_crashing_flow(world):
    def factory(*a, **k):
        class F:
            def run(self):
                raise RuntimeError("взрыв")
        return F()
    h = _open_panel(world, factory)
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    assert h._panel.outcome.kind == "error"
    h._close()


def test_hub_skip_rules(monkeypatch):
    from photogrid import app as appmod
    monkeypatch.delenv("PE_NO_HUB", raising=False)
    monkeypatch.setattr(sys, "argv", ["prog"])
    assert appmod._skip_hub() is False
    monkeypatch.setattr(sys, "argv", ["prog", "--check-updates"])
    assert appmod._skip_hub() is True
    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setenv("PE_NO_HUB", "1")
    assert appmod._skip_hub() is True


def test_admin_word_tab_saves_description(world, tmp_path):
    app, view, seg = _admin_view(world)
    seg._choose("word")
    pump(world.root, 0.8)
    page = [w for w in _walk(view) if hasattr(w, "fill_from_file")][0]
    f = tmp_path / "setup.exe"
    f.write_bytes(b"hello-installer")
    page.fill_from_file(str(f))
    entries = [w for w in _walk(page) if w.winfo_class() == "Entry"]
    assert pump_until(world.root, lambda: any(e.get() == hashlib.sha256(b"hello-installer").hexdigest()
                                              for e in entries), 5)
    [e for e in entries if e.get() == "" and e.cget("width") == 64][0].insert(
        0, "https://files.example.com/office/setup.exe")
    for w in _walk(page):
        if w.__class__.__name__ == "SegmentedControl" and "on" in w._cells:
            w._choose("on")
    _button(view, "Сохранить").invoke()
    assert pump_until(world.root, lambda: world.admin_api.admin("GET", "/software/word")["package"]["enabled"], 5)
    pk = world.admin_api.admin("GET", "/software/word")["package"]
    assert pk["sha256"] == hashlib.sha256(b"hello-installer").hexdigest() and pk["size"] == 15
    assert pk["filename"] == "setup.exe" and pk["url"].startswith("https://")
