"""Проверки перед запуском: вход, регистрация по ключу, возобновление сессии.

Логика отделена от интерфейса — окно входа только показывает ход проверок.
Проверки (шаги для экрана): network → version → account → license → device → clock.
"""
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from .. import server_config
from ..version import __version__
from . import device, store
from .tokens import verify_token
from .api import ApiClient, ApiError, NetworkError
from .session import Session

STEPS = (
    ("network", "Связь с сервером"),
    ("version", "Версия программы"),
    ("account", "Аккаунт"),
    ("license", "Лицензия"),
    ("device", "Это устройство"),
    ("clock", "Дата и время"),
)

CLOCK_WARN = 10 * 60            # 10 минут расхождения — предупреждение
CLOCK_BLOCK = 24 * 3600         # сутки — блокировка (иначе срок токена теряет смысл)
ROLLBACK_TOLERANCE = 3600       # часы «назад» больше чем на час — подозрительно


class GateError(Exception):
    def __init__(self, code, message, step="account", action=None, data=None):
        super().__init__(message)
        self.code, self.message, self.step = code, message, step
        self.action, self.data = action, data or {}


# каким шагом проверки считать код ошибки сервера
_ERR_STEP = {
    "maintenance": "version", "update_required": "version",
    "bad_credentials": "account", "locked": "account", "banned": "account",
    "invalid_key": "account", "key_used": "account", "key_revoked": "account",
    "username_taken": "account", "bad_username": "account", "weak_password": "account",
    "consent_required": "account", "token_invalid": "account",
    "device_limit": "device", "device_removed": "device", "bad_device": "device",
    "license_expired": "license", "license_revoked": "license", "license_none": "license",
}
_ERR_ACTION = {"update_required": "update", "device_limit": "devices",
               "locked": "wait", "maintenance": "wait"}


# ------------------------------------------------------------- настройка
def public_key():
    """Открытый ключ сервера, вшитый в программу (или None, если не настроен)."""
    candidates = [os.environ.get("PE_LICENSE_PUB"),
                  Path(__file__).resolve().parents[1] / "license_pub.pem"]
    for c in candidates:
        if c and Path(c).exists():
            try:
                return serialization.load_pem_public_key(Path(c).read_bytes())
            except Exception:
                continue
    return None


def server_url():
    return (os.environ.get("PE_SERVER_URL") or server_config.SERVER_URL or "").strip()


def enforced():
    """Вход включён, только когда указан адрес сервера и есть открытый ключ."""
    return bool(server_url()) and public_key() is not None


def make_api():
    return ApiClient(server_url(), app_version=__version__)


# -------------------------------------------------------- проверка токена
def verify_token_local(token, pub, now=None, hwid=None, last_seen=0):
    """Офлайн-проверка: подпись, срок, устройство, откат часов, лицензия."""
    now = now if now is not None else time.time()
    claims = verify_token(pub, token, now=now)
    if not claims:
        raise GateError("token_invalid", "Сессия устарела — войдите заново", "account")
    if hwid and claims.get("dev") != hwid:
        raise GateError("device_removed", "Сессия принадлежит другому компьютеру", "device")
    if last_seen and now < last_seen - ROLLBACK_TOLERANCE:
        raise GateError("clock_rollback", "Системные часы сдвинуты назад. Исправьте дату "
                        "и время и подключитесь к интернету.", "clock", "wait")
    return claims


def _lic_ok(claims, now):
    if claims.get("role") == "admin":
        return True
    lic = claims.get("lic", {})
    if lic.get("state") != "active":
        return False
    exp = lic.get("exp")
    return exp is None or exp > now


# ----------------------------------------------------------- онлайн-вход
def _finish(api, resp, remember, pub, hwid, progress):
    """Общая часть после успешного ответа login/register."""
    now = time.time()
    token = resp["token"]
    # сервер должен быть настоящим: токен подписан нашим ключом
    try:
        verify_token_local(token, pub, now=resp.get("server_time", now), hwid=hwid)
    except GateError:
        raise GateError("untrusted_server", "Ответ сервера не прошёл проверку подлинности. "
                        "Проверьте адрес сервера.", "account")
    progress("account", "ok")
    session = Session(api, token, resp)
    lic_ok = session.license_active
    progress("license", "ok" if lic_ok else "fail",
             "" if lic_ok else "лицензия не активна")
    progress("device", "ok")
    skew = abs(resp.get("server_time", now) - now)
    if skew > CLOCK_BLOCK:
        raise GateError("clock", "Дата и время на компьютере сильно отличаются от "
                        "реальных. Исправьте их и повторите.", "clock")
    progress("clock", "ok" if skew <= CLOCK_WARN else "warn",
             "" if skew <= CLOCK_WARN else "часы спешат/отстают")
    if remember:
        store.save(token, session.username, True, resp.get("server_time", now))
    else:
        store.clear()
    return session


