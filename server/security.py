"""Пароли, ключи лицензий и подписанные токены."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"        # без 0/O/1/I/L
_SCRYPT = dict(n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


# ----------------------------------------------------------------- пароли
def hash_password(password):
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(password, stored):
    try:
        scheme, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expect = base64.b64decode(hash_b64)
        got = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
        return hmac.compare_digest(got, expect)
    except Exception:
        return False


def new_license_key():
    groups = ["".join(secrets.choice(KEY_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "PE-" + "-".join(groups)


def normalize_key(text):
    """Приводит ввод пользователя к виду PE-XXXX-XXXX-XXXX (или возвращает '')."""
    raw = "".join(ch for ch in str(text).upper() if ch.isalnum())
    if raw.startswith("PE"):
        raw = raw[2:]
    if len(raw) != 12 or any(ch not in KEY_ALPHABET for ch in raw):
        return ""
    return f"PE-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def random_password(length=12):
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_ip(salt, ip):
    return hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:16]


# ----------------------------------------------------------------- ключи
def load_or_create_keypair(data_dir):
    """Приватный ключ подписи токенов лежит только на сервере."""
    path = os.path.join(data_dir, "license_private.pem")
    if os.path.exists(path):
        with open(path, "rb") as f:
            priv = serialization.load_pem_private_key(f.read(), password=None)
    else:
        priv = Ed25519PrivateKey.generate()
        pem = priv.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "wb") as f:
            f.write(pem)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return priv


def public_pem(priv):
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_token(priv, payload):
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    return body + "." + _b64e(priv.sign(body.encode()))


def verify_token(pub_key, token, now=None, check_exp=True):
    """Возвращает payload или None. pub_key — Ed25519PublicKey или PEM-байты."""
    try:
        if isinstance(pub_key, (bytes, str)):
            data = pub_key if isinstance(pub_key, bytes) else pub_key.encode()
            pub_key = serialization.load_pem_public_key(data)
        body, sig = token.split(".")
        pub_key.verify(_b64d(sig), body.encode())
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if check_exp and payload.get("exp", 0) < (now if now is not None else time.time()):
        return None
    return payload
