"""Генерация Ed25519 ключей для подписи обновлений.

Запуск:  python tools/generate_keys.py

Создаст:
    keys/private_key.pem   ← ХРАНИТЕ В СЕКРЕТЕ, никогда не коммитьте
    keys/public_key.pem    ← попадёт в приложение (можно коммитить)

Приватный ключ добавьте в GitHub Secrets как UPDATE_PRIVATE_KEY
(полное содержимое файла .pem, включая BEGIN/END).
"""
import sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("Установите: pip install cryptography")
    sys.exit(1)

HERE = Path(__file__).parent.parent
KEYS = HERE / "keys"
KEYS.mkdir(exist_ok=True)

private_key = Ed25519PrivateKey.generate()
public_key = private_key.public_key()

priv_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
pub_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

(KEYS / "private_key.pem").write_bytes(priv_pem)
(KEYS / "public_key.pem").write_bytes(pub_pem)

print("✓ Ключи созданы:")
print(f"   {KEYS / 'private_key.pem'}   ← СЕКРЕТ, не коммитьте!")
print(f"   {KEYS / 'public_key.pem'}")
print()
print("Далее:")
print("1. Скопируйте содержимое private_key.pem в GitHub Secrets")
print("   Settings → Secrets and variables → Actions → New secret")
print("   Имя: UPDATE_PRIVATE_KEY")
print("2. Скопируйте содержимое public_key.pem в файл")
print("   photogrid/public_key.pem (внутри пакета, попадёт в EXE)")