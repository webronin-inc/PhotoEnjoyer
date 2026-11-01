"""WSGI-приложение сервера PhotoEnjoyer.

Только стандартная библиотека + cryptography. Все ответы — JSON (кроме
скачивания пакета библиотеки и CSV-экспорта).

Принципы:
* пароли — scrypt, токены — подписанные Ed25519 (клиент проверяет их офлайн
  открытым ключом, поэтому приложение работает без сети в пределах «льготного»
  срока токена);
* лимит попыток входа, блокировка на 15 минут;
* IP не хранится — только его соль-хеш;
* события использования собираются только из белого списка, без содержимого фото.
"""
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import traceback
import zipfile
from urllib.parse import parse_qs, unquote

from . import db, security

API = "/api/v1"
TOKEN_TTL = 7 * 24 * 3600                 # «льготный» срок работы без сети
MAX_BODY = 12 * 1024 * 1024
LOCK_WINDOW = 15 * 60
LOCK_USER_FAILS = 5
LOCK_IP_FAILS = 30
MAX_PACK_BYTES = 8 * 1024 * 1024

# события, которые собираем (всё остальное отбрасывается)
ESSENTIAL_EVENTS = {"app_start", "app_exit", "login", "error"}
USAGE_EVENTS = {"export_save", "export_copy", "batch_run", "template_apply",
                "library_install", "caption_style", "editor_open", "pdf_export",
                "watermark_apply"}
ALL_EVENTS = ESSENTIAL_EVENTS | USAGE_EVENTS | {"register", "key_activated"}

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,24}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
PACK_ID_RE = re.compile(r"^[a-z0-9_\-]{3,40}$")


class HttpError(Exception):
    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def vtuple(text):
    out = []
    for part in re.split(r"[.\-+]", str(text or "0")):
        if part.isdigit():
            out.append(int(part))
        else:
            break
    return tuple(out) or (0,)