def _call(step_fn, progress):
    try:
        return step_fn()
    except NetworkError as e:
        progress("network", "fail", str(e))
        raise GateError("network", "Нет связи с сервером. Проверьте интернет.", "network",
                        "retry")
    except ApiError as e:
        step = _ERR_STEP.get(e.code, "account")
        if step != "version":
            progress("network", "ok")
            progress("version", "ok")
        else:
            progress("network", "ok")
        progress(step, "fail", e.message)
        raise GateError(e.code, e.message, step, _ERR_ACTION.get(e.code), e.data)


def authenticate(api, mode, creds, remember, progress=lambda *a: None, pub=None):
    """Вход или регистрация. Бросает GateError; возвращает Session."""
    pub = pub or public_key()
    hw, dev = device.hwid(), device.device_name()
    progress("network", "running")
    try:
        api.status()
    except NetworkError as e:
        progress("network", "fail", str(e))
        raise GateError("network", "Нет связи с сервером. Проверьте интернет.", "network", "retry")
    except ApiError:
        pass                                  # status не критичен — решит сам вход
    progress("network", "ok")
    progress("version", "running")
    if mode == "register":
        call = lambda: api.register(creds["key"], creds["username"], creds["password"],
                                    hw, dev, creds.get("consent", False))
    else:
        call = lambda: api.login(creds["username"], creds["password"], hw, dev)
    progress("version", "ok")
    progress("account", "running")
    resp = _call(call, progress)
    return _finish(api, resp, remember, pub, hw, progress)


# ----------------------------------------------------- возобновление сессии
def resume(api, progress=lambda *a: None, pub=None, now=None):
    """Автовход по сохранённому токену. None — сохранённой сессии нет.

    Онлайн: обновляет токен. Без сети: работает по подписанному токену, пока он
    не истёк (до 7 дней после последнего подключения) и лицензия действует."""
    pub = pub or public_key()
    saved = store.load()
    if not saved:
        return None
    now = now if now is not None else time.time()
    hw = device.hwid()
    try:
        claims = verify_token_local(saved["token"], pub, now=now, hwid=hw,
                                    last_seen=saved.get("last_seen", 0))
    except GateError as e:
        if e.code in ("token_invalid", "device_removed"):
            store.clear()
        raise
    api.token = saved["token"]
    progress("network", "running")
    try:
        resp = api.refresh()
    except NetworkError as e:
        progress("network", "fail", str(e))
        # офлайн-режим: токен подписан и не просрочен
        if not _lic_ok(claims, now):
            raise GateError("license_expired", "Срок лицензии истёк. Подключитесь к "
                            "интернету, чтобы продлить.", "license", "activate")
        for s in ("version", "account", "license", "device", "clock"):
            progress(s, "ok" if s != "version" else "skip")
        info = {"user": {"username": claims["u"], "role": claims["role"], "usage_stats": True},
                "license": {"state": claims["lic"]["state"], "plan": claims["lic"]["plan"],
                            "expires": claims["lic"]["exp"], "max_devices": claims["lic"].get("devices", 1)},
                "devices": []}
        store.touch_last_seen(int(now))
        return Session(api, saved["token"], info, offline=True)
    except ApiError as e:
        if e.code in ("token_invalid", "device_removed", "banned"):
            store.clear()
        step = _ERR_STEP.get(e.code, "account")
        progress("network", "ok")
        progress(step, "fail", e.message)
        raise GateError(e.code, e.message, step, _ERR_ACTION.get(e.code), e.data)
    progress("network", "ok")
    progress("version", "ok")
    return _finish(api, resp, saved.get("remember", True), pub, hw, progress)


def logout(session=None):
    store.clear()
    if session is not None:
        session.close()
