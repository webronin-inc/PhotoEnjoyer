"""Подписывает manifest.json приватным ключом Ed25519.

Запуск:
    python tools/sign_manifest.py manifest.json

Создаёт/обновляет поле 'signature' в manifest.json.
Используется в CI перед публикацией.
"""
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def sign(manifest_path: Path, private_key_path: Path) -> None:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data.pop("signature", None)

    canonical = json.dumps(data, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")).encode("utf-8")

    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    sig = private_key.sign(canonical)
    data["signature"] = base64.b64encode(sig).decode("ascii")

    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ Подписан: {manifest_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python tools/sign_manifest.py manifest.json")
        sys.exit(1)

    manifest = Path(sys.argv[1])
    # Приватный ключ: сначала из переменной окружения (для CI),
    # иначе из keys/private_key.pem (для локального использования)
    import os
    env_key = os.environ.get("UPDATE_PRIVATE_KEY")
    if env_key:
        tmp = Path("keys/_tmp_private.pem")
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(env_key, encoding="utf-8")
        sign(manifest, tmp)
        tmp.unlink()
    else:
        key = Path("keys/private_key.pem")
        if not key.exists():
            print("Нет keys/private_key.pem и UPDATE_PRIVATE_KEY")
            sys.exit(1)
        sign(manifest, key)