"""Клиент аккаунтов: реальный HTTP к локальному серверу."""
import sys
import threading
import time
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("cryptography")

from server import security                            # noqa: E402
from server.app import App                              # noqa: E402
from photogrid.account import device, gate, store, tokens  # noqa: E402
from photogrid.account.api import ApiClient, ApiError, NetworkError  # noqa: E402
from server_client import call                          # noqa: E402


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("PE_ADMIN_USER", "boss")
    monkeypatch.setenv("PE_ADMIN_PASSWORD", "super-secret-1")
    app = App(str(tmp_path / "data"))
    pub = app.pub
    httpd = make_server("127.0.0.1", 0, app, handler_class=_Quiet)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{httpd.server_port}"

    class E:
        pass
    e = E()
    e.app, e.pub, e.url, e.httpd = app, pub, url, httpd
    e.api = lambda: ApiClient(url, timeout=3, app_version="1.0.0.0")
    admin = e.api()
    admin.token = admin.login("boss", "super-secret-1", "e" * 32, "adm")["token"]
    e.admin = admin
    e.key = lambda **kw: admin.admin("POST", "/keys", {"count": 1, "days": 30, "max_devices": 1,
                                                       "plan": "T", **kw})["keys"][0]
    yield e
    httpd.shutdown()
    httpd.server_close()


def steps_logger():
    log = []
    return log, lambda step, state, detail="": log.append((step, state))


def test_token_format_is_compatible_between_server_and_client(env):
    tok = security.sign_token(env.app.priv, {"x": 1, "exp": time.time() + 100})
    assert tokens.verify_token(env.pub, tok)["x"] == 1
    assert tokens.verify_token(env.pub, tok, now=time.time() + 500) is None
    assert tokens.verify_token(env.pub, tok + "x") is None


def test_register_then_login_through_gate(env):
    log, prog = steps_logger()
    s = gate.authenticate(env.api(), "register",
                          {"key": env.key(), "username": "anna", "password": "password-1",
                           "consent": True}, True, prog, pub=env.pub)
    assert s.username == "anna" and s.license_active and not s.offline
    assert [x for x in log if x[1] == "fail"] == []
    assert {x[0] for x in log} >= {"network", "version", "account", "license", "device", "clock"}
    assert store.load()["username"] == "anna"           # «запомнить» сохранил сессию
    s2 = gate.authenticate(env.api(), "login", {"username": "anna", "password": "password-1"},
                           False, pub=env.pub)
    assert s2.username == "anna" and store.load() is None   # без «запомнить» сессия стёрта


def test_gate_error_mapping(env):
    api = env.api()
    with pytest.raises(gate.GateError) as e:
        gate.authenticate(api, "login", {"username": "nobody", "password": "xxxxxxxx"},
                          False, pub=env.pub)
    assert e.value.code == "bad_credentials" and e.value.step == "account"
    gate.authenticate(api, "register",
                      {"key": env.key(), "username": "bob", "password": "password-1",
                       "consent": True}, False, pub=env.pub)
    env.admin.admin("POST", "/settings", {"min_version": "9.9.9.9", "download_url": "http://dl"})
    with pytest.raises(gate.GateError) as e:                  # обычного пользователя — просим обновиться
        gate.authenticate(env.api(), "login", {"username": "bob", "password": "password-1"},
                          False, pub=env.pub)
    assert e.value.code == "update_required" and e.value.action == "update"
    assert e.value.step == "version" and e.value.data["download_url"] == "http://dl"
    # администратора обновление не блокирует (иначе не зайти и не исправить настройку)
    assert gate.authenticate(env.api(), "login", {"username": "boss", "password": "super-secret-1"},
                             False, pub=env.pub).is_admin
    env.admin.admin("POST", "/settings", {"min_version": "0.0.0.0", "maintenance": True})
    with pytest.raises(gate.GateError) as e:
        gate.authenticate(env.api(), "login", {"username": "bob", "password": "password-1"},
                          False, pub=env.pub)
    assert e.value.code == "maintenance" and e.value.action == "wait"