class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = unquote(environ.get("PATH_INFO", "/"))
        self.query = {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
        self.ip = (environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                   or environ.get("REMOTE_ADDR", ""))
        self.auth_header = environ.get("HTTP_AUTHORIZATION", "")
        self.content_type = environ.get("CONTENT_TYPE", "")
        self._body = None
        self.user = None            # строка users после auth
        self.claims = None

    @property
    def body(self):
        if self._body is None:
            try:
                n = int(self.environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                n = 0
            if n > MAX_BODY:
                raise HttpError(413, "too_large", "Слишком большой запрос")
            self._body = self.environ["wsgi.input"].read(n) if n else b""
        return self._body

    def json(self):
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except Exception:
            raise HttpError(400, "bad_json", "Некорректный JSON")
        if not isinstance(data, dict):
            raise HttpError(400, "bad_json", "Ожидался JSON-объект")
        return data


class App:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(os.path.join(data_dir, "library"), exist_ok=True)
        self.db_path = os.path.join(data_dir, "photoenjoyer.sqlite3")
        self.priv = security.load_or_create_keypair(data_dir)
        self.pub = self.priv.public_key()
        self.ip_salt = hashlib.sha256(
            open(os.path.join(data_dir, "license_private.pem"), "rb").read()
        ).hexdigest()[:24]
        con = db.connect(self.db_path)
        db.init_db(con)
        self._bootstrap_admin(con)
        con.close()
        self.routes = []
        self._register_routes()

    # ------------------------------------------------------------ служебное
    def _bootstrap_admin(self, con):
        """Первый администратор — из переменных окружения (удобно на хостинге)."""
        user, pw = os.environ.get("PE_ADMIN_USER"), os.environ.get("PE_ADMIN_PASSWORD")
        if not user or not pw:
            return
        if con.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            return
        self.create_user(con, user, pw, role="admin", max_devices=10)

    def create_user(self, con, username, password, role="user", max_devices=1):
        con.execute(
            "INSERT INTO users(username, pw, role, created_at, max_devices, lic_active) "
            "VALUES(?,?,?,?,?,?)",
            (username, security.hash_password(password), role, db.now(), max_devices,
             1 if role == "admin" else 0))
        con.commit()
        return con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    def route(self, method, pattern):
        rx = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

        def deco(fn):
            self.routes.append((method, rx, fn))
            return fn
        return deco

    def __call__(self, environ, start_response):
        req = Request(environ)
        con = db.connect(self.db_path)
        try:
            status, payload, headers = self.dispatch(req, con)
        except HttpError as e:
            status = e.status
            payload = {"ok": False, "error": e.code, "message": e.message, **e.extra}
            headers = {}
        except Exception:
            traceback.print_exc(file=sys.stderr)
            status, payload, headers = 500, {"ok": False, "error": "server_error",
                                             "message": "Внутренняя ошибка сервера"}, {}
        finally:
            con.close()
        if isinstance(payload, (bytes, bytearray)):
            body = bytes(payload)
            ctype = headers.pop("Content-Type", "application/octet-stream")
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        out = [("Content-Type", ctype), ("Content-Length", str(len(body))),
               ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")]
        out += list(headers.items())
        start_response(f"{status} {_REASONS.get(status, 'OK')}", out)
        return [body]

    def dispatch(self, req, con):
        path_matched = False
        for method, rx, fn in self.routes:
            m = rx.match(req.path)
            if not m:
                continue
            path_matched = True
            if method != req.method:
                continue
            result = fn(req, con, **m.groupdict())
            if isinstance(result, tuple):
                return result
            return 200, {"ok": True, **(result or {})}, {}
        if path_matched:
            raise HttpError(405, "method_not_allowed", "Метод не поддерживается")
        raise HttpError(404, "not_found", "Не найдено")

    # ------------------------------------------------------------ лицензия/токен
    @staticmethod
    def lic_state(user, now=None):
        now = now or db.now()
        if user["role"] == "admin":
            return "active"
        if not user["lic_active"]:
            return "revoked" if user["lic_plan"] else "none"
        exp = user["lic_expires"]
        if exp is not None and exp <= now:
            return "expired"
        return "active"

    def issue_token(self, user, hwid):
        now = db.now()
        payload = {
            "v": 1, "uid": user["id"], "u": user["username"], "role": user["role"],
            "dev": hwid, "iat": now, "exp": now + TOKEN_TTL,
            "lic": {"state": self.lic_state(user, now), "plan": user["lic_plan"],
                    "exp": user["lic_expires"], "devices": user["max_devices"]},
        }
        return security.sign_token(self.priv, payload), payload

    def me_payload(self, con, user):
        devs = con.execute(
            "SELECT id, name, first_seen, last_seen, last_version FROM devices "
            "WHERE user_id=? ORDER BY last_seen DESC", (user["id"],)).fetchall()
        return {
            "user": {"id": user["id"], "username": user["username"], "role": user["role"],
                     "created_at": user["created_at"], "usage_stats": bool(user["usage_stats"]),
                     "must_change_pw": bool(user["must_change_pw"])},
            "license": {"state": self.lic_state(user), "plan": user["lic_plan"],
                        "expires": user["lic_expires"], "max_devices": user["max_devices"]},
            "devices": [dict(d) for d in devs],
        }

    def auth(self, req, con, license_required=True, admin=False):
        h = req.auth_header
        if not h.lower().startswith("bearer "):
            raise HttpError(401, "unauthorized", "Требуется вход")
        claims = security.verify_token(self.pub, h[7:].strip())
        if not claims:
            raise HttpError(401, "token_invalid", "Сессия недействительна, войдите заново")
        user = con.execute("SELECT * FROM users WHERE id=?", (claims["uid"],)).fetchone()
        if not user:
            raise HttpError(401, "token_invalid", "Аккаунт не найден")
        if user["banned"]:
            raise HttpError(403, "banned", "Аккаунт заблокирован",
                            reason=user["ban_reason"])
        dev = con.execute("SELECT id FROM devices WHERE user_id=? AND hwid=?",
                          (user["id"], claims.get("dev", ""))).fetchone()
        if not dev:
            raise HttpError(401, "device_removed", "Это устройство отключено от аккаунта")
        if admin and user["role"] != "admin":
            raise HttpError(403, "forbidden", "Только для администратора")
        if license_required and self.lic_state(user) != "active":
            raise HttpError(403, "license_" + self.lic_state(user),
                            "Лицензия недействительна")
        req.user, req.claims, req.device_id = user, claims, dev["id"]
        return user

    def audit(self, con, req, action, target="", detail=""):
        con.execute("INSERT INTO audit(ts, admin_id, action, target, detail) VALUES(?,?,?,?,?)",
                    (db.now(), req.user["id"] if req.user else None, action, str(target),
                     str(detail)[:500]))

    def log_event(self, con, user_id, etype, version="", data=None, ip=""):
        con.execute("INSERT INTO events(ts, user_id, type, version, data, ip) VALUES(?,?,?,?,?,?)",
                    (db.now(), user_id, etype, version[:20],
                     json.dumps(data, ensure_ascii=False)[:2000] if data else "",
                     security.hash_ip(self.ip_salt, ip) if ip else ""))

    # ------------------------------------------------------------ вход
    def _check_lock(self, con, username, ip):
        since = db.now() - LOCK_WINDOW
        u = con.execute("SELECT COUNT(*) c, MAX(ts) t FROM login_attempts "
                        "WHERE ok=0 AND ts>? AND username=? COLLATE NOCASE",
                        (since, username)).fetchone()
        i = con.execute("SELECT COUNT(*) c FROM login_attempts WHERE ok=0 AND ts>? AND ip=?",
                        (since, security.hash_ip(self.ip_salt, ip))).fetchone()
        if u["c"] >= LOCK_USER_FAILS or i["c"] >= LOCK_IP_FAILS:
            retry = max(30, LOCK_WINDOW - (db.now() - (u["t"] or db.now())))
            raise HttpError(429, "locked", "Слишком много неудачных попыток. "
                            "Попробуйте через несколько минут.", retry_after=int(retry))

    def _attempt(self, con, username, ip, ok):
        con.execute("INSERT INTO login_attempts(ts, username, ip, ok) VALUES(?,?,?,?)",
                    (db.now(), username[:40], security.hash_ip(self.ip_salt, ip), 1 if ok else 0))
        if ok:        # успешный вход «обнуляет» неудачи этого логина
            con.execute("DELETE FROM login_attempts WHERE ok=0 AND username=? COLLATE NOCASE",
                        (username,))
        con.execute("DELETE FROM login_attempts WHERE ts<?", (db.now() - 24 * 3600,))
        con.commit()

    def _gate_checks(self, con, body, user=None):
        s = db.get_settings(con)
        if s["maintenance"] == "1" and not (user is not None and user["role"] == "admin"):
            raise HttpError(503, "maintenance", s["maintenance_text"])
        ver = str(body.get("app_version", ""))
        if ver and vtuple(ver) < vtuple(s["min_version"]) and not (
                user is not None and user["role"] == "admin"):
            raise HttpError(426, "update_required",
                            "Нужно обновить программу до версии " + s["min_version"],
                            min_version=s["min_version"], download_url=s["download_url"])

    def _bind_device(self, con, user, body):
        hwid = str(body.get("hwid", ""))
        if not re.fullmatch(r"[0-9a-f]{16,64}", hwid):
            raise HttpError(400, "bad_device", "Не удалось определить устройство")
        name = str(body.get("device_name", ""))[:40]
        ver = str(body.get("app_version", ""))[:20]
        row = con.execute("SELECT id FROM devices WHERE user_id=? AND hwid=?",
                          (user["id"], hwid)).fetchone()
        if row:
            con.execute("UPDATE devices SET last_seen=?, last_version=?, name=? WHERE id=?",
                        (db.now(), ver, name or "Устройство", row["id"]))
        else:
            n = con.execute("SELECT COUNT(*) c FROM devices WHERE user_id=?",
                            (user["id"],)).fetchone()["c"]
            if n >= max(1, user["max_devices"]):
                devs = con.execute("SELECT id, name, last_seen FROM devices WHERE user_id=? "
                                   "ORDER BY last_seen DESC", (user["id"],)).fetchall()
                raise HttpError(403, "device_limit",
                                "Достигнут лимит устройств для этой лицензии",
                                devices=[dict(d) for d in devs], max_devices=user["max_devices"])
            con.execute("INSERT INTO devices(user_id, hwid, name, first_seen, last_seen, "
                        "last_version) VALUES(?,?,?,?,?,?)",
                        (user["id"], hwid, name or "Устройство", db.now(), db.now(), ver))
        return hwid

    def _session_response(self, con, user, hwid, req):
        token, payload = self.issue_token(user, hwid)
        con.execute("UPDATE users SET last_login=? WHERE id=?", (db.now(), user["id"]))
        self.log_event(con, user["id"], "login", str(req.json().get("app_version", "")),
                       {"dev": hwid[:6]}, req.ip)
        con.commit()
        fresh = con.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        return {"token": token, "server_time": db.now(), "expires": payload["exp"],
                **self.me_payload(con, fresh)}

    # ------------------------------------------------------------ маршруты
    def _register_routes(self):
        r = self.route

        @r("GET", API + "/status")
        def status(req, con):
            s = db.get_settings(con)
            return {"server_time": db.now(), "maintenance": s["maintenance"] == "1",
                    "maintenance_text": s["maintenance_text"], "min_version": s["min_version"],
                    "latest_version": s["latest_version"], "download_url": s["download_url"],
                    "support_contact": s["support_contact"], "motd": s["motd"]}

        @r("POST", API + "/auth/register")
        def register(req, con):
            b = req.json()
            self._gate_checks(con, b)
            username = str(b.get("username", "")).strip()
            password = str(b.get("password", ""))
            key = security.normalize_key(b.get("key", ""))
            if not b.get("consent"):
                raise HttpError(400, "consent_required",
                                "Нужно согласиться с условиями использования")
            if not USERNAME_RE.match(username):
                raise HttpError(400, "bad_username", "Логин: 3–24 символа, латиница, цифры, _ . -")
            if len(password) < 8:
                raise HttpError(400, "weak_password", "Пароль — минимум 8 символов")
            if not key:
                raise HttpError(400, "invalid_key", "Ключ введён неверно")
            self._check_lock(con, "register:" + req.ip, req.ip)
            row = con.execute("SELECT * FROM license_keys WHERE key=?", (key,)).fetchone()
            if not row:
                self._attempt(con, "register:" + req.ip, req.ip, False)
                raise HttpError(400, "invalid_key", "Такого ключа нет")
            if row["revoked"]:
                raise HttpError(400, "key_revoked", "Этот ключ отозван")
            if row["used_by"]:
                raise HttpError(400, "key_used", "Этот ключ уже использован")
            if con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise HttpError(409, "username_taken", "Этот логин уже занят")
            con.execute(
                "INSERT INTO users(username, pw, created_at, max_devices) VALUES(?,?,?,?)",
                (username, security.hash_password(password), db.now(), row["max_devices"]))
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            self._apply_key(con, user, row)
            hwid = self._bind_device(con, user, b)
            self.log_event(con, user["id"], "register", str(b.get("app_version", "")), None, req.ip)
            con.commit()
            user = con.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            return self._session_response(con, user, hwid, req)

        @r("POST", API + "/auth/login")
        def login(req, con):
            b = req.json()
            username = str(b.get("username", "")).strip()
            password = str(b.get("password", ""))
            ip = req.ip
            self._check_lock(con, username, ip)
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not user or not security.verify_password(password, user["pw"]):
                self._attempt(con, username, ip, False)
                raise HttpError(401, "bad_credentials", "Неверный логин или пароль")
            self._attempt(con, username, ip, True)
            if user["banned"]:
                raise HttpError(403, "banned", "Аккаунт заблокирован", reason=user["ban_reason"])
            self._gate_checks(con, b, user)
            hwid = self._bind_device(con, user, b)
            return self._session_response(con, user, hwid, req)

        @r("POST", API + "/auth/release-device")
        def release_device(req, con):
            """Снять устройство при достигнутом лимите — по логину и паролю."""
            b = req.json()
            username = str(b.get("username", "")).strip()
            self._check_lock(con, username, req.ip)
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not user or not security.verify_password(str(b.get("password", "")), user["pw"]):
                self._attempt(con, username, req.ip, False)
                raise HttpError(401, "bad_credentials", "Неверный логин или пароль")
            con.execute("DELETE FROM devices WHERE id=? AND user_id=?",
                        (int(b.get("device_id", 0)), user["id"]))
            con.commit()
            return {}

        @r("POST", API + "/auth/refresh")
        def refresh(req, con):
            user = self.auth(req, con, license_required=False)
            self._gate_checks(con, req.json(), user)
            hwid = req.claims["dev"]
            con.execute("UPDATE devices SET last_seen=?, last_version=? WHERE id=?",
                        (db.now(), str(req.json().get("app_version", ""))[:20], req.device_id))
            token, payload = self.issue_token(user, hwid)
            con.commit()
            return {"token": token, "server_time": db.now(), "expires": payload["exp"],
                    **self.me_payload(con, user)}

        @r("GET", API + "/me")
        def me(req, con):
            user = self.auth(req, con, license_required=False)
            return self.me_payload(con, user)

        @r("POST", API + "/me/password")
        def change_password(req, con):
            user = self.auth(req, con, license_required=False)
            b = req.json()
            if not security.verify_password(str(b.get("old_password", "")), user["pw"]):
                raise HttpError(403, "bad_credentials", "Текущий пароль неверный")
            new = str(b.get("new_password", ""))
            if len(new) < 8:
                raise HttpError(400, "weak_password", "Пароль — минимум 8 символов")
            con.execute("UPDATE users SET pw=?, must_change_pw=0 WHERE id=?",
                        (security.hash_password(new), user["id"]))
            con.commit()
            return {}

        @r("POST", API + "/me/activate-key")
        def activate_key(req, con):
            user = self.auth(req, con, license_required=False)
            key = security.normalize_key(req.json().get("key", ""))
            row = con.execute("SELECT * FROM license_keys WHERE key=?", (key,)).fetchone() if key else None
            if not row:
                raise HttpError(400, "invalid_key", "Такого ключа нет")
            if row["revoked"]:
                raise HttpError(400, "key_revoked", "Этот ключ отозван")
            if row["used_by"]:
                raise HttpError(400, "key_used", "Этот ключ уже использован")
            self._apply_key(con, user, row)
            self.log_event(con, user["id"], "key_activated", "", {"plan": row["plan"]}, req.ip)
            con.commit()
            fresh = con.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            token, payload = self.issue_token(fresh, req.claims["dev"])
            return {"token": token, "expires": payload["exp"], **self.me_payload(con, fresh)}

        @r("DELETE", API + "/me/devices/<device_id>")
        def remove_device(req, con, device_id):
            user = self.auth(req, con, license_required=False)
            con.execute("DELETE FROM devices WHERE id=? AND user_id=?", (int(device_id), user["id"]))
            con.commit()
            return {"removed_current": int(device_id) == req.device_id}

        @r("POST", API + "/me/settings")
        def my_settings(req, con):
            user = self.auth(req, con, license_required=False)
            b = req.json()
            if "usage_stats" in b:
                con.execute("UPDATE users SET usage_stats=? WHERE id=?",
                            (1 if b["usage_stats"] else 0, user["id"]))
                con.commit()
            return {}

        @r("POST", API + "/me/delete")
        def delete_me(req, con):
            """Удаление своего аккаунта и всех своих данных (право на удаление)."""
            user = self.auth(req, con, license_required=False)
            if not security.verify_password(str(req.json().get("password", "")), user["pw"]):
                raise HttpError(403, "bad_credentials", "Пароль неверный")
            self._delete_user(con, user["id"])
            con.commit()
            return {}

        @r("POST", API + "/events")
        def events(req, con):
            user = self.auth(req, con)
            items = req.json().get("events", [])
            if not isinstance(items, list):
                raise HttpError(400, "bad_json", "events должен быть списком")
            ver = str(req.json().get("app_version", ""))
            saved = 0
            for it in items[:50]:
                if not isinstance(it, dict):
                    continue
                t = str(it.get("t", ""))
                if t not in ALL_EVENTS:
                    continue
                if t in USAGE_EVENTS and not user["usage_stats"]:
                    continue
                data = it.get("d") if isinstance(it.get("d"), dict) else None
                if data:
                    data = {str(k)[:24]: (v if isinstance(v, (int, float, bool)) else str(v)[:80])
                            for k, v in list(data.items())[:12]}
                self.log_event(con, user["id"], t, ver, data, req.ip)
                saved += 1
            con.commit()
            return {"saved": saved}

        @r("GET", API + "/announcements")
        def announcements(req, con):
            self.auth(req, con, license_required=False)
            rows = con.execute("SELECT id, ts, title, body, level, pinned FROM announcements "
                               "ORDER BY pinned DESC, ts DESC LIMIT 30").fetchall()
            return {"items": [dict(x) for x in rows]}

        @r("GET", API + "/library")
        def library_list(req, con):
            self.auth(req, con)
            rows = con.execute("SELECT * FROM library ORDER BY created_at DESC").fetchall()
            return {"items": [dict(x) for x in rows]}

        @r("GET", API + "/library/<pack_id>/download")
        def library_download(req, con, pack_id):
            self.auth(req, con)
            row = con.execute("SELECT * FROM library WHERE id=?", (pack_id,)).fetchone()
            path = os.path.join(self.data_dir, "library", pack_id + ".zip")
            if not row or not PACK_ID_RE.match(pack_id) or not os.path.exists(path):
                raise HttpError(404, "not_found", "Пакет не найден")
            with open(path, "rb") as f:
                data = f.read()
            con.execute("UPDATE library SET downloads=downloads+1 WHERE id=?", (pack_id,))
            con.commit()
            return 200, data, {"Content-Type": "application/zip", "X-Sha256": row["sha256"]}

        self._register_admin_routes()

    # ------------------------------------------------------------ лицензии
    def _apply_key(self, con, user, key_row):
        now = db.now()
        days = key_row["days"]
        cur_exp = user["lic_expires"]
        active = bool(user["lic_active"]) and (cur_exp is None or cur_exp > now)
        if days == 0:
            new_exp = None
        elif active and cur_exp is None:
            new_exp = None                              # бессрочная остаётся бессрочной
        else:
            base = cur_exp if (active and cur_exp) else now
            new_exp = base + days * 86400
        con.execute("UPDATE users SET lic_plan=?, lic_active=1, lic_expires=?, "
                    "max_devices=MAX(max_devices, ?) WHERE id=?",
                    (key_row["plan"], new_exp, key_row["max_devices"], user["id"]))
        con.execute("UPDATE license_keys SET used_by=?, used_at=? WHERE key=?",
                    (user["id"], now, key_row["key"]))

    def _delete_user(self, con, uid):
        con.execute("DELETE FROM devices WHERE user_id=?", (uid,))
        con.execute("DELETE FROM events WHERE user_id=?", (uid,))
        con.execute("UPDATE license_keys SET used_by=NULL WHERE used_by=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))

    # ------------------------------------------------------------ админ
    def _register_admin_routes(self):
        r = self.route
        A = API + "/admin"

        def adm(req, con):
            return self.auth(req, con, license_required=False, admin=True)

        @r("GET", A + "/overview")
        def overview(req, con):
            adm(req, con)
            now = db.now()
            q = lambda sql, *a: con.execute(sql, a).fetchone()[0]
            day = 86400
            series = []
            for i in range(13, -1, -1):
                t0 = (now // day - i) * day
                series.append({"day": t0, "events": q(
                    "SELECT COUNT(*) FROM events WHERE ts>=? AND ts<?", t0, t0 + day),
                    "logins": q("SELECT COUNT(*) FROM events WHERE type='login' AND ts>=? AND ts<?",
                                t0, t0 + day)})
            top = con.execute("SELECT type, COUNT(*) c FROM events WHERE ts>? GROUP BY type "
                              "ORDER BY c DESC LIMIT 8", (now - 7 * day,)).fetchall()
            return {
                "users": q("SELECT COUNT(*) FROM users WHERE role='user'"),
                "active_licenses": q("SELECT COUNT(*) FROM users WHERE role='user' AND lic_active=1 "
                                     "AND (lic_expires IS NULL OR lic_expires>?)", now),
                "expiring_7d": q("SELECT COUNT(*) FROM users WHERE role='user' AND lic_active=1 "
                                 "AND lic_expires BETWEEN ? AND ?", now, now + 7 * day),
                "banned": q("SELECT COUNT(*) FROM users WHERE banned=1"),
                "keys_total": q("SELECT COUNT(*) FROM license_keys"),
                "keys_unused": q("SELECT COUNT(*) FROM license_keys WHERE used_by IS NULL AND revoked=0"),
                "devices": q("SELECT COUNT(*) FROM devices"),
                "online_24h": q("SELECT COUNT(DISTINCT user_id) FROM events WHERE ts>?", now - day),
                "online_7d": q("SELECT COUNT(DISTINCT user_id) FROM events WHERE ts>?", now - 7 * day),
                "events_24h": q("SELECT COUNT(*) FROM events WHERE ts>?", now - day),
                "failed_logins_24h": q("SELECT COUNT(*) FROM login_attempts WHERE ok=0 AND ts>?",
                                       now - day),
                "series": series, "top_events": [dict(t) for t in top],
                "library": q("SELECT COUNT(*) FROM library"),
            }

        @r("GET", A + "/users")
        def users(req, con):
            adm(req, con)
            qs = req.query.get("q", "").strip()
            sql = ("SELECT u.*, (SELECT COUNT(*) FROM devices d WHERE d.user_id=u.id) devs, "
                   "(SELECT MAX(ts) FROM events e WHERE e.user_id=u.id) last_event "
                   "FROM users u")
            args = []
            if qs:
                sql += " WHERE u.username LIKE ? OR u.note LIKE ?"
                args = [f"%{qs}%", f"%{qs}%"]
            sql += " ORDER BY u.created_at DESC LIMIT 500"
            out = []
            for u in con.execute(sql, args).fetchall():
                out.append({"id": u["id"], "username": u["username"], "role": u["role"],
                            "banned": bool(u["banned"]), "ban_reason": u["ban_reason"],
                            "created_at": u["created_at"], "last_login": u["last_login"],
                            "license": self.lic_state(u), "plan": u["lic_plan"],
                            "expires": u["lic_expires"], "max_devices": u["max_devices"],
                            "devices": u["devs"], "last_event": u["last_event"],
                            "note": u["note"]})
            return {"items": out}

        @r("GET", A + "/users/<uid>/devices")
        def user_devices(req, con, uid):
            adm(req, con)
            rows = con.execute("SELECT id, name, first_seen, last_seen, last_version FROM devices "
                               "WHERE user_id=? ORDER BY last_seen DESC", (int(uid),)).fetchall()
            return {"items": [dict(x) for x in rows]}

        @r("POST", A + "/users/<uid>/<action>")
        def user_action(req, con, uid, action):
            admin = adm(req, con)
            uid = int(uid)
            u = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not u:
                raise HttpError(404, "not_found", "Пользователь не найден")
            b = req.json()
            extra = {}
            if u["role"] == "admin" and uid != admin["id"] and action in ("ban", "delete"):
                raise HttpError(403, "forbidden", "Нельзя трогать другого администратора")
            if action == "ban":
                if uid == admin["id"]:
                    raise HttpError(400, "bad_request", "Нельзя заблокировать себя")
                con.execute("UPDATE users SET banned=1, ban_reason=? WHERE id=?",
                            (str(b.get("reason", ""))[:200], uid))
            elif action == "unban":
                con.execute("UPDATE users SET banned=0, ban_reason='' WHERE id=?", (uid,))
            elif action == "reset-password":
                pw = security.random_password()
                con.execute("UPDATE users SET pw=?, must_change_pw=1 WHERE id=?",
                            (security.hash_password(pw), uid))
                extra["new_password"] = pw
            elif action == "extend":
                days = int(b.get("days", 0))
                if not -3650 <= days <= 3650 or days == 0:
                    raise HttpError(400, "bad_request", "Укажите дни (не 0)")
                now = db.now()
                base = u["lic_expires"] if (u["lic_active"] and u["lic_expires"]
                                            and u["lic_expires"] > now) else now
                con.execute("UPDATE users SET lic_active=1, lic_expires=?, "
                            "lic_plan=CASE WHEN lic_plan='' THEN 'Выдано вручную' ELSE lic_plan END "
                            "WHERE id=?", (base + days * 86400, uid))
            elif action == "unlimited":
                con.execute("UPDATE users SET lic_active=1, lic_expires=NULL, "
                            "lic_plan=CASE WHEN lic_plan='' THEN 'Бессрочная' ELSE lic_plan END "
                            "WHERE id=?", (uid,))
            elif action == "revoke-license":
                con.execute("UPDATE users SET lic_active=0 WHERE id=?", (uid,))
            elif action == "set-devices":
                n = int(b.get("max_devices", 1))
                if not 1 <= n <= 50:
                    raise HttpError(400, "bad_request", "От 1 до 50 устройств")
                con.execute("UPDATE users SET max_devices=? WHERE id=?", (n, uid))
            elif action == "reset-devices":
                con.execute("DELETE FROM devices WHERE user_id=?", (uid,))
            elif action == "note":
                con.execute("UPDATE users SET note=? WHERE id=?", (str(b.get("note", ""))[:200], uid))
            elif action == "set-role":
                role = b.get("role")
                if role not in ("user", "admin") or uid == admin["id"]:
                    raise HttpError(400, "bad_request", "Недопустимая смена роли")
                con.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
            elif action == "delete":
                if uid == admin["id"]:
                    raise HttpError(400, "bad_request", "Нельзя удалить себя")
                self._delete_user(con, uid)
            else:
                raise HttpError(404, "not_found", "Неизвестное действие")
            self.audit(con, req, "user." + action, f"{u['username']}#{uid}", json.dumps(
                {k: v for k, v in b.items() if k != "password"}, ensure_ascii=False))
            con.commit()
            return extra

        @r("GET", A + "/keys")
        def keys(req, con):
            adm(req, con)
            rows = con.execute(
                "SELECT k.*, u.username used_by_name FROM license_keys k "
                "LEFT JOIN users u ON u.id=k.used_by ORDER BY k.created_at DESC LIMIT 1000").fetchall()
            return {"items": [dict(x) for x in rows]}

        @r("POST", A + "/keys")
        def keys_create(req, con):
            admin = adm(req, con)
            b = req.json()
            count = int(b.get("count", 1))
            days = int(b.get("days", 30))
            devices = int(b.get("max_devices", 1))
            plan = str(b.get("plan", "Стандарт"))[:40] or "Стандарт"
            if not 1 <= count <= 200 or not 0 <= days <= 3650 or not 1 <= devices <= 50:
                raise HttpError(400, "bad_request", "Проверьте количество, срок и устройства")
            out = []
            for _ in range(count):
                k = security.new_license_key()
                con.execute("INSERT INTO license_keys(key, plan, days, max_devices, created_at, "
                            "created_by, note) VALUES(?,?,?,?,?,?,?)",
                            (k, plan, days, devices, db.now(), admin["id"],
                             str(b.get("note", ""))[:100]))
                out.append(k)
            self.audit(con, req, "keys.create", f"{count}x", f"{plan}, {days}д, {devices}уст.")
            con.commit()
            return {"keys": out}

        @r("POST", A + "/keys/<key>/revoke")
        def key_revoke(req, con, key):
            adm(req, con)
            con.execute("UPDATE license_keys SET revoked=1 WHERE key=?", (key,))
            self.audit(con, req, "keys.revoke", key)
            con.commit()
            return {}

        def event_filters(req):
            where, args = ["1=1"], []
            q = req.query
            if q.get("user"):
                where.append("u.username LIKE ?")
                args.append(f"%{q['user']}%")
            if q.get("type"):
                where.append("e.type=?")
                args.append(q["type"])
            if q.get("since"):
                where.append("e.ts>=?")
                args.append(int(q["since"]))
            if q.get("until"):
                where.append("e.ts<=?")
                args.append(int(q["until"]))
            return " AND ".join(where), args

        @r("GET", A + "/events")
        def events_list(req, con):
            adm(req, con)
            where, args = event_filters(req)
            limit = min(500, int(req.query.get("limit", 100)))
            offset = max(0, int(req.query.get("offset", 0)))
            rows = con.execute(
                "SELECT e.id, e.ts, e.type, e.version, e.data, e.ip, u.username FROM events e "
                f"LEFT JOIN users u ON u.id=e.user_id WHERE {where} "
                "ORDER BY e.id DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
            total = con.execute("SELECT COUNT(*) FROM events e LEFT JOIN users u "
                                f"ON u.id=e.user_id WHERE {where}", args).fetchone()[0]
            return {"items": [dict(x) for x in rows], "total": total}

        @r("GET", A + "/events.csv")
        def events_csv(req, con):
            adm(req, con)
            where, args = event_filters(req)
            rows = con.execute(
                "SELECT e.ts, u.username, e.type, e.version, e.data FROM events e "
                f"LEFT JOIN users u ON u.id=e.user_id WHERE {where} "
                "ORDER BY e.id DESC LIMIT 20000", args).fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["time_utc", "user", "type", "version", "data"])
            for x in rows:
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(x["ts"])),
                            x["username"] or "", x["type"], x["version"], x["data"]])
            return 200, buf.getvalue().encode("utf-8-sig"), {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": "attachment; filename=events.csv"}

        @r("GET", A + "/audit")
        def audit_list(req, con):
            adm(req, con)
            rows = con.execute("SELECT a.ts, a.action, a.target, a.detail, u.username admin "
                               "FROM audit a LEFT JOIN users u ON u.id=a.admin_id "
                               "ORDER BY a.id DESC LIMIT 300").fetchall()
            return {"items": [dict(x) for x in rows]}

        @r("POST", A + "/announcements")
        def ann_create(req, con):
            adm(req, con)
            b = req.json()
            title = str(b.get("title", "")).strip()[:120]
            if not title:
                raise HttpError(400, "bad_request", "Нужен заголовок")
            level = b.get("level") if b.get("level") in ("info", "warn", "success") else "info"
            con.execute("INSERT INTO announcements(ts, title, body, level, pinned) VALUES(?,?,?,?,?)",
                        (db.now(), title, str(b.get("body", ""))[:2000], level,
                         1 if b.get("pinned") else 0))
            self.audit(con, req, "announcement.create", title)
            con.commit()
            return {}

        @r("DELETE", A + "/announcements/<aid>")
        def ann_delete(req, con, aid):
            adm(req, con)
            con.execute("DELETE FROM announcements WHERE id=?", (int(aid),))
            self.audit(con, req, "announcement.delete", aid)
            con.commit()
            return {}

        @r("GET", A + "/settings")
        def settings_get(req, con):
            adm(req, con)
            return {"settings": db.get_settings(con)}

        @r("POST", A + "/settings")
        def settings_set(req, con):
            adm(req, con)
            b = req.json()
            for k in db.DEFAULT_SETTINGS:
                if k in b:
                    v = b[k]
                    if k == "maintenance":
                        v = "1" if v in (True, 1, "1", "true") else "0"
                    db.set_setting(con, k, str(v)[:300])
            self.audit(con, req, "settings", ",".join(k for k in b if k in db.DEFAULT_SETTINGS))
            con.commit()
            return {"settings": db.get_settings(con)}

        @r("POST", A + "/library")
        def library_upload(req, con):
            adm(req, con)
            data = req.body
            if len(data) > MAX_PACK_BYTES:
                raise HttpError(413, "too_large", "Пакет больше 8 МБ")
            meta = validate_pack(data)
            path = os.path.join(self.data_dir, "library", meta["id"] + ".zip")
            with open(path, "wb") as f:
                f.write(data)
            con.execute(
                "INSERT INTO library(id, name, description, author, version, kind, count, size, "
                "sha256, created_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, description=excluded.description, author=excluded.author, "
                "version=excluded.version, count=excluded.count, size=excluded.size, "
                "sha256=excluded.sha256, created_at=excluded.created_at",
                (meta["id"], meta["name"], meta["description"], meta["author"], meta["version"],
                 meta["kind"], len(meta["templates"]), len(data),
                 hashlib.sha256(data).hexdigest(), db.now()))
            self.audit(con, req, "library.upload", meta["id"])
            con.commit()
            return {"id": meta["id"], "count": len(meta["templates"])}

        @r("DELETE", A + "/library/<pack_id>")
        def library_delete(req, con, pack_id):
            adm(req, con)
            con.execute("DELETE FROM library WHERE id=?", (pack_id,))
            try:
                if PACK_ID_RE.match(pack_id):
                    os.remove(os.path.join(self.data_dir, "library", pack_id + ".zip"))
            except OSError:
                pass
            self.audit(con, req, "library.delete", pack_id)
            con.commit()
            return {}


# ---------------------------------------------------------------- пакеты
def validate_pack(data):
    """Проверяет zip с pack.json (шаблоны оформления) и возвращает метаданные."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        if "pack.json" not in names or len(names) > 20:
            raise ValueError("нужен pack.json (и не больше 20 файлов)")
        if any(n.startswith("/") or ".." in n for n in names):
            raise ValueError("недопустимые пути в архиве")
        if sum(i.file_size for i in zf.infolist()) > 4 * 1024 * 1024:
            raise ValueError("слишком большой распакованный размер")
        meta = json.loads(zf.read("pack.json").decode("utf-8"))
    except zipfile.BadZipFile:
        raise HttpError(400, "bad_pack", "Это не zip-архив")
    except (ValueError, KeyError) as e:
        raise HttpError(400, "bad_pack", f"Пакет не подходит: {e}")
    if not isinstance(meta, dict) or not PACK_ID_RE.match(str(meta.get("id", ""))):
        raise HttpError(400, "bad_pack", "id пакета: 3–40 символов a-z 0-9 _ -")
    name = str(meta.get("name", "")).strip()[:60]
    if not name:
        raise HttpError(400, "bad_pack", "У пакета нет названия")
    tpls = meta.get("templates")
    if not isinstance(tpls, list) or not 1 <= len(tpls) <= 100:
        raise HttpError(400, "bad_pack", "Нужен список templates (1–100 шт.)")
    clean = []
    for t in tpls:
        if not isinstance(t, dict) or not str(t.get("name", "")).strip():
            raise HttpError(400, "bad_pack", "У каждого шаблона нужно имя")
        c = {"name": str(t["name"]).strip()[:40], "desc": str(t.get("desc", ""))[:80],
             "layout": str(t.get("layout", ""))[:60],
             "mode": t.get("mode") if t.get("mode") in ("fit", "fill") else "fit"}
        for key, lo, hi in (("cell_size", 100, 4000), ("border", 0, 200)):
            if key in t:
                try:
                    v = int(t[key])
                except (TypeError, ValueError):
                    raise HttpError(400, "bad_pack", f"{key}: нужно число")
                if not lo <= v <= hi:
                    raise HttpError(400, "bad_pack", f"{key}: допустимо {lo}–{hi}")
                c[key] = v
        for key in ("border_color", "bg_color"):
            if key in t:
                if not COLOR_RE.match(str(t[key])):
                    raise HttpError(400, "bad_pack", f"{key}: цвет вида #rrggbb")
                c[key] = str(t[key]).lower()
        clean.append(c)
    return {"id": meta["id"], "name": name, "description": str(meta.get("description", ""))[:300],
            "author": str(meta.get("author", ""))[:60], "version": str(meta.get("version", "1"))[:12],
            "kind": "templates", "templates": clean}


_REASONS = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
            404: "Not Found", 405: "Method Not Allowed", 409: "Conflict",
            413: "Payload Too Large", 426: "Upgrade Required", 429: "Too Many Requests",
            500: "Internal Server Error", 503: "Service Unavailable"}


def create_app(data_dir=None):
    data_dir = data_dir or os.environ.get("PE_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), "photoenjoyer_data")
    return App(data_dir)
