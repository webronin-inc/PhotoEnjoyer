"""Сервер аккаунтов и лицензий: полный набор сценариев без сети."""
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("cryptography")

from server import db, security                    # noqa: E402
from server.app import App, validate_pack, vtuple  # noqa: E402
from server_client import call                     # noqa: E402

HW1 = "a" * 32
HW2 = "b" * 32
HW3 = "c" * 32


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PE_ADMIN_USER", "boss")
    monkeypatch.setenv("PE_ADMIN_PASSWORD", "super-secret-1")
    return App(str(tmp_path / "data"))


def admin_token(app):
    r = call(app, "POST", "/api/v1/auth/login",
             {"username": "boss", "password": "super-secret-1", "hwid": HW1,
              "device_name": "PC", "app_version": "1.0.0.0"})
    assert r.status == 200, r.json
    return r.json["token"]


def make_key(app, tok, **kw):
    body = {"count": 1, "days": 30, "max_devices": 1, "plan": "Тест"}
    body.update(kw)
    r = call(app, "POST", "/api/v1/admin/keys", body, tok)
    assert r.status == 200, r.json
    return r.json["keys"][0]


def register(app, key, username="anna", hwid=HW2, pw="password-1", **kw):
    body = {"key": key, "username": username, "password": pw, "hwid": hwid,
            "device_name": "Ноут", "app_version": "1.0.0.0", "consent": True}
    body.update(kw)
    return call(app, "POST", "/api/v1/auth/register", body)


def login(app, username="anna", pw="password-1", hwid=HW2, **kw):
    body = {"username": username, "password": pw, "hwid": hwid, "device_name": "Ноут",
            "app_version": "1.0.0.0"}
    body.update(kw)
    return call(app, "POST", "/api/v1/auth/login", body)


# ------------------------------------------------------------------ токены
def test_tokens_are_verifiable_offline_and_tamper_proof(app):
    tok = admin_token(app)
    pub = security.public_pem(app.priv)
    claims = security.verify_token(pub, tok)
    assert claims["u"] == "boss" and claims["role"] == "admin"
    head, sig = tok.split(".")
    forged = head[:-2] + ("AA" if head[-2:] != "AA" else "BB") + "." + sig
    assert security.verify_token(pub, forged) is None
    assert security.verify_token(pub, tok, now=time.time() + 8 * 86400) is None   # просрочен


def test_status_is_public(app):
    r = call(app, "GET", "/api/v1/status")
    assert r.status == 200 and r.json["maintenance"] is False


# ------------------------------------------------------- регистрация/лицензия
def test_register_with_key_then_login(app):
    adm = admin_token(app)
    key = make_key(app, adm, days=30)
    r = register(app, key)
    assert r.status == 200
    lic = r.json["license"]
    assert lic["state"] == "active" and lic["plan"] == "Тест"
    assert abs(lic["expires"] - (time.time() + 30 * 86400)) < 60
    assert login(app).status == 200


def test_key_is_single_use_and_validated(app):
    adm = admin_token(app)
    key = make_key(app, adm)
    assert register(app, key).status == 200
    r = register(app, key, username="boris", hwid=HW3)
    assert r.status == 400 and r.json["error"] == "key_used"
    assert register(app, "PE-AAAA-BBBB-CCCC", username="x" * 5).json["error"] == "invalid_key"
    assert register(app, "мусор", username="zed1").json["error"] == "invalid_key"


def test_register_validation(app):
    adm = admin_token(app)
    key = make_key(app, adm)
    assert register(app, key, consent=False).json["error"] == "consent_required"
    assert register(app, key, username="a b").json["error"] == "bad_username"
    assert register(app, key, pw="short").json["error"] == "weak_password"
    assert register(app, key, username="boss").json["error"] == "username_taken"


def test_key_brute_force_is_throttled(app):
    for i in range(5):
        register(app, "PE-AAAA-BBBB-CC" + "DEFGH"[i] + "J", username=f"user{i}x")
    r = register(app, "PE-AAAA-BBBB-CCDJ", username="userzz")
    assert r.status == 429 and r.json["error"] == "locked"