def test_device_limit_maps_to_devices_action(env):
    gate.authenticate(env.api(), "register", {"key": env.key(), "username": "carl",
                                              "password": "password-1", "consent": True},
                      False, pub=env.pub)
    other = env.api()
    r = None
    try:
        other.login("carl", "password-1", "f" * 32, "Другой ПК")
    except ApiError as e:
        r = e
    assert r and r.code == "device_limit" and r.data["devices"]


def test_untrusted_server_is_rejected(env, tmp_path):
    """Токен, подписанный чужим ключом, не принимается."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    stranger = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(gate.GateError) as e:
        gate.authenticate(env.api(), "login", {"username": "boss", "password": "super-secret-1"},
                          False, pub=stranger)
    assert e.value.code == "untrusted_server"


def test_network_down_reports_retry(tmp_path):
    api = ApiClient("http://127.0.0.1:9", timeout=1, app_version="1")
    with pytest.raises(gate.GateError) as e:
        gate.authenticate(api, "login", {"username": "a", "password": "b"}, False)
    assert e.value.code == "network" and e.value.action == "retry"


def test_resume_online_then_offline_grace(env):
    gate.authenticate(env.api(), "register", {"key": env.key(), "username": "dina",
                                              "password": "password-1", "consent": True},
                      True, pub=env.pub)
    s = gate.resume(env.api(), pub=env.pub)
    assert s and not s.offline and s.username == "dina"
    env.httpd.shutdown(); env.httpd.server_close()          # «сервер упал»
    dead = ApiClient(env.url, timeout=1, app_version="1")
    log, prog = steps_logger()
    s2 = gate.resume(dead, prog, pub=env.pub)
    assert s2.offline and s2.username == "dina" and s2.license_active
    assert s2.telemetry.flush() is False                   # офлайн ничего не шлёт


def test_resume_without_saved_session(env):
    assert gate.resume(env.api(), pub=env.pub) is None


def test_offline_blocked_when_token_expired_or_clock_rolled_back(env):
    gate.authenticate(env.api(), "register", {"key": env.key(), "username": "emil",
                                              "password": "password-1", "consent": True},
                      True, pub=env.pub)
    env.httpd.shutdown(); env.httpd.server_close()
    dead = ApiClient(env.url, timeout=1, app_version="1")
    with pytest.raises(gate.GateError) as e:                  # токен просрочен (8 дней)
        gate.resume(dead, pub=env.pub, now=time.time() + 8 * 86400)
    assert e.value.code == "token_invalid" and store.load() is None
    # откат часов
    tok = security.sign_token(env.app.priv, {"u": "emil", "role": "user", "dev": device.hwid(),
                                             "exp": time.time() + 1000,
                                             "lic": {"state": "active", "plan": "T", "exp": None}})
    store.save(tok, "emil", True, last_seen=int(time.time()) + 5 * 86400)
    with pytest.raises(gate.GateError) as e:
        gate.resume(dead, pub=env.pub)
    assert e.value.code == "clock_rollback"


def test_offline_expired_license_requires_activation(env):
    tok = security.sign_token(env.app.priv, {"u": "z", "role": "user", "dev": device.hwid(),
                                             "exp": time.time() + 1000,
                                             "lic": {"state": "active", "plan": "T",
                                                     "exp": int(time.time()) - 5}})
    store.save(tok, "z", True)
    dead = ApiClient("http://127.0.0.1:9", timeout=1, app_version="1")
    with pytest.raises(gate.GateError) as e:
        gate.resume(dead, pub=env.pub)
    assert e.value.code == "license_expired" and e.value.action == "activate"


def test_resume_clears_session_when_account_banned(env):
    s = gate.authenticate(env.api(), "register", {"key": env.key(), "username": "fred",
                                                  "password": "password-1", "consent": True},
                          True, pub=env.pub)
    uid = s.info["user"]["id"]
    env.admin.admin("POST", f"/users/{uid}/ban", {"reason": "тест"})
    with pytest.raises(gate.GateError) as e:
        gate.resume(env.api(), pub=env.pub)
    assert e.value.code == "banned" and store.load() is None


def test_session_store_roundtrip_and_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store.save("TOKEN-123", "u", True, 1000)
    raw = store._path().read_text()
    assert "TOKEN-123" not in raw                     # токен не лежит открытым текстом
    d = store.load()
    assert d["token"] == "TOKEN-123" and d["last_seen"] == 1000
    store.touch_last_seen(500)
    assert store.load()["last_seen"] == 1000                # время назад не двигаем
    store.touch_last_seen(2000)
    assert store.load()["last_seen"] == 2000
    store.clear()
    assert store.load() is None


def test_hwid_is_stable_and_not_raw():
    a, b = device.hwid(), device.hwid()
    assert a == b and len(a) == 32 and all(c in "0123456789abcdef" for c in a)


def test_telemetry_batches_and_respects_opt_out(env):
    s = gate.authenticate(env.api(), "register", {"key": env.key(), "username": "gina",
                                                  "password": "password-1", "consent": True},
                          False, pub=env.pub)
    s.track("app_start"); s.track("export_save", w=100)
    assert s.telemetry.flush() is True
    items = env.admin.admin("GET", "/events", query={"user": "gina"})["items"]
    assert {i["type"] for i in items} >= {"app_start", "export_save"}
    s.api.set_usage_stats(False)
    s.info["user"]["usage_stats"] = False
    s.track("export_save", w=1)                             # локально отфильтровано
    s.track("app_exit")
    s.telemetry.flush()
    items = env.admin.admin("GET", "/events", query={"user": "gina", "type": "export_save"})
    assert items["total"] == 1


def test_telemetry_failure_keeps_queue(env):
    s = gate.authenticate(env.api(), "register", {"key": env.key(), "username": "hugo",
                                                  "password": "password-1", "consent": True},
                          False, pub=env.pub)
    env.httpd.shutdown(); env.httpd.server_close()
    s.track("app_start")
    assert s.telemetry.flush() is False and len(s.telemetry._q) == 1
    for _ in range(300):
        s.track("app_start")
    assert len(s.telemetry._q) <= s.telemetry.MAX_QUEUE


def test_library_download_through_api(env):
    import io, json, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pack.json", json.dumps({"id": "neon-1", "name": "N",
                                            "templates": [{"name": "A"}]}))
    env.admin.admin("POST", "/library", raw=buf.getvalue())
    s = gate.authenticate(env.api(), "register", {"key": env.key(), "username": "iris",
                                                  "password": "password-1", "consent": True},
                          False, pub=env.pub)
    assert s.api.library()[0]["id"] == "neon-1"
    data, headers = s.api.library_download("neon-1")
    assert data == buf.getvalue()


def test_enforced_requires_url_and_public_key(monkeypatch, tmp_path):
    monkeypatch.delenv("PE_SERVER_URL", raising=False)
    monkeypatch.delenv("PE_LICENSE_PUB", raising=False)
    monkeypatch.setattr(gate.server_config, "SERVER_URL", "")
    monkeypatch.setattr(gate, "public_key", lambda: None)
    assert gate.enforced() is False                         # ни адреса, ни ключа
    monkeypatch.setenv("PE_SERVER_URL", "https://x.pythonanywhere.com")
    assert gate.enforced() is False                         # нет ключа
    pem = tmp_path / "pub.pem"
    pem.write_bytes(security.public_pem(security.load_or_create_keypair(str(tmp_path / "k"))))
    monkeypatch.undo()
    monkeypatch.setenv("PE_SERVER_URL", "https://x.pythonanywhere.com")
    monkeypatch.setenv("PE_LICENSE_PUB", str(pem))
    assert gate.enforced() is True


def test_shipped_public_key_is_a_valid_ed25519_key_and_url_is_set():
    """Файлы, которые уходят в сборку: ключ сервера и его адрес."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from photogrid import server_config
    key = gate.public_key()
    assert isinstance(key, Ed25519PublicKey)
    assert server_config.SERVER_URL.startswith("https://")
    assert gate.enforced() is True
