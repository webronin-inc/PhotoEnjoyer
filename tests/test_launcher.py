"""Общее меню и панель модуля Word (с подставными сценариями)."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("cryptography")

from test_account_ui import _session, _walk, pump, pump_until, world   # noqa: E402,F401
from photogrid.launcher import registry                               # noqa: E402
from photogrid.launcher.hub import HubScreen                          # noqa: E402
from photogrid.word import flow as wflow                              # noqa: E402


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
                    elif st[0] == "wait_cancel":
                        for _ in range(100):
                            if cancel.is_set():
                                return wflow.Outcome("cancelled", "Загрузка отменена.")
                            time.sleep(0.02)
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


def _open_panel(world, script, session=None):
    h = HubScreen(world.root, session)
    h.flow_factory = script
    pump(world.root, 0.3)
    h._show_word()
    return h


def test_registry_has_photo_and_word():
    assert [m.id for m in registry.MODULES] == ["photo", "word"]
    assert registry.by_id("word").windows_only and registry.by_id("photo").available


def test_hub_returns_photo_when_photo_card_clicked(world):
    h, res = _run_hub(world, None, lambda h: h.cards[0].on_click())
    assert res == "photo"


def test_hub_logout_and_close(world):
    s = _session(world, "ivan")
    h, res = _run_hub(world, s, lambda h: h.btn_logout.invoke())
    assert res == "logout"
    h2, res2 = _run_hub(world, None, lambda h: h._close())
    assert res2 is None


def test_word_card_is_disabled_off_windows(world):
    h = HubScreen(world.root, None)
    pump(world.root, 0.4)
    word = h.cards[1]
    assert word.module.id == "word"
    if sys.platform != "win32":
        assert not word.module.available and word.cursor == "arrow"
        called = []
        word.on_click = lambda: called.append(1)
        word._click(None)
        assert called == []
    h._close()


def test_panel_already_installed_flow_then_back(world):
    out = wflow.Outcome("launched", "Word запущен.")
    h = _open_panel(world, Script([("check", "ok", "Word 2021"), ("launch", "ok")], out))
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    assert h._panel.msg.cget("text") == "Word запущен."
    h._back_from_word()
    assert h._panel is None
    h._close()


def test_panel_consent_yes_then_progress_and_success(world):
    script = Script([("check", "warn", "Word 2019"), ("ask",), ("download", "running"),
                     ("progress", 100 * 1024 ** 2, 3 * 1024 ** 3), ("download", "ok"),
                     ("install", "running"), ("install", "ok")],
                    wflow.Outcome("launched", "Word запущен."), ask=CTX)
    h = _open_panel(world, script)
    assert pump_until(world.root, lambda: h._panel.consent.winfo_ismapped(), 5)
    assert "3.2 ГБ" in h._panel.consent_body.cget("text")
    assert script.__dict__.get("answer") is None
    h._panel.btn_yes._invoke()
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 6)
    assert script.answer is True and h._panel.outcome.kind == "launched"
    h._close()


def test_panel_consent_no_returns_without_installing(world):
    script = Script([("check", "warn", "нет"), ("ask",)], None, ask={**CTX, "installed": False})
    h = _open_panel(world, script)
    assert pump_until(world.root, lambda: h._panel.consent.winfo_ismapped(), 5)
    h._panel.btn_no.invoke()
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    assert h._panel.outcome.kind == "declined" and script.answer is False
    h._close()


def test_panel_error_has_retry_log_and_back(world):
    h = _open_panel(world, Script([("package", "fail", "нет связи")],
                                  wflow.Outcome("error", "Нет связи с сервером.", "package:network")))
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    texts = [w.cget("text") for w in _walk(h._panel.actions) if w.winfo_class() == "Button"]
    assert "Открыть журнал" in texts and "Назад в меню" in texts
    h._close()


def test_panel_survives_crashing_flow(world):
    def factory(*a, **k):
        class F:
            def run(self):
                raise RuntimeError("взрыв")
        return F()
    h = _open_panel(world, factory)
    assert pump_until(world.root, lambda: h._panel.outcome is not None, 5)
    assert h._panel.outcome.kind == "error" and "журнал" in h._panel.msg.cget("text")
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