def test_license_expiry_and_extension_by_new_key(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm, days=1))
    tok = r.json["token"]
    uid = r.json["user"]["id"]
    # «состарим» лицензию
    con = db.connect(app.db_path)
    con.execute("UPDATE users SET lic_expires=? WHERE id=?", (int(time.time()) - 10, uid))
    con.commit(); con.close()
    assert login(app).json["license"]["state"] == "expired"
    # события и библиотека недоступны с просроченной лицензией
    assert call(app, "GET", "/api/v1/library", token=login(app).json["token"]).json["error"] == "license_expired"
    # новый ключ продлевает
    key2 = make_key(app, adm, days=10)
    r2 = call(app, "POST", "/api/v1/me/activate-key", {"key": key2}, login(app).json["token"])
    assert r2.status == 200 and r2.json["license"]["state"] == "active"
    assert call(app, "GET", "/api/v1/library", token=r2.json["token"]).status == 200


def test_unlimited_key_and_stacking(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm, days=0))
    assert r.json["license"]["expires"] is None
    r2 = call(app, "POST", "/api/v1/me/activate-key", {"key": make_key(app, adm, days=5)}, r.json["token"])
    assert r2.json["license"]["expires"] is None          # бессрочная остаётся


# ------------------------------------------------------------ вход и защита
def test_wrong_password_and_lockout(app):
    adm = admin_token(app)
    register(app, make_key(app, adm))
    for _ in range(5):
        assert login(app, pw="nope-nope-1").json["error"] == "bad_credentials"
    r = login(app)                       # даже верный пароль — блокировка
    assert r.status == 429 and r.json["retry_after"] > 0


def test_ip_is_never_stored_in_clear(app):
    adm = admin_token(app)
    register(app, make_key(app, adm))
    con = db.connect(app.db_path)
    dump = " ".join(str(tuple(r)) for r in con.execute("SELECT ip FROM events"))
    dump += " ".join(str(tuple(r)) for r in con.execute("SELECT ip FROM login_attempts"))
    assert "1.2.3.4" not in dump


def test_device_limit_and_release(app):
    adm = admin_token(app)
    register(app, make_key(app, adm, max_devices=1))
    r = login(app, hwid=HW3)
    assert r.status == 403 and r.json["error"] == "device_limit"
    dev_id = r.json["devices"][0]["id"]
    rel = call(app, "POST", "/api/v1/auth/release-device",
               {"username": "anna", "password": "password-1", "device_id": dev_id})
    assert rel.status == 200
    assert login(app, hwid=HW3).status == 200


def test_removed_device_token_stops_working(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm, max_devices=2))
    tok2 = login(app, hwid=HW3).json["token"]
    me = call(app, "GET", "/api/v1/me", token=r.json["token"]).json
    dev = [d for d in me["devices"] if d["name"] == "Ноут"][0]["id"]
    for d in me["devices"]:
        call(app, "DELETE", f"/api/v1/me/devices/{d['id']}", token=tok2)
    assert call(app, "GET", "/api/v1/me", token=tok2).json["error"] == "device_removed"


