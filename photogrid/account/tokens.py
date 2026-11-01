"""Проверка подписанных токенов сервера (Ed25519) — на стороне программы.

Формат: base64url(JSON).base64url(подпись). Тот же, что выпускает server/security.py;
совместимость проверяется тестами."""
import base64
import json
import time


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_token(pub_key, token, now=None, check_exp=True):
    """Возвращает payload (dict) или None, если подпись неверна/токен просрочен."""
    try:
        body, sig = str(token).split(".")
        pub_key.verify(_b64d(sig), body.encode())
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if check_exp and payload.get("exp", 0) < (now if now is not None else time.time()):
        return None
    return payload
