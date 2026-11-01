"""HTTP-клиент сервера (urllib, без сторонних библиотек)."""
import json
import ssl
import urllib.error
import urllib.request

from .. import branding

API = "/api/v1"


class ApiError(Exception):
    """Сервер ответил ошибкой. code — машинный код, message — по-русски."""

    def __init__(self, status, code, message, data=None):
        super().__init__(message)
        self.status, self.code, self.message, self.data = status, code, message, data or {}


class NetworkError(Exception):
    """Нет связи с сервером."""


class ApiClient:
    def __init__(self, base_url, timeout=8.0, app_version=""):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.app_version = app_version
        self.token = None
        self._ctx = ssl.create_default_context()

    # ---- низкоуровневое
    def request(self, method, path, data=None, raw=None, query=None, timeout=None,
                want_bytes=False):
        url = self.base + API + path
        if query:
            from urllib.parse import urlencode
            url += "?" + urlencode(query)
        body = raw if raw is not None else (
            json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None)
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("User-Agent", f"{branding.APP_NAME}/{self.app_version}")
        if raw is not None:
            req.add_header("Content-Type", "application/zip")
        elif body is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout,
                                        context=self._ctx) as r:
                payload = r.read()
                if want_bytes:
                    return payload, dict(r.headers)
                return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read().decode("utf-8"))
            except Exception:
                j = {}
            raise ApiError(e.code, j.get("error", "http_" + str(e.code)),
                           j.get("message") or f"Ошибка сервера ({e.code})", j)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise NetworkError(str(getattr(e, "reason", e))) from e

    # ---- методы API
    def status(self):
        return self.request("GET", "/status", timeout=5)

    def login(self, username, password, hwid, device_name):
        return self.request("POST", "/auth/login", {
            "username": username, "password": password, "hwid": hwid,
            "device_name": device_name, "app_version": self.app_version})

    def register(self, key, username, password, hwid, device_name, consent):
        return self.request("POST", "/auth/register", {
            "key": key, "username": username, "password": password, "hwid": hwid,
            "device_name": device_name, "app_version": self.app_version,
            "consent": bool(consent)})

    def release_device(self, username, password, device_id):
        return self.request("POST", "/auth/release-device", {
            "username": username, "password": password, "device_id": device_id})

    def refresh(self):
        return self.request("POST", "/auth/refresh", {"app_version": self.app_version})

    def me(self):
        return self.request("GET", "/me")

    def change_password(self, old, new):
        return self.request("POST", "/me/password", {"old_password": old, "new_password": new})

    def activate_key(self, key):
        return self.request("POST", "/me/activate-key", {"key": key})

    def remove_device(self, device_id):
        return self.request("DELETE", f"/me/devices/{device_id}")

    def set_usage_stats(self, on):
        return self.request("POST", "/me/settings", {"usage_stats": bool(on)})

    def delete_account(self, password):
        return self.request("POST", "/me/delete", {"password": password})

    def send_events(self, events):
        return self.request("POST", "/events", {"events": events,
                                                "app_version": self.app_version}, timeout=6)

    def announcements(self):
        return self.request("GET", "/announcements")["items"]

    def library(self):
        return self.request("GET", "/library")["items"]

    def library_download(self, pack_id):
        return self.request("GET", f"/library/{pack_id}/download", want_bytes=True,
                            timeout=30)

    # ---- админ
    def admin(self, method, path, data=None, query=None, raw=None):
        return self.request(method, "/admin" + path, data=data, query=query, raw=raw,
                            timeout=20)