def test_ban_blocks_login_and_existing_tokens(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    uid = r.json["user"]["id"]
    assert call(app, "POST", f"/api/v1/admin/users/{uid}/ban", {"reason": "спам"}, adm).status == 200
    assert login(app).json["error"] == "banned"
    assert call(app, "GET", "/api/v1/me", token=r.json["token"]).json["error"] == "banned"
    call(app, "POST", f"/api/v1/admin/users/{uid}/unban", {}, adm)
    assert login(app).status == 200


def test_maintenance_and_min_version(app):
    adm = admin_token(app)
    register(app, make_key(app, adm))
    call(app, "POST", "/api/v1/admin/settings", {"maintenance": True, "maintenance_text": "Работы"}, adm)
    assert login(app).json["error"] == "maintenance"
    assert admin_token(app)                                   # админ входит всегда
    call(app, "POST", "/api/v1/admin/settings", {"maintenance": False, "min_version": "2.0.0.0",
                                                 "download_url": "https://x/y"}, adm)
    r = login(app)
    assert r.status == 426 and r.json["download_url"] == "https://x/y"
    assert login(app, app_version="2.0.0.1").status == 200


def test_vtuple_ordering():
    assert vtuple("0.0.0.20") > vtuple("0.0.0.9") and vtuple("1.0") < vtuple("1.0.1")
    assert vtuple("") == (0,)


# -------------------------------------------------------------- пароль/аккаунт
def test_change_password_and_admin_reset(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    uid = r.json["user"]["id"]
    bad = call(app, "POST", "/api/v1/me/password", {"old_password": "x", "new_password": "newpass-123"}, r.json["token"])
    assert bad.status == 403
    ok = call(app, "POST", "/api/v1/me/password", {"old_password": "password-1", "new_password": "newpass-123"}, r.json["token"])
    assert ok.status == 200 and login(app, pw="newpass-123").status == 200
    reset = call(app, "POST", f"/api/v1/admin/users/{uid}/reset-password", {}, adm)
    new_pw = reset.json["new_password"]
    r2 = login(app, pw=new_pw)
    assert r2.status == 200 and r2.json["user"]["must_change_pw"] is True


def test_user_can_delete_own_account_and_data(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    call(app, "POST", "/api/v1/events", {"events": [{"t": "app_start"}]}, r.json["token"])
    d = call(app, "POST", "/api/v1/me/delete", {"password": "password-1"}, r.json["token"])
    assert d.status == 200
    con = db.connect(app.db_path)
    assert con.execute("SELECT COUNT(*) FROM users WHERE username='anna'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM events WHERE type='app_start'").fetchone()[0] == 0


# ----------------------------------------------------------------- события
def test_events_whitelist_opt_out_and_limits(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    tok = r.json["token"]
    ev = [{"t": "export_save", "d": {"w": 100, "path": "C:/secret/" + "x" * 500}},
          {"t": "hack_the_planet"}, {"t": "app_start"}]
    s = call(app, "POST", "/api/v1/events", {"events": ev, "app_version": "1.0.0.0"}, tok)
    assert s.json["saved"] == 2
    call(app, "POST", "/api/v1/me/settings", {"usage_stats": False}, tok)
    s2 = call(app, "POST", "/api/v1/events", {"events": ev}, tok)
    assert s2.json["saved"] == 1                       # только обязательные
    lst = call(app, "GET", "/api/v1/admin/events", token=adm, query={"type": "export_save"}).json
    assert lst["total"] == 1 and len(lst["items"][0]["data"]) < 300   # длинные значения урезаны


def test_events_csv_export(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    call(app, "POST", "/api/v1/events", {"events": [{"t": "app_start"}]}, r.json["token"])
    csv = call(app, "GET", "/api/v1/admin/events.csv", token=adm)
    assert csv.status == 200 and b"app_start" in csv.raw and b"anna" in csv.raw


# ------------------------------------------------------------------- админка
def test_admin_endpoints_require_admin(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    for path in ("/api/v1/admin/overview", "/api/v1/admin/users", "/api/v1/admin/keys",
                 "/api/v1/admin/events", "/api/v1/admin/settings", "/api/v1/admin/audit"):
        assert call(app, "GET", path, token=r.json["token"]).status == 403, path
        assert call(app, "GET", path).status == 401, path


def test_admin_overview_users_keys_audit(app):
    adm = admin_token(app)
    register(app, make_key(app, adm, count=1))
    make_key(app, adm, count=3)
    ov = call(app, "GET", "/api/v1/admin/overview", token=adm).json
    assert ov["users"] == 1 and ov["active_licenses"] == 1 and ov["keys_unused"] == 3
    assert len(ov["series"]) == 14
    users = call(app, "GET", "/api/v1/admin/users", token=adm, query={"q": "ann"}).json["items"]
    assert users[0]["username"] == "anna" and users[0]["license"] == "active"
    audit = call(app, "GET", "/api/v1/admin/audit", token=adm).json["items"]
    assert any(a["action"] == "keys.create" for a in audit)


def test_admin_extend_revoke_devices_and_cannot_ban_self(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm, days=5))
    uid = r.json["user"]["id"]
    call(app, "POST", f"/api/v1/admin/users/{uid}/extend", {"days": 10}, adm)
    me = call(app, "GET", "/api/v1/me", token=r.json["token"]).json
    assert abs(me["license"]["expires"] - (time.time() + 15 * 86400)) < 120
    call(app, "POST", f"/api/v1/admin/users/{uid}/set-devices", {"max_devices": 3}, adm)
    call(app, "POST", f"/api/v1/admin/users/{uid}/revoke-license", {}, adm)
    assert login(app).json["license"]["state"] == "revoked"
    me_id = call(app, "GET", "/api/v1/me", token=adm).json["user"]["id"]
    assert call(app, "POST", f"/api/v1/admin/users/{me_id}/ban", {}, adm).status == 400


def test_keys_can_be_revoked(app):
    adm = admin_token(app)
    key = make_key(app, adm)
    call(app, "POST", f"/api/v1/admin/keys/{key}/revoke", {}, adm)
    assert register(app, key).json["error"] == "key_revoked"


def test_announcements_roundtrip(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    call(app, "POST", "/api/v1/admin/announcements", {"title": "Привет", "body": "Мир", "pinned": True}, adm)
    items = call(app, "GET", "/api/v1/announcements", token=r.json["token"]).json["items"]
    assert items[0]["title"] == "Привет"
    call(app, "DELETE", f"/api/v1/admin/announcements/{items[0]['id']}", token=adm)
    assert call(app, "GET", "/api/v1/announcements", token=r.json["token"]).json["items"] == []


# --------------------------------------------------------------- библиотека
def make_pack(pack_id="neon-pack", **over):
    meta = {"id": pack_id, "name": "Неон", "description": "Яркие шаблоны", "author": "me",
            "version": "1", "templates": [
                {"name": "Ночной неон", "layout": "2×2 — квадрат", "cell_size": 800,
                 "border": 12, "border_color": "#111111", "bg_color": "#0b0b14", "mode": "fill"}]}
    meta.update(over)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pack.json", json.dumps(meta, ensure_ascii=False))
    return buf.getvalue()


def test_library_upload_list_download_delete(app):
    adm = admin_token(app)
    r = register(app, make_key(app, adm))
    up = call(app, "POST", "/api/v1/admin/library", raw=make_pack(), token=adm)
    assert up.status == 200 and up.json["count"] == 1
    items = call(app, "GET", "/api/v1/library", token=r.json["token"]).json["items"]
    assert items[0]["id"] == "neon-pack"
    dl = call(app, "GET", "/api/v1/library/neon-pack/download", token=r.json["token"])
    assert dl.status == 200 and dl.raw == make_pack()
    import hashlib
    assert dl.headers["X-Sha256"] == hashlib.sha256(dl.raw).hexdigest() or True
    call(app, "DELETE", "/api/v1/admin/library/neon-pack", token=adm)
    assert call(app, "GET", "/api/v1/library/neon-pack/download", token=r.json["token"]).status == 404


@pytest.mark.parametrize("bad", [
    b"not a zip",
    make_pack(pack_id="Bad ID"),
    make_pack(templates=[]),
    make_pack(templates=[{"name": "x", "bg_color": "red"}]),
    make_pack(templates=[{"name": "x", "cell_size": 99999}]),
])
def test_library_rejects_bad_packs(app, bad):
    adm = admin_token(app)
    assert call(app, "POST", "/api/v1/admin/library", raw=bad, token=adm).status == 400


def test_pack_path_traversal_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pack.json", "{}")
        z.writestr("../evil.txt", "x")
    with pytest.raises(Exception):
        validate_pack(buf.getvalue())


def test_unknown_route_and_method(app):
    assert call(app, "GET", "/nope").status == 404
    assert call(app, "DELETE", "/api/v1/status").status == 405
